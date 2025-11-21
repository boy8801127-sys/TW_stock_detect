# trading_day.py
from datetime import datetime
from typing import Tuple

def is_taiwan_trading_day_pmcal(date_obj: datetime) -> Tuple[bool, str]:
    """
    使用 pandas_market_calendars (XTAI) 判斷交易日。
    回傳 (bool, reason)。
    """
    try:
        import pandas_market_calendars as mcal
    except Exception as e:
        return False, f"pmcal_import_error:{e}"
    try:
        twse = mcal.get_calendar("XTAI")
        s = date_obj.strftime('%Y-%m-%d')
        schedule = twse.valid_days(start_date=s, end_date=s)
        return (len(schedule) > 0), "pmcal_checked"
    except Exception as e:
        return False, f"pmcal_error:{e}"

def is_taiwan_trading_day_yf(date_obj: datetime, sample_ticker="^TWII") -> Tuple[bool, str]:
    """
    備援：使用 yfinance 檢查 sample_ticker 是否有當天日線（period=3d）。
    只要 yfinance 回傳包含當日 index 即視為交易日。
    """
    try:
        import pytz, time, yfinance as yf
    except Exception as e:
        return False, f"yf_import_error:{e}"
    try:
        tz = pytz.timezone("Asia/Taipei")
        today = date_obj.astimezone(tz).date()
        t = yf.Ticker(sample_ticker)
        df = t.history(period="3d", interval="1d", auto_adjust=False, prepost=False)
        if df is None or df.empty:
            return False, "yf_no_data"
        dates = set()
        for idx in df.index:
            try:
                d = idx.tz_convert(tz).date() if getattr(idx, "tz", None) is not None else idx.date()
            except Exception:
                try:
                    d = idx.date()
                except Exception:
                    d = None
            if d is not None:
                dates.add(d)
        if today in dates:
            return True, "yf_today_present"
        latest = max(dates) if dates else None
        if latest == today:
            return True, "yf_latest_is_today"
        return False, "yf_no_today"
    except Exception as e:
        return False, f"yf_error:{e}"

def is_twse_trading_day(date_obj: datetime = None) -> Tuple[bool, str]:
    """
    先用 pandas_market_calendars 判斷，失敗時以 yfinance 備援。
    回傳 (is_trading_day: bool, reason: str)
    """
    if date_obj is None:
        date_obj = datetime.now()
    # 1) try pmcal
    ok, reason = is_taiwan_trading_day_pmcal(date_obj)
    if reason.startswith("pmcal_checked"):
        return ok, reason
    # 2) try yfinance fallback
    ok2, reason2 = is_taiwan_trading_day_yf(date_obj)
    if ok2:
        return True, reason2
    # if pmcal import failed but pmcal error wasn't import, return pmcal reason only if it was explicit
    # prefer pmcal error message if pmcal was available but errored
    return False, f"fallback:{reason}|{reason2}"
