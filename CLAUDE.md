# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

A daily automated bot that scrapes Taiwan stock market indicators (券資比, VIX, futures open interest, margin market cap, margin maintenance ratio) and sends a Chinese-language summary to Telegram before each trading day's open. It runs at 08:00 (Asia/Taipei) daily via a GCP Cloud Run Job or Docker, skipping non-trading days automatically.

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
| `RETRY` | `1` | Attempts per scraper on failure |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR |

Default scraper order (when `ORDERED_SCRAPERS` not set): `twse_margin_api`, `twse_mi_index`, `cmoney_futures_night`, `VIXTWN`, `taifex_futures`, `cmoney_margin`, `maintenance_calc`, `cnn_fear_greed`, `tsm_adr_compare`. Scrapers run only from this list (or `ORDERED_SCRAPERS`); a new scraper must be added to `DEFAULT_ORDER`.

## Architecture

### Execution flow (`main.py`)

1. `_check_trading_day_or_exit()` — calls `scrapers.trading_day.is_twse_trading_day()`; exits 0 on non-trading days.
2. `resolve_run_list()` — determines scraper order from `ORDERED_SCRAPERS` env var or `DEFAULT_ORDER`.
3. `run_single_scraper()` — runs each scraper sequentially, with retry; calls the scraper's optional `save_result()` on success.
4. `aggregate_results()` — collects all `(name, ok, result)` tuples into a summary dict.
5. `save_summary()` — writes `results/latest_summary.json` atomically via temp file + `os.replace`.
6. `build_and_optionally_send()` — calls `scrapers.compose_notification.build_message(summary)` to format the Chinese message, then optionally calls `scrapers.tg_send.send_message()`.

### Scraper contract

Every scraper listed in `DEFAULT_ORDER` must export a `fetch()` function. The function must return a dict in this shape:

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

Scrapers may also export an optional `save_result(result)` function — called by the pipeline after a successful `fetch()`. Most delegate to `utils.save_json(result, prefix)`, which writes `results/latest_<prefix>.json` plus a dated archive `results/<YYYY-MM-DD>_<prefix>.json`. Only the dated archives are synced to GCS, so anything that must survive between Cloud Run executions (day-over-day deltas, 「（快取）」 fallbacks) has to be read from a dated archive, never from `latest_*`.

`scrapers/utils.py` holds the shared helpers: `make_result`/`error_result` (build the dict above), `to_float`/`to_int`, `save_json`, `safe_parse_json`, `capture_xhr` (Playwright XHR interception used by the CMoney scrapers) and `run_cli` (the `python -m scrapers.<name>` entry point).

### Notification format (`compose_notification.py`)

`build_message(summary, ai_text=None)` reads the `summary["scrapers"]` dict and formats each section in order: (AI 簡評) → 大盤指數 → 市場情緒(VIX) → 美股恐懼貪婪指數 → 台積電 ADR → 券資比 → 期貨未平倉口數 → 融資融券.

融資融券 section: balance / usage / short data come from `cmoney_margin`, but 維持率 comes from `maintenance_calc` (`data.maintenance_calc.maintenance_rate_pct`) and is shown independently of whether `cmoney_margin` succeeded. If `maintenance_calc` failed today, it falls back to the most recent dated archive `<date>_maintenance_calc.json` and appends 「（快取）」 (same pattern as VIX, which uses `<date>_taifex_vix.json`). CMoney's own `maintenance_rate` field is no longer used — it stopped updating for regulatory reasons.

### 維持率 calculation (`maintenance_calc.py`)

維持率 = (Σ 個股融資股數 × 收盤價，**不含 ETF**) ÷ 大盤融資餘額, matching 財經M平方. ETF (code starts with `00`) is excluded from the numerator only; the denominator is TWSE's published 大盤融資金額 (includes ETF). Rows noted `!` are skipped and `O` are zeroed. Excluded ETF value is kept in the CSV audit trail and `etf_excluded_value_billion`.

## Docker

```bash
docker build -t tw-stock-detect .

docker run --env-file .env tw-stock-detect
```

The `results/` directory is excluded from version control (`.gitignore`). It is created at startup by `main.py` and by the Dockerfile.
