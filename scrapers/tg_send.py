# scrapers/tg_send.py
"""
Simple Telegram sender used by main.py.
Configure via environment variables: TG_BOT_TOKEN, TG_CHAT_ID (both required).
"""
import os
import time
import requests

TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")


def send_message(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        raise RuntimeError("TG_BOT_TOKEN or TG_CHAT_ID not set in environment")
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    last_err = None
    for _ in range(2):
        try:
            r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                return data
            last_err = f"telegram returned not ok: {data}"
        except Exception as e:
            last_err = str(e)
        time.sleep(1)
    raise RuntimeError(f"Failed to send Telegram message: {last_err}")
