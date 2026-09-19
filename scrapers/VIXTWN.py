# scrapers/VIXTWN.py
"""
Scraper for 臺指選擇權波動率指數 (TAIWAN VIX).

Provides:
- fetch() -> returns standardized dict with meta.status "ok" or "error"
- save_result(result) -> saves latest and daily archive into results/
"""
import time
import requests
from .utils import HEADERS as BASE_HEADERS, error_result, make_result, run_cli, safe_parse_json, save_json, to_float

URL = "https://mis.taifex.com.tw/futures/api/getQuoteListVIX"
HEADERS = {
    **BASE_HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://mis.taifex.com.tw",
    "Origin": "https://mis.taifex.com.tw",
    "Content-Type": "application/json",
}


def fetch():
    t0 = time.time()
    try:
        resp = requests.post(URL, headers=HEADERS, json={}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        return error_result(URL, f"request error: {e}")

    elapsed = int((time.time() - t0) * 1000)
    payload = safe_parse_json(resp)
    if payload is None:
        return error_result(URL, "invalid or non-json response from VIX endpoint", elapsed_ms=elapsed)

    quotes = payload.get("RtData", {}).get("QuoteList", [])
    last_raw = quotes[0].get("CLastPrice") if quotes and isinstance(quotes[0], dict) else None
    last_val = to_float(last_raw)
    # 來源偶爾回傳 0 當佔位值，視為錯誤以免覆蓋快取
    return make_result(URL, {"vix": {"raw": last_raw, "value": last_val}},
                       status="ok" if last_val is not None and last_val > 0 else "error", elapsed_ms=elapsed)


def save_result(result):
    return save_json(result, "taifex_vix")


if __name__ == "__main__":
    run_cli(fetch, save_result)
