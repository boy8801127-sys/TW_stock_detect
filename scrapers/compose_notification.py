# scrapers/compose_notification.py
import os
import re
import glob
import json
from datetime import datetime, timezone

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
SUMMARY_PATH = os.path.join(RESULTS_DIR, "latest_summary.json")
MAINT_PATH = os.path.join(RESULTS_DIR, "latest_maintenance_calc.json")

WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def _fmt_number(v, decimals=None):
    if v is None:
        return "-"
    try:
        vv = float(str(v).replace(",", "")) if isinstance(v, str) else float(v)
    except Exception:
        return str(v)
    if decimals is None:
        if abs(vv - int(vv)) < 1e-8:
            return f"{int(vv):,}"
        return f"{vv:,}"
    fmt = f"{{:,.{decimals}f}}"
    s = fmt.format(vv)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _fmt_signed(v, decimals=0):
    if v is None:
        return "-"
    try:
        vv = float(v)
    except Exception:
        return str(v)
    fmt = f"{{:+,.{decimals}f}}"
    s = fmt.format(vv)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
        if s.endswith(("+", "-")):
            s += "0"
    return s


def _sign_symbol(delta):
    try:
        d = float(delta)
    except Exception:
        return "→"
    if d > 0:
        return "▲"
    if d < 0:
        return "▼"
    return "→"


