# scrapers/taifex_futures.py
import re
import requests
from datetime import datetime
from lxml import html
from .utils import HEADERS, error_result, make_result, run_cli, save_json

URL = "https://www.taifex.com.tw/cht/3/futContractsDateExcel"


def _to_int(s):
    ss = re.sub(r"[^\d\-]", "", str(s or ""))
    try:
        return int(ss)
    except ValueError:
        return None


def fetch():
    """直接用 downloadDate=YYYY/MM/DD 取得今日表格 HTML 並解析三大法人臺股期貨口數"""
    try:
        resp = requests.get(URL, headers=HEADERS, params={"downloadDate": datetime.now().strftime("%Y/%m/%d")}, timeout=15)
        resp.raise_for_status()
        doc = html.fromstring(resp.content)
    except Exception as e:
        return error_result(URL, str(e))

    def extract(xpath_list):
        for xp in xpath_list:
            joined = "".join(str(x).strip() for x in doc.xpath(xp) if str(x).strip())
            if joined:
                return joined
        return None

    raw = {
        "foreign_raw": extract([
            "/html/body/div/div[2]/main/div/div/div[2]/div/table/tbody/tr[3]/td[12]//text()",
            "//table//tr[3]/td[12]//text()"
        ]),
        "inv_raw": extract([
            "/html/body/div/div[2]/main/div/div/div[2]/div/table/tbody/tr[2]/td[12]//text()",
            "//table//tr[2]/td[12]//text()"
        ]),
        "dealer_raw": extract([
            "/html/body/div[1]/div[2]/div[3]/div[2]/div[3]/div/div[4]/div[2]/table/tbody/tr[1]/td[14]//text()",
            "//table//tr[1]/td[14]//text()"
        ]),
    }
    foreign, inv_trust, dealer = (_to_int(raw[k]) for k in ("foreign_raw", "inv_raw", "dealer_raw"))
    return make_result(URL, {
        "foreign": {"current": foreign},
        "dealer": {"current": dealer},
        "inv_trust": {"current": inv_trust},
    }, status="ok" if any(v is not None for v in (foreign, dealer, inv_trust)) else "error", raw=raw)


def save_result(result):
    return save_json(result, "taifex")


if __name__ == "__main__":
    run_cli(fetch, save_result)
