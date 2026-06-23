# scrapers/cmoney_margin.py
"""
Scraper for 大盤融資融券 (CMoney f00012).

CMoney's page itself requires a session-bound `cmkey`, so we drive a headless
browser to the page and intercept the page's own XHR call to
GetMarketMarginTradingInfo rather than re-implementing the key handshake.

Row "TWA00R" (市融資金額) carries the market-wide 融資餘額/增減 in NT$ thousand.
Row "TWA00" (加權指數) carries usage/maintenance rates plus the 融券餘額/增減 in 張,
since CMoney has no separate aggregate row for short-selling totals.

Provides:
- fetch() -> standardized dict with meta.status "ok" or "error"
- save_result(result) -> saves latest + daily archive into results/
"""
import os
import json
import time
from datetime import datetime, timezone

URL = "https://www.cmoney.tw/finance/f00012.aspx"
RESULT_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
USER_AGENT = "Mozilla/5.0 (compatible; TWStockBot/1.0)"


def ensure_result_dir():
    os.makedirs(RESULT_DIR, exist_ok=True)


def _to_float(s):
    try:
        if s is None or s == "":
            return None
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None


def _fetch_rows_via_playwright(timeout_ms=45000):
    from playwright.sync_api import sync_playwright

    captured = {}

    def on_response(resp):
        try:
            if "GetMarketMarginTradingInfo" in resp.url:
                captured["rows"] = resp.json()
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT)
        page = ctx.new_page()
        page.on("response", on_response)
        page.goto(URL, timeout=timeout_ms, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1000)
        browser.close()

    return captured.get("rows")


def fetch():
    t0 = time.time()
    try:
        rows = _fetch_rows_via_playwright()
    except Exception as e:
        return {
            "timestamp": int(time.time()),
            "source": URL,
            "data": {},
            "meta": {"status": "error", "message": f"playwright error: {e}"},
        }

    elapsed = int((time.time() - t0) * 1000)
    if not rows:
        return {
            "timestamp": int(time.time()),
            "source": URL,
            "data": {},
            "meta": {"status": "error", "message": "no GetMarketMarginTradingInfo response captured", "elapsed_ms": elapsed},
        }

    twa00 = next((r for r in rows if r.get("CommKey") == "TWA00"), None)
    twa00r = next((r for r in rows if r.get("CommKey") == "TWA00R"), None)

    if not twa00 or not twa00r:
        return {
            "timestamp": int(time.time()),
            "source": URL,
            "data": {"raw_rows": rows},
            "meta": {"status": "error", "message": "TWA00/TWA00R row missing", "elapsed_ms": elapsed},
        }

    margin_balance_thousand = _to_float(twa00r.get("MarginLoanBalance"))
    margin_change_thousand = _to_float(twa00r.get("MarginLoanFluctuation"))

    data = {
        "margin": {
            "balance_billion": margin_balance_thousand / 100000 if margin_balance_thousand is not None else None,
            "change_billion": margin_change_thousand / 100000 if margin_change_thousand is not None else None,
            "usage_rate": _to_float(twa00.get("MarginLoanUsageRate")),
            "maintenance_rate": _to_float(twa00.get("MarginLoanMaintenanceRate")),
        },
        "short": {
            "balance_lots": _to_float(twa00.get("StockLoanBalance")),
            "change_lots": _to_float(twa00.get("StockLoanFluctuation")),
            "usage_rate": _to_float(twa00.get("StockLoanUsageRate")),
        },
        "date": twa00.get("Date"),
    }

    return {
        "timestamp": int(time.time()),
        "source": URL,
        "data": data,
        "meta": {"status": "ok", "elapsed_ms": elapsed},
    }


def save_result(result, prefix="cmoney_margin"):
    ensure_result_dir()
    latest = os.path.join(RESULT_DIR, f"latest_{prefix}.json")
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive = os.path.join(RESULT_DIR, f"{tag}_{prefix}.json")
    tmp = latest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, latest)
    if not os.path.exists(archive):
        with open(archive, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    return latest


if __name__ == "__main__":
    res = fetch()
    if res.get("meta", {}).get("status") == "ok":
        save_result(res)
    print(json.dumps(res, ensure_ascii=False, indent=2))