def _load_json_try(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _find_previous_value(prefix, today_str, extractor):
    """Read the most recent {date}_{prefix}.json archive strictly before today_str
    and run extractor(json_obj) -> value. Returns None if nothing usable is found.
    """
    rx = re.compile(r"^(\d{4}-\d{2}-\d{2})_" + re.escape(prefix) + r"\.json$")
    dates = []
    try:
        for fp in glob.glob(os.path.join(RESULTS_DIR, f"*_{prefix}.json")):
            m = rx.match(os.path.basename(fp))
            if m and m.group(1) < today_str:
                dates.append(m.group(1))
    except Exception:
        return None
    if not dates:
        return None
    dates.sort()
    j = _load_json_try(os.path.join(RESULTS_DIR, f"{dates[-1]}_{prefix}.json"))
    if not j:
        return None
    try:
        return extractor(j)
    except Exception:
        return None


def _vix_interpret_by_change(pct_change):
    if pct_change is None:
        return "情緒平穩（無前日資料可比較）"
    if pct_change > 20:
        return "市場恐慌情緒急升"
    if pct_change > 5:
        return "情緒升溫，市場不安感增加"
    if pct_change >= -5:
        return "情緒平穩"
    if pct_change >= -20:
        return "情緒回落，波動趨緩"
    return "市場恐慌情緒明顯消退"


def _maintenance_level(rate):
    if rate is None:
        return "", ""
    if rate >= 180:
        return "🟢", "過高，融資空間充裕"
    if rate >= 150:
        return "🟡", "中等，正常水位"
    if rate >= 130:
        return "🟠", "偏低，需留意"
    return "🔴", "危險，接近追繳水位"


def build_message(summary):
    gen = summary.get("generated_at")
    try:
        dt = datetime.fromisoformat(gen) if gen else datetime.now(timezone.utc).astimezone()
    except Exception:
        dt = datetime.now(timezone.utc).astimezone()
    today_str = dt.strftime("%Y-%m-%d")
    weekday = WEEKDAY_CN[dt.weekday()]

    scrapers = summary.get("scrapers", {})
    sections = []

    # ── 大盤指數 ──────────────────────────────
    idx_lines = []
    if "twse_mi_index" in scrapers:
        v = scrapers["twse_mi_index"].get("data", {}).get("mi_index_close", {})
        val = v.get("value")
        if val is not None:
            prev = _find_previous_value(
                "twse_mi_index", today_str,
                lambda j: j.get("data", {}).get("mi_index_close", {}).get("value"),
            )
            delta = (val - prev) if prev is not None else None
            pct = (delta / prev * 100) if (delta is not None and prev) else None
            sym = _sign_symbol(delta)
            extra = f"  {sym} {_fmt_signed(delta)} ({_fmt_signed(pct, 2)}%)" if delta is not None else ""
            idx_lines.append(f"📈 加權指數：{_fmt_number(val, 0)}{extra}")

    if "cmoney_futures_night" in scrapers:
        nf = scrapers["cmoney_futures_night"].get("data", {}).get("night_futures", {})
        val = nf.get("index")
        if val is not None:
            change = nf.get("change")
            pct = nf.get("pct_change")
            sym = _sign_symbol(change)
            extra = f"  {sym} {_fmt_signed(change)} ({_fmt_signed(pct, 2)}%)" if change is not None else ""
            idx_lines.append(f"🌙 台指期夜盤：{_fmt_number(val, 0)}{extra}")

    if idx_lines:
        sections.append("━━━━━━ 大盤指數 ━━━━━━\n" + "\n".join(idx_lines))

    # ── 市場情緒 (VIX) ────────────────────────
    if "VIXTWN" in scrapers:
        v = scrapers["VIXTWN"].get("data", {}).get("vix", {})
        val = v.get("value")
        if val is not None:
            prev = _find_previous_value(
                "taifex_vix", today_str,
                lambda j: j.get("data", {}).get("vix", {}).get("value"),
            )
            delta = (val - prev) if prev is not None else None
            pct = (delta / prev * 100) if (delta is not None and prev) else None
            sym = _sign_symbol(delta)
            extra = f"  {sym} {_fmt_signed(delta, 1)}（{_fmt_signed(pct, 1)}%）" if delta is not None else ""
            interp = _vix_interpret_by_change(pct)
            sections.append(
                "━━━━━━ 市場情緒 ━━━━━━\n"
                f"🌡 VIX：{_fmt_number(val, 2)}{extra}\n"
                f"   {interp}"
            )

    # ── 券資比 ────────────────────────────────
    if "twse_margin_api" in scrapers:
        ratio = scrapers["twse_margin_api"].get("data", {}).get("ratio", {})
        today = ratio.get("today")
        delta = ratio.get("delta")
        if today is not None:
            sym = _sign_symbol(delta or 0)
            pt_str = f"{delta * 100:+.2f}pt" if delta is not None else "-"
            sections.append(
                "━━━━━━ 券資比 ━━━━━━\n"
                f"⚖️ 券資比：{today * 100:.2f}%  {sym} ({pt_str})"
            )

    # ── 期貨未平倉口數 ────────────────────────
    if "taifex_futures" in scrapers:
        data = scrapers["taifex_futures"].get("data", {})

        def cur(key):
            item = data.get(key) or {}
            return item.get("current") if isinstance(item, dict) else item

        fut_lines = []
        for label, key in (("外資", "foreign"), ("自營", "dealer"), ("投信", "inv_trust")):
            val = cur(key)
            if val is None:
                continue
            prev = _find_previous_value(
                "taifex", today_str,
                lambda j, k=key: (j.get("data", {}).get(k) or {}).get("current"),
            )
            delta = (val - prev) if prev is not None else None
            sym = _sign_symbol(delta)
            delta_str = f"  {sym} {_fmt_signed(delta)}" if delta is not None else f"  {sym}"
            fut_lines.append(f"{label} {_fmt_number(val, 0):>7}{delta_str}")
        if fut_lines:
            sections.append("━━━━━━ 期貨未平倉口數 ━━━━━━\n" + "\n".join(fut_lines))

    # ── 融資融券 (CMoney) ─────────────────────
    if "cmoney_margin" in scrapers:
        data = scrapers["cmoney_margin"].get("data", {})
        margin = data.get("margin", {})
        short = data.get("short", {})
        margin_lines = []

        bal = margin.get("balance_billion")
        if bal is not None:
            chg = margin.get("change_billion")
            sym = _sign_symbol(chg)
            chg_str = f"  {sym} {_fmt_signed(chg, 0)}億" if chg is not None else ""
            margin_lines.append(f"💰 融資餘額：{_fmt_number(bal, 0)}億{chg_str}")

            usage = margin.get("usage_rate")
            maint = margin.get("maintenance_rate")
            parts = []
            if usage is not None:
                parts.append(f"使用率 {usage:.2f}%")
            if maint is not None:
                emoji, label = _maintenance_level(maint)
                parts.append(f"維持率 {maint:.1f}%  {emoji} {label}")
            if parts:
                margin_lines.append("   " + "  ".join(parts))

        short_bal = short.get("balance_lots")
        if short_bal is not None:
            chg = short.get("change_lots")
            sym = _sign_symbol(chg)
            chg_str = f"  {sym} {_fmt_signed(chg, 0)}張" if chg is not None else ""
            margin_lines.append(f"\n🔻 融券餘額：{_fmt_number(short_bal, 0)}張{chg_str}")
            usage = short.get("usage_rate")
            if usage is not None:
                margin_lines.append(f"   使用率 {usage:.2f}%")

        if margin_lines:
            sections.append("━━━━━━ 融資融券 ━━━━━━\n" + "\n".join(margin_lines))

    header = f"📊 台股早盤指標 — {today_str}（{weekday}）"
    body = "\n\n".join(sections)
    footer = "━━━━━━━━━━━━━━━━━━━━"
    return f"{header}\n\n{body}\n\n{footer}" if body else header


def load_summary(path=SUMMARY_PATH):
    j = _load_json_try(path)
    if j:
        return j
    j2 = _load_json_try(MAINT_PATH)
    if j2:
        return {"generated_at": None, "scrapers": {"maintenance_calc": j2.get("data", {}).get("maintenance_calc", j2.get("data", {}))}}
    raise FileNotFoundError(f"Neither {path} nor {MAINT_PATH} found")


def main():
    summary = load_summary()
    msg = build_message(summary)
    print(msg)
    return msg


if __name__ == "__main__":
    main()
