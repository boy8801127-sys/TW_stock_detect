# scrapers/tg_send.py
"""
Simple Telegram sender used by main.py.
Configure via environment variables:
  TG_BOT_TOKEN  - required
  TG_CHAT_ID    - required
Optional:
  TG_RETRY (default 2)
  TG_TIMEOUT (default 10)
"""
import os
import requests
import time
import json

# Read from environment variables
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
TG_RETRY = int(os.getenv("TG_RETRY", "2"))
TG_TIMEOUT = int(os.getenv("TG_TIMEOUT", "10"))
API_BASE = f"https://api.telegram.org/bot{TG_TOKEN}" if TG_TOKEN else None

def send_message(text, parse_mode=None):
    if not TG_TOKEN or not TG_CHAT_ID:
        raise RuntimeError("TG_BOT_TOKEN or TG_CHAT_ID not set in environment")
    url = f"{API_BASE}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    headers = {"Content-Type": "application/json"}
    last_err = None
    for i in range(1, TG_RETRY + 1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=TG_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                last_err = f"telegram returned not ok: {data}"
                time.sleep(1)
                continue
            return data
        except Exception as e:
            last_err = str(e)
            time.sleep(1)
    raise RuntimeError(f"Failed to send Telegram message: {last_err}")

if __name__ == "__main__":
    # Local quick test helper.
    # Recommended: set TG_BOT_TOKEN and TG_CHAT_ID in your environment before running.
    test_text = "測試訊息 - 若要發送請先設定 TG_BOT_TOKEN 與 TG_CHAT_ID 為環境變數"
    try:
        resp = send_message(test_text)
        print("sent:", json.dumps(resp, ensure_ascii=False, indent=2))
    except Exception as e:
        print("send failed:", e)
