# main.py
"""
Run scrapers in a controlled order, aggregate results, build a Chinese notification,
and optionally send it via Telegram.
"""
import os
import sys
import time
import json
import logging
import importlib
import traceback
from datetime import datetime, timezone

# Ensure project root is on sys.path so "scrapers" package can be imported reliably
PROJECT_ROOT = os.path.dirname(__file__)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Config via environment variables
ORDERED_SCRAPERS = os.getenv("ORDERED_SCRAPERS", "").strip()  # comma-separated module names (without .py)
RETRY = int(os.getenv("RETRY", "1"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
AUTO_SEND = os.getenv("AUTO_SEND", "false").lower() in ("1", "true", "yes")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")
SKIP_TRADING_DAY_CHECK = os.getenv("SKIP_TRADING_DAY_CHECK", "false").lower() in ("1", "true", "yes")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
SUMMARY_PATH = os.path.join(RESULTS_DIR, "latest_summary.json")

# Scrapers run in this order (module filenames under scrapers/); maintenance_calc must follow cmoney_margin
DEFAULT_ORDER = [
    "twse_margin_api",
    "twse_mi_index",
    "cmoney_futures_night",
    "VIXTWN",
    "taifex_futures",
    "cmoney_margin",
    "maintenance_calc",
    "cnn_fear_greed",
    "tsm_adr_compare"
]

os.makedirs(RESULTS_DIR, exist_ok=True)

# stdout (not stderr): Cloud Run tags stderr lines as ERROR severity
logging.basicConfig(stream=sys.stdout, level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s [%(levelname)s] %(message)s")


def log(msg, level="INFO"):
    logging.log(getattr(logging, level.upper()), msg)


def _check_trading_day_or_exit():
    if SKIP_TRADING_DAY_CHECK:
        log("SKIP_TRADING_DAY_CHECK enabled; skipping trading day check")
        return
    try:
        from scrapers.trading_day import is_twse_trading_day
        is_open, reason = is_twse_trading_day()
    except Exception as e:
        log(f"Trading day check failed with exception: {e}. Proceeding anyway.", "WARNING")
        return
    if not is_open:
        log(f"Not a trading day or could not confirm trading day ({reason}). Aborting pipeline.")
        sys.exit(0)  # normal non-run on non-trading day
    log(f"Trading day check passed ({reason}). Proceeding.")


def resolve_run_list():
    names = [n.strip() for n in ORDERED_SCRAPERS.split(",") if n.strip()] or DEFAULT_ORDER
    log(f"Run list: {names}")
    return names


def call_fetch(module):
    try:
        res = module.fetch()
        return res.get("meta", {}).get("status") == "ok", res
    except Exception as e:
        log(f"Fetch error in {getattr(module, '__name__', '<unknown>')}: {e}\n{traceback.format_exc()}", "ERROR")
        return False, {
            "timestamp": int(time.time()),
            "source": getattr(module, "__file__", "<unknown>"),
            "data": {},
            "meta": {"status": "error", "message": str(e)}
        }


def run_single_scraper(name):
    """Import and run a single scraper with RETRY; returns (name, ok, result)"""
    try:
        mod = importlib.import_module(f"scrapers.{name}")
    except Exception:
        log(f"Import failed for scrapers.{name}:\n{traceback.format_exc()}", "ERROR")
        return name, False, {"timestamp": int(time.time()), "source": f"scrapers.{name}", "data": {}, "meta": {"status": "error", "message": "import_failed"}}

    last_res = None
    for attempt in range(1, RETRY + 1):
        log(f"Running {name} attempt {attempt}/{RETRY}")
        ok, res = call_fetch(mod)
        last_res = res
        if ok:
            save_fn = getattr(mod, "save_result", None)
            if save_fn:
                try:
                    save_fn(res)
                except Exception:
                    log(f"{name}.save_result failed: {traceback.format_exc()}", "WARNING")
            return name, True, res
        log(f"{name} attempt {attempt} failed: {res.get('meta', {}).get('message')}", "WARNING")
    return name, False, last_res


def aggregate_results(results):
    summary = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "scrapers": {},
        "overall_status": "ok"
    }
    for name, ok, res in results:
        summary["scrapers"][name] = {
            "ok": bool(ok),
            "source": res.get("source"),
            "meta": res.get("meta", {}),
            "data": res.get("data", {})
        }
        if not ok:
            summary["overall_status"] = "partial_error"
    return summary


def save_summary(summary):
    tmp = SUMMARY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SUMMARY_PATH)
    log(f"Saved summary -> {SUMMARY_PATH}")


def build_and_optionally_send(summary):
    ai_text = None
    try:
        from scrapers.ai_summary import generate_summary
        ai_text = generate_summary(summary)
    except Exception:
        log(f"ai_summary.generate_summary failed: {traceback.format_exc()}", "WARNING")

    try:
        from scrapers.compose_notification import build_message
        message = build_message(summary, ai_text=ai_text)
    except Exception:
        log(f"compose_notification.build_message error: {traceback.format_exc()}", "ERROR")
        return False, "compose_build_failed"

    log("Notification message preview:\n" + message)
    print("\n" + message + "\n")

    if not AUTO_SEND:
        log("AUTO_SEND disabled; not sending message")
        return True, "dry_not_sent_auto_disabled"
    if DRY_RUN:
        log("DRY_RUN enabled; not sending message")
        return True, "dry_not_sent_dry_run"

    try:
        from scrapers.tg_send import send_message
        send_message(message)
        log("Telegram message sent")
        return True, "sent"
    except Exception:
        log(f"TG send failed: {traceback.format_exc()}", "ERROR")
        return False, "tg_send_failed"


def main():
    # check trading day first (may exit)
    _check_trading_day_or_exit()

    try:
        from scrapers.gcs_sync import download_results
        download_results()
    except Exception:
        log(f"gcs_sync.download_results failed: {traceback.format_exc()}", "WARNING")

    results = [run_single_scraper(name) for name in resolve_run_list()]
    summary = aggregate_results(results)
    save_summary(summary)

    sent_ok, reason = build_and_optionally_send(summary)
    if not sent_ok:
        log(f"Notification/send step issue: {reason}", "WARNING")

    try:
        from scrapers.gcs_sync import upload_results
        upload_results()
    except Exception:
        log(f"gcs_sync.upload_results failed: {traceback.format_exc()}", "WARNING")

    ok_count = sum(1 for _, ok, _ in results if ok)
    log(f"Scrapers done: {ok_count}/{len(results)} succeeded")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["overall_status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
