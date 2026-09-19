# scrapers/tsm_adr_compare.py
"""
Compares TSMC's NYSE ADR (TSM) implied TWD price against TWSE 2330's close,
to gauge the overnight premium/discount ahead of the Taiwan market open.

1 ADR represents 5 TSMC ordinary shares.

Provides:
- fetch() -> returns standardized dict with meta.status "ok" or "error"
- save_result(result) -> saves latest and daily archive into results/
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from .utils import error_result, make_result, run_cli, save_json

ADR_RATIO = 5
SOURCE = "yfinance:TSM,2330.TW,TWD=X"


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
        today_local = datetime.now(ZoneInfo(exclude_today_tz)).strftime("%Y-%m-%d")
        hist = hist[hist.index.strftime("%Y-%m-%d") != today_local]
        if hist.empty:
            return None, None

    row = hist.tail(1)
    return float(row["Close"].iloc[0]), row.index[0].strftime("%Y-%m-%d")


def fetch():
    t0 = time.time()
    try:
        adr_close, adr_date = _last_close("TSM")
        twse_close, twse_date = _last_close("2330.TW", exclude_today_tz="Asia/Taipei")
        usdtwd, _ = _last_close("TWD=X")
    except Exception as e:
        return error_result(SOURCE, f"yfinance error: {e}")

    elapsed = int((time.time() - t0) * 1000)
    if adr_close is None or twse_close is None or usdtwd is None:
        return error_result(SOURCE, "missing close price(s)", elapsed_ms=elapsed)

    implied_twd_price = adr_close / ADR_RATIO * usdtwd
    return make_result(SOURCE, {
        "adr_usd": adr_close,
        "adr_date": adr_date,
        "usdtwd": usdtwd,
        "implied_twd_price": implied_twd_price,
        "twse_close": twse_close,
        "twse_date": twse_date,
        "premium_pct": (implied_twd_price - twse_close) / twse_close * 100,
    }, elapsed_ms=elapsed)


def save_result(result):
    return save_json(result, "tsm_adr_compare")


if __name__ == "__main__":
    run_cli(fetch, save_result)
