# scrapers/cnn_fear_greed.py
"""
Scraper for CNN Fear & Greed Index (US stock market sentiment).

Provides:
- fetch() -> returns standardized dict with meta.status "ok" or "error"
- save_result(result) -> saves latest and daily archive into results/
"""
import os
import time
import json
from datetime import datetime, timezone
import requests

from .utils import safe_parse_json

URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
RESULT_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
}


def ensure_result_dir():
    os.makedirs(RESULT_DIR, exist_ok=True)


def _classify(score):
    if score is None:
        return None
    if score < 25:
        return "極度恐懼"
    if score < 45:
        return "恐懼"
    if score < 56:
        return "中性"
    if score < 76:
        return "貪婪"
    return "極度貪婪"


def fetch():
    t0 = time.time()
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15)
    except Exception as e:
        return {
            "timestamp": int(time.time()),
            "source": URL,
            "data": {},
            "meta": {"status": "error", "message": f"request error: {e}"},
        }

    elapsed = int((time.time() - t0) * 1000)
    payload = safe_parse_json(r, snapshot_chars=1000)
    if payload is None:
        return {
            "timestamp": int(time.time()),
            "source": URL,
            "data": {},
            "meta": {"status": "error", "message": "invalid or non-json response", "elapsed_ms": elapsed},
        }

    fng = payload.get("fear_and_greed") or {}
    score = fng.get("score")
    api_rating = fng.get("rating")
    try:
        score = float(score) if score is not None else None
    except Exception:
        score = None

    rating = _classify(score)

    result = {
        "timestamp": int(time.time()),
        "source": URL,
        "data": {"score": score, "rating": rating, "api_rating": api_rating},
        "meta": {"status": "ok" if score is not None else "error", "elapsed_ms": elapsed},
    }
    return result


def save_result(result, prefix="cnn_fear_greed"):
    ensure_result_dir()
    latest = os.path.join(RESULT_DIR, f"latest_{prefix}.json")
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive = os.path.join(RESULT_DIR, f"{tag}_{prefix}.json")
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
