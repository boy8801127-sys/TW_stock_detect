# main.py
"""
Run scrapers in a controlled order, aggregate results, build a Chinese notification,
and optionally send it via Telegram.
"""
import os
import sys
import time
import json
import importlib
import traceback
import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from importlib.util import spec_from_file_location, module_from_spec

# Ensure project root is on sys.path so "scrapers" package can be imported reliably
PROJECT_ROOT = os.path.dirname(__file__)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Config via environment variables
ORDERED_SCRAPERS = os.getenv("ORDERED_SCRAPERS", "").strip()  # comma-separated module names (without .py)
PARALLEL = os.getenv("PARALLEL", "false").lower() in ("1", "true", "yes")
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
RETRY = int(os.getenv("RETRY", "1"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
AUTO_SEND = os.getenv("AUTO_SEND", "false").lower() in ("1", "true", "yes")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")
TG_MODULE = os.getenv("TG_MODULE", "scrapers.tg_send")  # module path to use for sending
SCRAPERS_DIR = os.path.join(os.path.dirname(__file__), "scrapers")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
SUMMARY_PATH = os.path.join(RESULTS_DIR, "latest_summary.json")

# Trading day check config
SKIP_TRADING_DAY_CHECK = os.getenv("SKIP_TRADING_DAY_CHECK", "false").lower() in ("1", "true", "yes")

# Default ordered list you requested (module filenames under scrapers/)
DEFAULT_ORDER = [
    "twse_margin_api",
    "twse_mi_index",
    "VIXTWN",
    "taifex_futures",
    "maintenance_calc"
]

os.makedirs(RESULTS_DIR, exist_ok=True)


def log(msg, level="INFO"):
    level = level.upper()
    order = ["DEBUG", "INFO", "WARNING", "ERROR"]
    # safe fallback if LOG_LEVEL invalid
    current_level = LOG_LEVEL if LOG_LEVEL in order else "INFO"
    try:
        if order.index(level) < order.index(current_level):
            return
    except Exception:
        # if anything odd, still print
        pass
    ts = datetime.now(timezone.utc).astimezone().isoformat()
    print(f"{ts} [{level}] {msg}", flush=True)


def _check_trading_day_or_exit():
    if SKIP_TRADING_DAY_CHECK:
        log("SKIP_TRADING_DAY_CHECK enabled; skipping trading day check", "INFO")
        return
    try:
        td_mod = importlib.import_module("scrapers.trading_day")
        is_open, reason = getattr(td_mod, "is_twse_trading_day")(None)
        if not is_open:
            log(f"Not a trading day or could not confirm trading day ({reason}). Aborting pipeline.", "INFO")
            # Exit quietly with code 0 to indicate normal non-run on non-trading day.
            sys.exit(0)
        else:
            log(f"Trading day check passed ({reason}). Proceeding.", "INFO")
    except Exception as e:
        log(f"Trading day check failed with exception: {e}. Proceeding anyway.", "WARNING")
        # If trading day check raises, we proceed; change behavior if you prefer to abort.


def resolve_run_list():
    # If ORDERED_SCRAPERS provided, use that (split and strip)
    if ORDERED_SCRAPERS:
        names = [n.strip() for n in ORDERED_SCRAPERS.split(",") if n.strip()]
        log(f"Using ORDERED_SCRAPERS from env: {names}", "INFO")
        return names
    # Otherwise use DEFAULT_ORDER plus any other auto-discovered scrapers (that are present as files) appended
    names = list(DEFAULT_ORDER)
    # auto-discover additional scrapers in scrapers/ dir by filename only (avoid importing at discovery time)
    try:
        for fn in sorted(os.listdir(SCRAPERS_DIR)):
            if not fn.endswith(".py"):
                continue
            name = fn[:-3]
            if name in names or name.startswith("__"):
                continue
            # Append by filename; actual import occurs later in run_single_scraper
            names.append(name)
    except Exception:
        # if scrapers dir doesn't exist, just return default list
        log(f"Failed to list scrapers dir {SCRAPERS_DIR}", "WARNING")
    log(f"Resolved run list: {names}", "INFO")
    return names


def import_module(name):
    """
    Import a scraper module under package scrapers.<name>.
    Fallback: if normal import fails (commonly due to running outside package context),
    try loading the file scrapers/<name>.py as a module by path while ensuring a minimal 'scrapers' package exists.
    """
    full = f"scrapers.{name}"
    try:
        if full in sys.modules:
            return sys.modules[full]
        return importlib.import_module(full)
    except Exception:
        log(f"Primary import failed for {full}:\n{traceback.format_exc()}", "WARNING")
        # Fallback: import by file path but ensure a minimal 'scrapers' package exists
        try:
            # ensure scrapers package exists and has proper __path__
            if "scrapers" not in sys.modules:
                pkg = types.ModuleType("scrapers")
                pkg.__path__ = [SCRAPERS_DIR]
                sys.modules["scrapers"] = pkg

            file_path = os.path.join(SCRAPERS_DIR, f"{name}.py")
            if not os.path.isfile(file_path):
                raise FileNotFoundError(f"Fallback file not found: {file_path}")

            spec = spec_from_file_location(full, file_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create spec for {file_path}")

            module = module_from_spec(spec)
            # register module under package name to help relative imports inside the file
            sys.modules[full] = module
            spec.loader.exec_module(module)
            log(f"Imported {full} via file fallback {file_path}", "INFO")
            return module
        except Exception:
            log(f"Fallback file import failed for scrapers.{name}:\n{traceback.format_exc()}", "ERROR")
            raise


def call_fetch(module):
    try:
        fetch_fn = getattr(module, "fetch", None)
        if not fetch_fn or not callable(fetch_fn):
            raise RuntimeError("module has no fetch()")
        res = fetch_fn()
        ok = res.get("meta", {}).get("status") == "ok"
        return ok, res
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
        mod = import_module(name)
    except Exception:
        return name, False, {"timestamp": int(time.time()), "source": f"scrapers.{name}", "data": {}, "meta": {"status": "error", "message": "import_failed"}}

    # check fetch presence
    if not hasattr(mod, "fetch") or not callable(getattr(mod, "fetch")):
        return name, False, {"timestamp": int(time.time()), "source": getattr(mod, "__file__", f"scrapers/{name}.py"), "data": {}, "meta": {"status": "error", "message": "no fetch()"}}

    last_res = None
    for attempt in range(1, RETRY + 1):
        log(f"Running {name} attempt {attempt}/{RETRY}", "INFO")
        ok, res = call_fetch(mod)
        last_res = res
        if ok:
            # call save_result if available
            save_fn = getattr(mod, "save_result", None)
            if save_fn:
                try:
                    save_fn(res)
                except Exception:
                    log(f"{name}.save_result failed: {traceback.format_exc()}", "WARNING")
            return name, True, res
        else:
            log(f"{name} attempt {attempt} failed: {res.get('meta', {}).get('message')}", "WARNING")
    return name, False, last_res


def run_scrapers_in_order(run_list):
    results = []
    skipped = []
    if PARALLEL:
        # run in parallel using ThreadPoolExecutor
        log("Running scrapers in parallel mode", "INFO")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(run_single_scraper, name): name for name in run_list}
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    res = fut.result()
                    results.append(res)
                except Exception:
                    log(f"Scraper {name} crashed: {traceback.format_exc()}", "ERROR")
                    results.append((name, False, {"meta": {"status": "error", "message": "executor exception"}}))
    else:
        # sequential
        log("Running scrapers sequentially", "INFO")
        for name in run_list:
            name, ok, res = run_single_scraper(name)
            # If module missing fetch, record skipped instead of error
            if res.get("meta", {}).get("message") == "no fetch()":
                skipped.append({"name": name, "reason": "no fetch()"})
                log(f"Skipped {name} (no fetch())", "INFO")
                continue
            results.append((name, ok, res))
    return results, skipped


def aggregate_results(results, skipped):
    summary = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "scrapers": {},
        "skipped": skipped,
        "overall_status": "ok"
    }
    for name, ok, res in results:
        entry = {
            "ok": bool(ok),
            "source": res.get("source"),
            "meta": res.get("meta", {}),
            "data": res.get("data", {})
        }
        summary["scrapers"][name] = entry
        if not ok:
            summary["overall_status"] = "partial_error"
    return summary


def save_summary(summary):
    tmp = SUMMARY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SUMMARY_PATH)
    log(f"Saved summary -> {SUMMARY_PATH}", "INFO")


