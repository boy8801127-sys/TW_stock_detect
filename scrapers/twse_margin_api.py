# scrapers/twse_margin_api.py
import os
import json
import time
from datetime import datetime, timezone
import requests
from .utils import safe_parse_json

URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TWStockBot/1.0)"}
RESULT_DIR = os.path.join(os.path.dirname(__file__), "..", "results")

def ensure_result_dir():
    os.makedirs(RESULT_DIR, exist_ok=True)

def _to_int(s):
    if s is None:
        return None
    try:
        return int(str(s).replace(",", "").strip())
    except Exception:
        return None

def _safe_div(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return a / b
    except Exception:
        return None

def fetch():
    params = {"response": "json", "_": str(int(time.time() * 1000))}
    r = requests.get(URL, headers=HEADERS, params=params, timeout=15)
    try:
        r.raise_for_status()
    except Exception as e:
        return {"timestamp": int(time.time()), "source": URL, "data": {}, "meta": {"status": "error", "message": f"request error: {e}"}}

    data = safe_parse_json(r)
    if data is None:
        return {"timestamp": int(time.time()), "source": r.url, "data": {}, "meta": {"status": "error", "message": "invalid or non-json response from TWSE", "saved_raw_snippet": r.text[:1000]}}

    # 取 tables[0].data，假設格式與你貼出的一致
    tables = data.get("tables") or []
    if not tables or not isinstance(tables, list) or not tables[0].get("data"):
        return {"timestamp": int(time.time()), "source": URL, "data": {}, "meta": {"status": "error", "message": "unexpected json structure"}}

    rows = tables[0]["data"]
    # 融資 區塊在 row 0，融券 在 row 1；前日餘額 在 index 4，今日餘額 在 index 5
    try:
        fin_prev = _to_int(rows[0][4])
        fin_today = _to_int(rows[0][5])
    except Exception:
        fin_prev = fin_today = None
    try:
        short_prev = _to_int(rows[1][4])
        short_today = _to_int(rows[1][5])
    except Exception:
        short_prev = short_today = None

    ratio_prev = _safe_div(short_prev, fin_prev)
    ratio_today = _safe_div(short_today, fin_today)

    ratio_delta = None if (ratio_prev is None or ratio_today is None) else (ratio_today - ratio_prev)
    ratio_pct = None
    if ratio_prev not in (None, 0) and ratio_delta is not None:
        ratio_pct = ratio_delta / abs(ratio_prev)

    result = {
        "timestamp": int(time.time()),
        "source": r.url,
        "data": {
            "financing": {"previous": fin_prev, "today": fin_today},
            "shorting": {"previous": short_prev, "today": short_today},
            "ratio": {
                "previous": ratio_prev,
                "today": ratio_today,
                "delta": ratio_delta,
                "pct_change": ratio_pct
            }
        },
        "meta": {"status": "ok" if any(v is not None for v in [fin_prev, fin_today, short_prev, short_today]) else "error", "elapsed_ms": None}
    }

    return result

def save(result, prefix="twse_margin_api"):
    ensure_result_dir()
    latest = os.path.join(RESULT_DIR, f"latest_{prefix}.json")
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive = os.path.join(RESULT_DIR, f"{tag}_{prefix}.json")
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if not os.path.exists(archive):
        with open(archive, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    start = time.time()
    try:
        res = fetch()
        res["meta"]["elapsed_ms"] = int((time.time() - start) * 1000)
        if res["meta"]["status"] == "ok":
            save(res)
    except Exception as e:
        res = {"timestamp": int(time.time()), "source": URL, "data": {}, "meta": {"status": "error", "message": str(e)}}
    print(json.dumps(res, ensure_ascii=False, indent=2))
