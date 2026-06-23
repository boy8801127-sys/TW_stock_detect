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
import os
import json
import time
from datetime import datetime, timezone

URL = "https://www.cmoney.tw/forum/futures/TXF1?s=p"
RESULT_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
USER_AGENT = "Mozilla/5.0 (compatible; TWStockBot/1.0)"
EXPECTED_COLUMNS = 9  # CommKey, 即時成交價, 漲跌, 漲跌幅, 開盤價, 最高價, 最低價, 即時成交量, 累計成交量


def ensure_result_dir():
    os.makedirs(RESULT_DIR, exist_ok=True)


def _to_float(s):
    try:
        if s is None or s == "":
            return None
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None


def _fetch_row_via_playwright(timeout_ms=45000):
    from playwright.sync_api import sync_playwright

    captured = {}

    def on_response(resp):
        try:
            if "FuturesNightCalculation" in resp.url:
                body = resp.json()
                if isinstance(body, list) and body:
                    row0 = body[0]
                    if isinstance(row0, list) and len(row0) == EXPECTED_COLUMNS:
                        captured["row"] = row0
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

    return captured.get("row")


def fetch():
    t0 = time.time()
    try:
        row = _fetch_row_via_playwright()
    except Exception as e:
        return {
            "timestamp": int(time.time()),
            "source": URL,
            "data": {},
            "meta": {"status": "error", "message": f"playwright error: {e}"},
        }

    elapsed = int((time.time() - t0) * 1000)
    if not row:
        return {
            "timestamp": int(time.time()),
            "source": URL,
            "data": {},
            "meta": {"status": "error", "message": "no FuturesNightCalculation response captured", "elapsed_ms": elapsed},
        }

    # row: [CommKey, 即時成交價, 漲跌, 漲跌幅, 開盤價, 最高價, 最低價, 即時成交量, 累計成交量]
    index_val = _to_float(row[1])
    data = {
        "night_futures": {
            "index": index_val,
            "change": _to_float(row[2]),
            "pct_change": _to_float(row[3]),
        }
    }

    return {
        "timestamp": int(time.time()),
        "source": URL,
        "data": data,
        "meta": {"status": "ok" if index_val is not None else "error", "elapsed_ms": elapsed},
    }


def save_result(result, prefix="cmoney_futures_night"):
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
