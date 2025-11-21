# scrapers/twse_mi_index.py
import os
import time
import json
from datetime import datetime, timezone
import requests
from .utils import safe_parse_json

URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
RESULT_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TWStockBot/1.0)", "Accept": "application/json"}

def ensure_result_dir():
    os.makedirs(RESULT_DIR, exist_ok=True)

def _to_float_or_int(s):
    if s is None:
        return None
    try:
        s2 = str(s).replace(",", "").strip()
        if "." in s2:
            return float(s2)
        return int(s2)
    except Exception:
        return None

def fetch(timeout=10):
    t0 = time.time()
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        r = session.get(URL, timeout=timeout)
        r.raise_for_status()
    except Exception as e:
        return {"timestamp": int(time.time()), "source": URL, "data": {}, "meta": {"status": "error", "message": f"request error: {e}", "elapsed_ms": int((time.time()-t0)*1000)}}

    elapsed = int((time.time() - t0) * 1000)
    try:
        payload = safe_parse_json(r)
    except Exception as e:
        payload = None

    if payload is None:
        ensure_result_dir()
        dump = os.path.join(RESULT_DIR, f"twse_mi_index_raw_{int(time.time())}.txt")
        with open(dump, "w", encoding="utf-8") as f:
            f.write(r.text)
        return {"timestamp": int(time.time()), "source": r.url, "data": {}, "meta": {"status": "error", "message": "invalid json or empty response", "elapsed_ms": elapsed, "saved_raw": dump}}

    # payload is expected to be a list of dicts; find the row with 指數 == '發行量加權股價指數'
    target = None
    if isinstance(payload, list):
        for item in payload:
            try:
                if item.get("指數") == "發行量加權股價指數":
                    target = item
                    break
            except Exception:
                continue
        # if not found, fallback to first entry that has 收盤指數
        if target is None:
            for item in payload:
                if "收盤指數" in item:
                    target = item
                    break

    if not target:
        return {"timestamp": int(time.time()), "source": r.url, "data": {}, "meta": {"status": "error", "message": "no suitable record found", "elapsed_ms": elapsed}}

    close_raw = target.get("收盤指數")
    close_val = _to_float_or_int(close_raw)

    result = {
        "timestamp": int(time.time()),
        "source": r.url,
        "data": {
            "mi_index_close": {"raw": close_raw, "value": close_val}
        },
        "meta": {"status": "ok" if close_val is not None else "error", "elapsed_ms": elapsed}
    }
    return result

def save_result(result, prefix="twse_mi_index"):
    ensure_result_dir()
    latest = os.path.join(RESULT_DIR, f"latest_{prefix}.json")
    date_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive = os.path.join(RESULT_DIR, f"{date_tag}_{prefix}.json")
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if not os.path.exists(archive):
        with open(archive, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    return latest

if __name__ == "__main__":
    res = fetch()
    if res.get("meta", {}).get("status") == "ok":
        save_result(res)
    print(json.dumps(res, ensure_ascii=False, indent=2))
