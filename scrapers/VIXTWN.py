# scrapers/VIXTWN.py
"""
Scraper for 臺指選擇權波動率指數 (TAIWAN VIX).

Provides:
- fetch() -> returns standardized dict with meta.status "ok" or "error"
- save_result(result) -> saves latest and daily archive into results/
"""
import os
import time
import json
from datetime import datetime, timezone

URL = "https://mis.taifex.com.tw/futures/api/getQuoteListVIX"
RESULT_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TWStockBot/1.0)",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://mis.taifex.com.tw",
    "Origin": "https://mis.taifex.com.tw",
    "Content-Type": "application/json"
}


def ensure_result_dir():
    os.makedirs(RESULT_DIR, exist_ok=True)


def _to_float(s):
    try:
        if s is None:
            return None
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None


def _requests_post_fetch(timeout=10):
    import requests
    from .utils import safe_parse_json

    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        resp = s.post(URL, json={}, timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        # request-level error (network, timeout, non-2xx)
        return {"ok": False, "error": f"request error: {e}", "response": getattr(e, "response", None)}

    # Try to parse JSON safely
    payload = safe_parse_json(resp, snapshot_chars=2000)
    if payload is None:
        # save raw for debugging
        try:
            ensure_result_dir()
            dump = os.path.join(RESULT_DIR, f"vix_raw_{int(time.time())}.txt")
            with open(dump, "w", encoding="utf-8") as f:
                f.write(resp.text)
        except Exception as e:
            # if saving fails, log to stdout but continue returning structured error
            print(f"[VIXTWN._requests_post_fetch] failed to save raw response: {e}")
            dump = None
        return {"ok": False, "error": "invalid or non-json response from VIX endpoint", "saved_raw": dump, "status_code": resp.status_code}

    # parse CLastPrice safely
    try:
        q = payload.get("RtData", {}).get("QuoteList", [])
        item = q[0] if isinstance(q, list) and q else None
        last_raw = item.get("CLastPrice") if isinstance(item, dict) else None
    except Exception:
        last_raw = None

    return {"ok": True, "payload": payload, "CLastPrice": last_raw, "status_code": resp.status_code}


def _playwright_fetch(timeout_ms=15000):
    # Optional fallback: use Playwright if requests fails or server requires browser context.
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return {"ok": False, "error": f"playwright not available: {e}"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=HEADERS["User-Agent"])
            page = ctx.new_page()

            captured = {"payload": None, "status": None, "ctype": None, "url": None}

            def on_response(resp):
                try:
                    if "/futures/api/getQuoteListVIX" in resp.url:
                        captured["status"] = resp.status
                        captured["ctype"] = resp.headers.get("content-type")
                        captured["url"] = resp.url
                        try:
                            captured["payload"] = resp.json()
                        except Exception:
                            captured["payload"] = resp.text()
                except Exception:
                    pass

            page.on("response", on_response)
            # load domain to establish context
            page.goto("https://mis.taifex.com.tw", timeout=20000)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(500)

            # attempt an explicit POST via page.request (keeps same context)
            try:
                res = page.request.post(URL, data="{}", headers={
                    "Accept": HEADERS["Accept"],
                    "Content-Type": "application/json",
                    "Origin": HEADERS["Origin"],
                    "Referer": HEADERS["Referer"],
                }, timeout=timeout_ms)
                status = res.status
                try:
                    payload = res.json()
                except Exception:
                    payload = res.text()
                browser.close()
                # parse
                if isinstance(payload, dict):
                    q = payload.get("RtData", {}).get("QuoteList", [])
                    item = q[0] if isinstance(q, list) and q else None
                    last_raw = item.get("CLastPrice") if isinstance(item, dict) else None
                else:
                    last_raw = None
                return {"ok": True, "payload": payload, "CLastPrice": last_raw, "status_code": status}
            except Exception:
                # maybe response was captured by on_response instead
                browser.close()
                payload = captured.get("payload")
                if payload:
                    try:
                        q = payload.get("RtData", {}).get("QuoteList", [])
                        item = q[0] if isinstance(q, list) and q else None
                        last_raw = item.get("CLastPrice") if isinstance(item, dict) else None
                    except Exception:
                        last_raw = None
                    return {"ok": True, "payload": payload, "CLastPrice": last_raw, "status_code": captured.get("status")}
                return {"ok": False, "error": "playwright request failed and no captured response"}
    except Exception as e:
        return {"ok": False, "error": f"playwright error: {e}"}


def fetch():
    """
    Standardized fetch() used by main.py.
    Returns:
    {
      "timestamp": <int>,
      "source": <url>,
      "data": {"vix": {"raw": <str>, "value": <float>}},
      "meta": {"status": "ok" or "error", "elapsed_ms": <int>, ...}
    }
    """
    t0 = time.time()
    # 1) try direct requests POST
    r = _requests_post_fetch(timeout=10)
    elapsed = int((time.time() - t0) * 1000)
    if r.get("ok"):
        last_raw = r.get("CLastPrice")
        last_val = _to_float(last_raw)
        result = {
            "timestamp": int(time.time()),
            "source": URL,
            "data": {"vix": {"raw": last_raw, "value": last_val}},
            "meta": {"status": "ok" if last_val is not None and last_val > 0 else "error", "elapsed_ms": elapsed}
        }
        return result

    # 2) fallback: try Playwright
    pw = _playwright_fetch(timeout_ms=15000)
    if pw.get("ok"):
        last_raw = pw.get("CLastPrice")
        last_val = _to_float(last_raw)
        result = {
            "timestamp": int(time.time()),
            "source": URL,
            "data": {"vix": {"raw": last_raw, "value": last_val}},
            "meta": {"status": "ok" if last_val is not None and last_val > 0 else "error", "elapsed_ms": elapsed, "note": "fetched_via_playwright"}
        }
        return result

    # 3) both methods failed: return helpful error
    err_msg = r.get("error") or pw.get("error") or "unknown error"
    meta = {"status": "error", "message": err_msg, "elapsed_ms": elapsed}
    if r.get("saved_raw"):
        meta["saved_raw"] = r.get("saved_raw")
    return {"timestamp": int(time.time()), "source": URL, "data": {}, "meta": meta}


def save_result(result, prefix="taifex_vix"):
    ensure_result_dir()
    latest = os.path.join(RESULT_DIR, f"latest_{prefix}.json")
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive = os.path.join(RESULT_DIR, f"{tag}_{prefix}.json")
    # atomic write
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
