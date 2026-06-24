# scrapers/tsm_adr_compare.py
"""
Compares TSMC's NYSE ADR (TSM) implied TWD price against TWSE 2330's close,
to gauge the overnight premium/discount ahead of the Taiwan market open.

1 ADR represents 5 TSMC ordinary shares.

Provides:
- fetch() -> returns standardized dict with meta.status "ok" or "error"
- save_result(result) -> saves latest and daily archive into results/
"""
import os
import time
import json
from datetime import datetime, timezone

ADR_RATIO = 5
RESULT_DIR = os.path.join(os.path.dirname(__file__), "..", "results")


def ensure_result_dir():
    os.makedirs(RESULT_DIR, exist_ok=True)


def _last_close(ticker, exclude_today_tz=None):
    """Returns (close, date_str) for the most recent completed session.

    If exclude_today_tz is set (e.g. "Asia/Taipei"), drops the latest row when
    its date matches "today" in that timezone, so an in-progress session
    doesn't get used as a settled close.
    """
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period="5d")
    if hist is None or hist.empty:
        return None, None

    if exclude_today_tz:
        import pytz

        today_local = datetime.now(pytz.timezone(exclude_today_tz)).strftime("%Y-%m-%d")
        hist = hist[hist.index.strftime("%Y-%m-%d") != today_local]
        if hist.empty:
            return None, None

    row = hist.tail(1)
    close = float(row["Close"].iloc[0])
    date = row.index[0].strftime("%Y-%m-%d")
    return close, date


def fetch():
    t0 = time.time()
    try:
        adr_close, adr_date = _last_close("TSM")
        twse_close, twse_date = _last_close("2330.TW", exclude_today_tz="Asia/Taipei")
        usdtwd, fx_date = _last_close("TWD=X")
    except Exception as e:
        return {
            "timestamp": int(time.time()),
            "source": "yfinance:TSM,2330.TW,TWD=X",
            "data": {},
            "meta": {"status": "error", "message": f"yfinance error: {e}"},
        }

    elapsed = int((time.time() - t0) * 1000)

    if adr_close is None or twse_close is None or usdtwd is None:
        return {
            "timestamp": int(time.time()),
            "source": "yfinance:TSM,2330.TW,TWD=X",
            "data": {},
            "meta": {"status": "error", "message": "missing close price(s)", "elapsed_ms": elapsed},
        }

    implied_twd_price = adr_close / ADR_RATIO * usdtwd
    premium_pct = (implied_twd_price - twse_close) / twse_close * 100

    result = {
        "timestamp": int(time.time()),
        "source": "yfinance:TSM,2330.TW,TWD=X",
        "data": {
            "adr_usd": adr_close,
            "adr_date": adr_date,
            "usdtwd": usdtwd,
            "implied_twd_price": implied_twd_price,
            "twse_close": twse_close,
            "twse_date": twse_date,
            "premium_pct": premium_pct,
        },
        "meta": {"status": "ok", "elapsed_ms": elapsed},
    }
    return result


def save_result(result, prefix="tsm_adr_compare"):
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
