# scrapers/utils.py
import requests
from typing import Optional

def safe_parse_json(response: requests.Response, *, snapshot_chars: int = 1000) -> Optional[dict]:
    """
    嘗試安全解析 response.json()：
    - 若 status != 200，記錄 status 與 body 前 snapshot_chars 字元，回傳 None
    - 若 content-type 非 JSON，嘗試解析，但若失敗仍回傳 None 並輸出 snippet
    - 捕捉 JSON parse 例外並印出 body snippet
    """
    try:
        status = response.status_code
        ct = response.headers.get("Content-Type", "")
        if status != 200:
            print(f"[safe_parse_json] non-200 status: {status}; content-type: {ct}")
            body = response.text or ""
            print(f"[safe_parse_json] body (first {snapshot_chars} chars): {body[:snapshot_chars]}")
            return None
        # 若 header 不是 JSON，仍嘗試解析（有些 API 忘了 Content-Type）
        if "application/json" not in ct and "text/json" not in ct:
            try:
                return response.json()
            except Exception as e:
                print(f"[safe_parse_json] unexpected content-type: {ct}; json parse failed: {e}")
                print(f"[safe_parse_json] body (first {snapshot_chars} chars): {response.text[:snapshot_chars]}")
                return None
        # content-type 看起來是 JSON
        try:
            return response.json()
        except Exception as e:
            print(f"[safe_parse_json] response.json() failed: {e}; body (first {snapshot_chars} chars): {response.text[:snapshot_chars]}")
            return None
    except Exception as e:
        print(f"[safe_parse_json] unexpected outer error: {e}")
        return None
