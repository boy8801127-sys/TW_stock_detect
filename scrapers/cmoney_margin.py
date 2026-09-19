# scrapers/cmoney_margin.py
"""
Scraper for 大盤融資融券 (CMoney f00012).

CMoney's page itself requires a session-bound `cmkey`, so we drive a headless
browser to the page and intercept the page's own XHR call to
GetMarketMarginTradingInfo rather than re-implementing the key handshake.

Row "TWA00R" (市融資金額) carries the market-wide 融資餘額/增減 in NT$ thousand.
Row "TWA00" (加權指數) carries usage rates plus the 融券餘額/增減 in 張,
since CMoney has no separate aggregate row for short-selling totals.
(CMoney's own 維持率 field stopped updating; 維持率 comes from maintenance_calc.)

Provides:
- fetch() -> standardized dict with meta.status "ok" or "error"
- save_result(result) -> saves latest + daily archive into results/
"""
import time
from .utils import capture_xhr, error_result, make_result, run_cli, save_json, to_float

URL = "https://www.cmoney.tw/finance/f00012.aspx"


def fetch():
    t0 = time.time()
    try:
        rows = capture_xhr(URL, "GetMarketMarginTradingInfo")
    except Exception as e:
        return error_result(URL, f"playwright error: {e}")

    elapsed = int((time.time() - t0) * 1000)
    if not rows:
        return error_result(URL, "no GetMarketMarginTradingInfo response captured", elapsed_ms=elapsed)

    twa00 = next((r for r in rows if r.get("CommKey") == "TWA00"), None)
    twa00r = next((r for r in rows if r.get("CommKey") == "TWA00R"), None)
    if not twa00 or not twa00r:
        res = error_result(URL, "TWA00/TWA00R row missing", elapsed_ms=elapsed)
        res["data"] = {"raw_rows": rows}
        return res

    def billion(v):
        v = to_float(v)
        return None if v is None else v / 100000  # NT$ thousand -> 億

    return make_result(URL, {
        "margin": {
            "balance_billion": billion(twa00r.get("MarginLoanBalance")),
            "change_billion": billion(twa00r.get("MarginLoanFluctuation")),
            "usage_rate": to_float(twa00.get("MarginLoanUsageRate")),
        },
        "short": {
            "balance_lots": to_float(twa00.get("StockLoanBalance")),
            "change_lots": to_float(twa00.get("StockLoanFluctuation")),
            "usage_rate": to_float(twa00.get("StockLoanUsageRate")),
        },
        "date": twa00.get("Date"),
    }, elapsed_ms=elapsed)


def save_result(result):
    return save_json(result, "cmoney_margin")


if __name__ == "__main__":
    run_cli(fetch, save_result)
