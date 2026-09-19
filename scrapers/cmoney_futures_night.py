# scrapers/cmoney_futures_night.py
"""
Scraper for 台指期夜盤 (CMoney TXF1).

The page is client-rendered (Vue), so static HTML fetch returns no data.
We drive a headless browser and intercept the page's own XHR call to
FuturesNightCalculation, matched by row shape (9 columns: CommKey, 即時成交價,
漲跌, 漲跌幅, 開盤價, 最高價, 最低價, 即時成交量, 累計成交量) since the endpoint
name is reused with a different column set elsewhere on the page.

Provides:
- fetch() -> standardized dict with meta.status "ok" or "error"
- save_result(result) -> saves latest + daily archive into results/
"""
import time
from .utils import capture_xhr, error_result, make_result, run_cli, save_json, to_float

URL = "https://www.cmoney.tw/forum/futures/TXF1?s=p"
EXPECTED_COLUMNS = 9


def _is_night_table(body):
    return isinstance(body, list) and bool(body) and isinstance(body[0], list) and len(body[0]) == EXPECTED_COLUMNS


def fetch():
    t0 = time.time()
    try:
        body = capture_xhr(URL, "FuturesNightCalculation", accept=_is_night_table)
    except Exception as e:
        return error_result(URL, f"playwright error: {e}")

    elapsed = int((time.time() - t0) * 1000)
    if not body:
        return error_result(URL, "no FuturesNightCalculation response captured", elapsed_ms=elapsed)

    # row: [CommKey, 即時成交價, 漲跌, 漲跌幅, 開盤價, 最高價, 最低價, 即時成交量, 累計成交量]
    row = body[0]
    index_val = to_float(row[1])
    return make_result(URL, {
        "night_futures": {"index": index_val, "change": to_float(row[2]), "pct_change": to_float(row[3])}
    }, status="ok" if index_val is not None else "error", elapsed_ms=elapsed)


def save_result(result):
    return save_json(result, "cmoney_futures_night")


if __name__ == "__main__":
    run_cli(fetch, save_result)
