# scrapers/taifex_futures.py
import os
import re
import json
import time
from datetime import datetime, timezone, timedelta
import requests
from lxml import html

URL = "https://www.taifex.com.tw/cht/3/futContractsDateExcel"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TWStockBot/1.0)"}
RESULT_DIR = os.path.join(os.path.dirname(__file__), "..", "results")

def _to_int(s):
    if not s:
        return None
    ss = re.sub(r"[^\d\-]", "", str(s))
    if ss in ("", "-", "--"):
        return None
    try:
        return int(ss)
    except:
        return None

def ensure_result_dir():
    os.makedirs(RESULT_DIR, exist_ok=True)

def save_result(result):
    ensure_result_dir()
    latest = os.path.join(RESULT_DIR, "latest_taifex.json")
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive = os.path.join(RESULT_DIR, f"{tag}_taifex.json")
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if not os.path.exists(archive):
        with open(archive, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

def fetch_for_date(dt):
    """直接用 downloadDate=YYYY/MM/DD 取得該日的表格 HTML 並解析口數"""
    date_str = dt.strftime("%Y/%m/%d")
    resp = requests.get(URL, headers=HEADERS, params={"downloadDate": date_str}, timeout=15)
    resp.raise_for_status()
    doc = html.fromstring(resp.content)

    def extract(xpath_list):
        for xp in xpath_list:
            r = doc.xpath(xp)
            if r:
                joined = "".join([str(x).strip() for x in r if str(x).strip()])
                if joined:
                    return joined
        return None

    foreign_raw = extract([
        "/html/body/div/div[2]/main/div/div/div[2]/div/table/tbody/tr[3]/td[12]//text()",
        "//table//tr[3]/td[12]//text()"
    ])
    inv_raw = extract([
        "/html/body/div/div[2]/main/div/div/div[2]/div/table/tbody/tr[2]/td[12]//text()",
        "//table//tr[2]/td[12]//text()"
    ])
    dealer_raw = extract([
        "/html/body/div[1]/div[2]/div[3]/div[2]/div[3]/div/div[4]/div[2]/table/tbody/tr[1]/td[14]//text()",
        "//table//tr[1]/td[14]//text()"
    ])

    return {
        "timestamp": int(time.time()),
        "source": URL,
        "symbol": "臺股期貨",
        "data": {
            "foreign": {"current": _to_int(foreign_raw)},
            "dealer": {"current": _to_int(dealer_raw)},
            "inv_trust": {"current": _to_int(inv_raw)}
        },
        "meta": {
            "status": "ok" if any(v is not None for v in [
                _to_int(foreign_raw), _to_int(dealer_raw), _to_int(inv_raw)
            ]) else "error",
            "elapsed_ms": None,
            "raw": {"foreign_raw": foreign_raw, "dealer_raw": dealer_raw, "inv_raw": inv_raw}
        }
    }

def fetch(target_date=None):
    """
    Compatibility wrapper so main.py can call this scraper.
    If target_date is None, use today (local time).
    Returns the same dict shape as fetch_for_date.
    """
    try:
        if target_date is None:
            from datetime import datetime
            target_date = datetime.now()
        # fetch_for_date already returns the standardized dict
        res = fetch_for_date(target_date)
        return res
    except Exception as e:
        return {"timestamp": int(time.time()), "source": URL, "symbol": "臺股期貨", "data": {}, "meta": {"status": "error", "message": str(e)}}


if __name__ == "__main__":
    # 預設用今天；若要比昨天可把這行改為 datetime.now()-timedelta(days=1)
    target_date = datetime.now() 
    try:
        start = time.time()
        res = fetch_for_date(target_date)
        res["meta"]["elapsed_ms"] = int((time.time() - start) * 1000)
        if res["meta"]["status"] == "ok":
            save_result(res)
    except Exception as e:
        res = {"timestamp": int(time.time()), "source": URL, "symbol": "臺股期貨", "data": {}, "meta": {"status": "error", "message": str(e)}}
    print(json.dumps(res, ensure_ascii=False, indent=2))
