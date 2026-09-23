# scrapers/utils.py
"""各爬蟲共用的小工具：數值轉換、結果字典、存檔、JSON 解析、瀏覽器 XHR 攔截、命令列執行。"""
import json
import os
import shutil
import time
from datetime import datetime, timezone

RESULT_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
USER_AGENT = "Mozilla/5.0 (compatible; TWStockBot/1.0)"
HEADERS = {"User-Agent": USER_AGENT}


def to_float(s):
    """'1,234.5' -> 1234.5；空值、NaN 或無法解析回傳 None。

    float("nan") 不會拋 ValueError，若不擋下，上游 API 回傳的 NaN
    （json.loads 預設會接受非標準的 NaN token）會被當成合法數字，
    一路帶進通知訊息顯示成「nan」。
    """
    try:
        v = None if s in (None, "") else float(str(s).replace(",", "").strip())
    except ValueError:
        return None
    return None if v is not None and v != v else v


def to_int(s):
    f = to_float(s)
    return None if f is None else int(f)


def make_result(source, data=None, status="ok", **meta):
    """各爬蟲統一的回傳格式（見 CLAUDE.md 的 Scraper contract）。"""
    return {"timestamp": int(time.time()), "source": source, "data": data or {}, "meta": {"status": status, **meta}}


def error_result(source, message, **meta):
    return make_result(source, status="error", message=message, **meta)


def save_json(result, prefix):
    """寫 latest_<prefix>.json（原子寫入），當日尚無存檔時另存 <YYYY-MM-DD>_<prefix>.json。

    GCS 只同步日期存檔，"與前一交易日比較"與快取備援都靠它。
    """
    os.makedirs(RESULT_DIR, exist_ok=True)
    latest = os.path.join(RESULT_DIR, f"latest_{prefix}.json")
    archive = os.path.join(RESULT_DIR, f"{datetime.now(timezone.utc):%Y-%m-%d}_{prefix}.json")
    tmp = latest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, latest)
    if not os.path.exists(archive):
        shutil.copyfile(latest, archive)
    return latest


def safe_parse_json(response):
    """response.json()；解析失敗時印出內容前段供除錯並回傳 None。"""
    try:
        return response.json()
    except ValueError as e:
        print(f"[safe_parse_json] status={response.status_code} content-type={response.headers.get('Content-Type', '')}; "
              f"json parse failed: {e}; body: {response.text[:1000]}")
        return None


def capture_xhr(url, url_part, accept=lambda body: True, timeout_ms=45000):
    """用無頭瀏覽器開啟 url，回傳網址含 url_part 且通過 accept(body) 的最後一個 XHR 回應 JSON（沒有則 None）。"""
    from playwright.sync_api import sync_playwright

    captured = {}

    def on_response(resp):
        try:
            if url_part in resp.url:
                body = resp.json()
                if accept(body):
                    captured["body"] = body
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=USER_AGENT).new_page()
        page.on("response", on_response)
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1000)
        browser.close()

    return captured.get("body")


def run_cli(fetch, save=None):
    """python -m scrapers.<name>：執行 fetch()，成功時存檔，並印出結果 JSON。"""
    res = fetch()
    if save and res["meta"].get("status") == "ok":
        save(res)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    assert to_float("1,234.5") == 1234.5
    assert to_float("") is None
    assert to_float(None) is None
    assert to_float("N/A") is None
    assert to_float(float("nan")) is None
    assert to_float("nan") is None
    assert to_int("1,234.5") == 1234
    assert to_int(float("nan")) is None
    print("utils self-check ok")
