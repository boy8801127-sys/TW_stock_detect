# trading_day.py
from datetime import datetime
from typing import Tuple


def is_twse_trading_day(date_obj: datetime = None) -> Tuple[bool, str]:
    """
    使用 pandas_market_calendars (XTAI) 判斷交易日。
    回傳 (is_trading_day: bool, reason: str)
    """
    day = (date_obj or datetime.now()).strftime("%Y-%m-%d")
    try:
        import pandas_market_calendars as mcal
        return len(mcal.get_calendar("XTAI").valid_days(start_date=day, end_date=day)) > 0, "pmcal_checked"
    except Exception as e:
        return False, f"pmcal_error:{e}"
