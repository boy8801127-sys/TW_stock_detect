# scrapers/ai_summary.py
"""
Calls the Claude API to turn the day's aggregated indicator summary into a short
Traditional Chinese narrative (~50 chars, three sentences). Not auto-discovered as
a regular scraper: it needs the full aggregated summary (after all scrapers have
run), so it's invoked explicitly from main.build_and_optionally_send().

Configure via environment variables:
  ANTHROPIC_API_KEY  - required; if unset, generate_summary() returns None
  AI_SUMMARY_ENABLED - default "true"; set "false" to skip
  AI_SUMMARY_MODEL    - default "claude-haiku-4-5-20251001"
"""
import os
import json
import requests

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

PROMPT_TEMPLATE = """你是台股開盤前指標分析助手。根據以下 JSON 數據，用繁體中文寫一段約 50 字的簡評，務必恰好三句：
第一句：夜盤指數與前一交易日台股收盤的比較（漲跌方向與幅度）。
第二句：從 VIX、美股恐懼貪婪指數、券資比、期貨未平倉口數、融資融券這幾項中，挑出最異常或最值得注意的一至三項說明。
第三句：簡短總結今日整體偏多/偏空/觀望的判斷。
只輸出這段文字本身，不要加引號、不要加「簡評：」這類前綴。

數據：{facts}"""


def _get(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _extract_key_facts(summary):
    scrapers = summary.get("scrapers", {})
    facts = {}

    nf = _get(scrapers, "cmoney_futures_night", "data", "night_futures") or {}
    if nf.get("index") is not None:
        facts["夜盤指數"] = nf.get("index")
        facts["夜盤漲跌"] = nf.get("change")
        facts["夜盤漲跌幅"] = nf.get("pct_change")

    vix_entry = scrapers.get("VIXTWN") or {}
    if vix_entry.get("ok"):
        vix_val = _get(vix_entry, "data", "vix", "value")
        if vix_val and vix_val > 0:
            facts["VIX"] = vix_val

    fg = _get(scrapers, "cnn_fear_greed", "data") or {}
    if fg.get("score") is not None:
        facts["美股恐懼貪婪指數"] = fg.get("score")
        facts["美股恐懼貪婪指數分級"] = fg.get("rating")

    ratio = _get(scrapers, "twse_margin_api", "data", "ratio") or {}
    if ratio.get("today") is not None:
        facts["券資比"] = round(ratio["today"] * 100, 2)
        if ratio.get("delta") is not None:
            facts["券資比變化_pt"] = round(ratio["delta"] * 100, 2)

    fut = _get(scrapers, "taifex_futures", "data") or {}
    fut_lines = {}
    for label, key in (("外資", "foreign"), ("自營", "dealer"), ("投信", "inv_trust")):
        item = fut.get(key) or {}
        if isinstance(item, dict) and item.get("current") is not None:
            fut_lines[label] = item.get("current")
    if fut_lines:
        facts["期貨未平倉口數"] = fut_lines

    margin = _get(scrapers, "cmoney_margin", "data", "margin") or {}
    short = _get(scrapers, "cmoney_margin", "data", "short") or {}
    if margin.get("balance_billion") is not None:
        facts["融資餘額_億"] = margin.get("balance_billion")
        facts["融資使用率"] = margin.get("usage_rate")
        facts["融資維持率"] = margin.get("maintenance_rate")
    if short.get("balance_lots") is not None:
        facts["融券餘額_張"] = short.get("balance_lots")
        facts["融券使用率"] = short.get("usage_rate")

    adr = _get(scrapers, "tsm_adr_compare", "data") or {}
    if adr.get("premium_pct") is not None:
        facts["台積電ADR溢價折價百分比"] = round(adr["premium_pct"], 2)

    return facts


def generate_summary(summary):
    if os.getenv("AI_SUMMARY_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    facts = _extract_key_facts(summary)
    if not facts:
        return None

    model = os.getenv("AI_SUMMARY_MODEL", "claude-haiku-4-5-20251001")
    prompt = PROMPT_TEMPLATE.format(facts=json.dumps(facts, ensure_ascii=False))

    try:
        resp = requests.post(
            API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("content", [{}])[0].get("text", "").strip()
        return text or None
    except Exception as e:
        print(f"[ai_summary.generate_summary] failed: {e}")
        return None


if __name__ == "__main__":
    sample_summary = {
        "scrapers": {
            "cmoney_futures_night": {"ok": True, "data": {"night_futures": {"index": 23510, "change": 85, "pct_change": 0.36}}},
            "VIXTWN": {"ok": True, "data": {"vix": {"value": 18.32}}},
            "cnn_fear_greed": {"ok": True, "data": {"score": 32, "rating": "恐懼"}},
            "twse_margin_api": {"ok": True, "data": {"ratio": {"today": 0.0234, "delta": 0.0005}}},
        }
    }
    print(generate_summary(sample_summary))
