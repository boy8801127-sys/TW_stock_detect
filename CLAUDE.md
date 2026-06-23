# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

A daily automated bot that scrapes Taiwan stock market indicators (券資比, VIX, futures open interest, margin market cap, margin maintenance ratio) and sends a Chinese-language summary to Telegram before each trading day's open. It runs at 00:02 daily via GCP or Docker, skipping non-trading days automatically.

## Running the project

```bash
# Install dependencies
pip install -r requirements.txt

# Run (dry-run by default — prints message but does not send to Telegram)
python main.py

# Send to Telegram (requires .env with TG_BOT_TOKEN and TG_CHAT_ID)
AUTO_SEND=true DRY_RUN=false python main.py

# Skip trading-day gate (useful for local testing on weekends/holidays)
SKIP_TRADING_DAY_CHECK=true python main.py

# Test a single scraper module directly (each module is independently runnable)
python -m scrapers.twse_margin_api
```

## Key environment variables

| Variable | Default | Purpose |
|---|---|---|
| `TG_BOT_TOKEN` | — | Telegram bot token (required to send) |
| `TG_CHAT_ID` | — | Telegram chat ID (required to send) |
| `AUTO_SEND` | `false` | Actually call Telegram API |
| `DRY_RUN` | `true` | Skip sending even if AUTO_SEND=true |
| `SKIP_TRADING_DAY_CHECK` | `false` | Bypass trading-day gate |
| `ORDERED_SCRAPERS` | (see below) | Comma-separated module names to run |
| `PARALLEL` | `false` | Run scrapers concurrently |
| `MAX_WORKERS` | `4` | Thread count when PARALLEL=true |
| `RETRY` | `1` | Attempts per scraper on failure |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR |

Default scraper order (when `ORDERED_SCRAPERS` not set): `twse_margin_api`, `twse_mi_index`, `VIXTWN`, `taifex_futures`, `maintenance_calc`.

## Architecture

### Execution flow (`main.py`)

1. `_check_trading_day_or_exit()` — calls `scrapers.trading_day.is_twse_trading_day()`; exits 0 on non-trading days.
2. `resolve_run_list()` — determines scraper order from `ORDERED_SCRAPERS` env var or `DEFAULT_ORDER`.
3. `run_scrapers_in_order()` — runs each scraper sequentially (or in a thread pool if `PARALLEL=true`), with retry.
4. `aggregate_results()` — collects all `(name, ok, result)` tuples into a summary dict.
5. `save_summary()` — writes `results/latest_summary.json` atomically via temp file + `os.replace`.
6. `build_and_optionally_send()` — calls `scrapers.compose_notification.build_message(summary)` to format the Chinese message, then optionally calls `scrapers.tg_send.send_message()`.

### Scraper contract

Every file under `scrapers/` that should be auto-discovered must export a `fetch()` function. The function must return a dict in this shape:

```python
{
    "timestamp": int,        # unix epoch
    "source": str,           # human-readable source name
    "data": dict,            # scraper-specific payload
    "meta": {
        "status": "ok",      # "ok" = success, anything else = failure
        "message": str       # optional detail
    }
}
```

Scrapers may also export an optional `save_result(result)` function — called by the pipeline after a successful `fetch()` to write a per-scraper JSON file under `results/`.

Support modules (`compose_notification.py`, `tg_send.py`, `trading_day.py`, `utils.py`) are not auto-discovered because they have no `fetch()`.

### Notification format (`compose_notification.py`)

`build_message(summary)` reads the `summary["scrapers"]` dict and formats each section in order: 指數 → 券資比 → VIX → 期貨未平倉 → 融資市值 → 維持率. Unknown scrapers with recognizable data shapes get a generic fallback line. The function handles several nested data shapes for `maintenance_calc` (it checks `data.maintenance_calc`, `data` directly, and also tries loading `results/latest_maintenance_calc.json` as a fallback).

## Docker

```bash
docker build -t tw-stock-detect .
# With Playwright browsers (larger image):
docker build --build-arg INSTALL_PLAYWRIGHT=true -t tw-stock-detect .

docker run --env-file .env tw-stock-detect
```

The `results/` directory is excluded from version control (`.gitignore`). It is created at startup by `main.py` and by the Dockerfile.
