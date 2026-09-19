# scrapers/twse_margin_api.py
import time
import requests
from .utils import HEADERS, error_result, make_result, run_cli, safe_parse_json, to_int

URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"


def _balances(rows, i):
    """rows[i] 的 (前日餘額, 今日餘額)：index 4 與 5。"""
    try:
        return to_int(rows[i][4]), to_int(rows[i][5])
    except (IndexError, TypeError):
        return None, None


def _safe_div(a, b):
    return a / b if a is not None and b else None


def fetch():
    params = {"response": "json", "_": str(int(time.time() * 1000))}
    try:
        r = requests.get(URL, headers=HEADERS, params=params, timeout=15)
        r.raise_for_status()
    except Exception as e:
        return error_result(URL, f"request error: {e}")

    data = safe_parse_json(r)
    if data is None:
        return error_result(r.url, "invalid or non-json response from TWSE")

    tables = data.get("tables") or []
    if not tables or not tables[0].get("data"):
        return error_result(URL, "unexpected json structure")

    rows = tables[0]["data"]
    # 融資 區塊在 row 0，融券 在 row 1
    fin_prev, fin_today = _balances(rows, 0)
    short_prev, short_today = _balances(rows, 1)

    ratio_prev = _safe_div(short_prev, fin_prev)
    ratio_today = _safe_div(short_today, fin_today)
    ratio_delta = None if (ratio_prev is None or ratio_today is None) else (ratio_today - ratio_prev)

    ok = any(v is not None for v in (fin_prev, fin_today, short_prev, short_today))
    return make_result(r.url, {
        "financing": {"previous": fin_prev, "today": fin_today},
        "shorting": {"previous": short_prev, "today": short_today},
        "ratio": {"previous": ratio_prev, "today": ratio_today, "delta": ratio_delta},
    }, status="ok" if ok else "error")


if __name__ == "__main__":
    run_cli(fetch)
