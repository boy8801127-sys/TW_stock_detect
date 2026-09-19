# scrapers/twse_mi_index.py
import time
import requests
from .utils import HEADERS, error_result, make_result, run_cli, safe_parse_json, save_json, to_float

URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"


def fetch(timeout=10):
    t0 = time.time()
    try:
        r = requests.get(URL, headers={**HEADERS, "Accept": "application/json"}, timeout=timeout)
        r.raise_for_status()
    except Exception as e:
        return error_result(URL, f"request error: {e}", elapsed_ms=int((time.time() - t0) * 1000))

    elapsed = int((time.time() - t0) * 1000)
    payload = safe_parse_json(r)
    if payload is None:
        return error_result(r.url, "invalid json or empty response", elapsed_ms=elapsed)

    # 取 指數 == '發行量加權股價指數' 那列；找不到則取第一筆有收盤指數的
    rows = payload if isinstance(payload, list) else []
    target = (next((i for i in rows if i.get("指數") == "發行量加權股價指數"), None)
              or next((i for i in rows if "收盤指數" in i), None))
    if not target:
        return error_result(r.url, "no suitable record found", elapsed_ms=elapsed)

    close_raw = target.get("收盤指數")
    close_val = to_float(close_raw)
    return make_result(r.url, {"mi_index_close": {"raw": close_raw, "value": close_val}},
                       status="ok" if close_val is not None else "error", elapsed_ms=elapsed)


def save_result(result):
    return save_json(result, "twse_mi_index")


if __name__ == "__main__":
    run_cli(fetch, save_result)
