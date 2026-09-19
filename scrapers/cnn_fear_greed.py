# scrapers/cnn_fear_greed.py
"""
Scraper for CNN Fear & Greed Index (US stock market sentiment).

Provides:
- fetch() -> returns standardized dict with meta.status "ok" or "error"
- save_result(result) -> saves latest and daily archive into results/
"""
import time
import requests
from .utils import USER_AGENT, error_result, make_result, run_cli, safe_parse_json, save_json, to_float

URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
}


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
        return error_result(URL, f"request error: {e}")

    elapsed = int((time.time() - t0) * 1000)
    payload = safe_parse_json(r)
    if payload is None:
        return error_result(URL, "invalid or non-json response", elapsed_ms=elapsed)

    fng = payload.get("fear_and_greed") or {}
    score = to_float(fng.get("score"))
    return make_result(URL, {"score": score, "rating": _classify(score), "api_rating": fng.get("rating")},
                       status="ok" if score is not None else "error", elapsed_ms=elapsed)


def save_result(result):
    return save_json(result, "cnn_fear_greed")


if __name__ == "__main__":
    run_cli(fetch, save_result)