def build_and_optionally_send(summary):
    # build message
    try:
        cn = importlib.import_module("scrapers.compose_notification")
    except Exception:
        log("compose_notification import failed; cannot build notification", "ERROR")
        return False, "compose_import_failed"

    try:
        if hasattr(cn, "build_message"):
            message = cn.build_message(summary)
        else:
            # fallback: write summary and call its main
            save_summary(summary)
            if hasattr(cn, "main"):
                cn.main()
                return True, "sent_via_compose_main"
            else:
                return False, "no_build_message_or_main"
    except Exception:
        log(f"compose_notification.build_message error: {traceback.format_exc()}", "ERROR")
        return False, "compose_build_failed"

    # show preview
    log("Notification message preview:\n" + message, "INFO")
    print("\n" + message + "\n")

    if not AUTO_SEND:
        log("AUTO_SEND disabled; not sending message", "INFO")
        return True, "dry_not_sent_auto_disabled"
    if DRY_RUN:
        log("DRY_RUN enabled; not sending message", "INFO")
        return True, "dry_not_sent_dry_run"

    # import tg sender
    try:
        tg = importlib.import_module(TG_MODULE)
    except Exception:
        log(f"Failed to import TG module {TG_MODULE}: {traceback.format_exc()}", "ERROR")
        return False, "tg_import_failed"

    send_fn = getattr(tg, "send_message", None)
    if send_fn is None:
        log(f"TG module {TG_MODULE} missing send_message()", "ERROR")
        return False, "tg_send_missing"

    # send
    try:
        send_fn(message)
        log("Telegram message sent", "INFO")
        return True, "sent"
    except Exception:
        log(f"TG send failed: {traceback.format_exc()}", "ERROR")
        return False, "tg_send_failed"


def main():
    # check trading day first (may exit)
    _check_trading_day_or_exit()

    run_list = resolve_run_list()
    results, skipped = run_scrapers_in_order(run_list)
    summary = aggregate_results(results, skipped)
    save_summary(summary)

    sent_ok, reason = build_and_optionally_send(summary)
    if not sent_ok:
        log(f"Notification/send step issue: {reason}", "WARNING")

    ok_count = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    log(f"Scrapers done: {ok_count}/{total} succeeded", "INFO")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["overall_status"] == "ok" else 2


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
