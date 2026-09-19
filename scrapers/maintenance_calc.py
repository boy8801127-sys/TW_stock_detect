# scrapers/maintenance_calc.py
"""
計算 大盤融資維持率（market-level）並輸出每檔計算明細 CSV（含精確數值、累積百分比、top contributors）
- 計算邏輯比照財經M平方：融資維持率 =（不含 ETF 之所有融資股票市值）／大盤融資餘額
  ETF（代號 00 開頭）的融資市值不計入分子，僅記錄於明細供稽核；分母仍為 TWSE 公告的大盤融資金額（含 ETF）
- 輸出：
  - results/maintenance_calc_formula.csv: 每檔明細，含精確 fin_value 與 numerator_contribution_precise、cumulative_pct（以 denominator 計，ETF 貢獻度為 0）
  - results/top_contributors.csv: 依 numerator_contribution_precise 排序的 top N（預設 top 50）
  - results/latest_maintenance_calc.json 與日期存檔: summary（含 numerator（不含ETF）, denominator, maintenance_rate, maintenance_rate_pct, numerator_billion, denominator_billion, etf_excluded_value_billion）
- 註記處理規則：含 '!' 整檔不計、含 'O' 融資視為 0
"""
import os
import csv
import time
import requests
from decimal import Decimal
from .utils import HEADERS, RESULT_DIR, error_result, make_result, run_cli, safe_parse_json, save_json, to_float, to_int

MI_MARGN_PER_STOCK = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"
STOCK_DAY_AVG_ALL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_AVG_ALL"
MI_MARGN_SUMMARY = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json"

SHARE_PER_LOT = 1000  # 融資今日餘額單位為張

CSV_HEADER = [
    "code", "name", "note", "note_flags", "is_etf", "closing_price",
    "fin_lots_raw", "short_lots_raw",
    "fin_lots_used", "fin_shares_used",
    "fin_value_used", "fin_value_precise",
    "numerator_contribution", "numerator_contribution_precise",
    "formula_text", "cumulative_pct"
]
TOP_HEADER = ["rank", "code", "name", "numerator_contribution_precise", "numerator_contribution", "cumulative_pct"]


def _get_json(url):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = safe_parse_json(resp)
    if data is None:
        raise ValueError(f"invalid or non-json response from {url}")
    return data


def fetch_prices():
    """回傳 (price_map, name_map)，鍵為補零至 4 碼的股票代號。"""
    price_map, name_map = {}, {}
    for item in _get_json(STOCK_DAY_AVG_ALL):
        code = item.get("Code") or item.get("股票代號")
        if code:
            key = str(code).zfill(4)
            price_map[key] = to_float(item.get("ClosingPrice") or item.get("MonthlyAveragePrice") or item.get("Close"))
            name_map[key] = item.get("Name") or item.get("股票名稱") or item.get("Name_zh")
    return price_map, name_map


def fetch_margin_per_stock():
    data = _get_json(MI_MARGN_PER_STOCK)
    if not isinstance(data, list):
        raise ValueError("unexpected MI_MARGN per-stock structure")
    return data


def fetch_margin_amount_thousands():
    """大盤融資金額（千元），取「融資金額」列的今日餘額（index 5）。"""
    for row in _get_json(MI_MARGN_SUMMARY)["tables"][0]["data"]:
        if isinstance(row, (list, tuple)) and len(row) >= 6 and "融資金額" in str(row[0] or ""):
            return Decimal(str(row[5]).replace(",", "").strip())
    raise ValueError("融資金額 row not found")


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def compute_and_export(top_n=50):
    start = time.time()
    prices, names = fetch_prices()
    margin_list = fetch_margin_per_stock()
    denominator = fetch_margin_amount_thousands() * 1000
    if denominator == 0:
        raise ValueError("denominator zero")

    numerator = Decimal(0)  # 不含 ETF（比照財經M平方計算邏輯）
    etf_excluded_value = Decimal(0)
    processed = skipped = 0
    skipped_examples = []
    entries = []  # (numerator contribution, csv row)

    for item in margin_list:
        code = item.get("股票代號") or item.get("Code")
        if not code:
            continue
        code_s = str(code).zfill(4)
        note = (item.get("註記") or item.get("Note") or item.get("remarks") or "").strip()
        flags_str = ",".join(ch for ch in "OX!" if ch in note)
        is_etf = code_s.startswith("00")
        price = prices.get(code_s)
        fin_lots_raw = to_int(item.get("融資今日餘額") or item.get("融資今日餘額(股)") or item.get("融資"))
        short_lots_raw = to_int(item.get("融券今日餘額") or item.get("融券今日餘額(張)") or item.get("融券"))

        excluded = "!" in note  # 註記含 ! 整檔不計
        fin_lots_used = 0 if excluded or "O" in note else (fin_lots_raw or 0)
        value = Decimal(0)
        if excluded:
            skipped += 1
            reason = "note_exclamation"
        elif fin_lots_used and price is None:
            skipped += 1
            reason = "no_price"
        else:
            reason = None
            if fin_lots_used:
                value = Decimal(fin_lots_used * SHARE_PER_LOT) * Decimal(str(price))
        if reason and len(skipped_examples) < 10:
            skipped_examples.append({"code": code_s, "reason": reason, "note": note})

        if is_etf:
            # ETF 不計入分子（比照財經M平方：融資維持率僅反映個股，不含 ETF）
            etf_excluded_value += value
            contrib = Decimal(0)
            formula_text = "ETF excluded from numerator (M平方 methodology)"
        else:
            numerator += value
            processed += value > 0
            contrib = value
            formula_text = "fin_value = fin_lots_used * SHARE_PER_LOT * closing_price"
        if excluded:
            formula_text = "skipped due to !"

        entries.append((contrib, {
            "code": code_s,
            "name": names.get(code_s) or item.get("股票名稱") or item.get("Name") or "",
            "note": note,
            "note_flags": flags_str,
            "is_etf": "True" if is_etf else "False",
            "closing_price": price if price is not None else "",
            "fin_lots_raw": fin_lots_raw or 0,
            "short_lots_raw": short_lots_raw or 0,
            "fin_lots_used": fin_lots_used,
            "fin_shares_used": fin_lots_used * SHARE_PER_LOT,
            "fin_value_used": float(round(value, 2)),
            "fin_value_precise": format(value, "f"),
            "numerator_contribution": float(round(contrib, 2)),
            "numerator_contribution_precise": format(contrib, "f"),
            "formula_text": formula_text,
            "cumulative_pct": 0.0,
        }))

    # 依貢獻度由大到小累積，cumulative_pct 以 denominator 計（rows 為共用物件，明細 CSV 維持原順序）
    ranked = sorted(entries, key=lambda e: e[0], reverse=True)
    running = Decimal(0)
    for contrib, row in ranked:
        running += contrib
        row["cumulative_pct"] = float(round(running / denominator * 100, 6))

    os.makedirs(RESULT_DIR, exist_ok=True)
    main_csv_path = os.path.join(RESULT_DIR, "maintenance_calc_formula.csv")
    top_csv_path = os.path.join(RESULT_DIR, "top_contributors.csv")
    _write_csv(main_csv_path, CSV_HEADER, (row for _, row in entries))
    _write_csv(top_csv_path, TOP_HEADER, ({"rank": i, **{k: row[k] for k in TOP_HEADER[1:]}}
                                          for i, (_, row) in enumerate(ranked[:top_n], start=1)))

    billion = Decimal(100000000)  # 億
    maintenance_rate = numerator / denominator
    return {
        "ok": True,
        "numerator": float(numerator),  # 不含 ETF
        "numerator_billion": float(numerator / billion),
        "etf_excluded_value": float(etf_excluded_value),
        "etf_excluded_value_billion": float(etf_excluded_value / billion),
        "denominator": float(denominator),
        "denominator_billion": float(denominator / billion),
        "maintenance_rate": float(maintenance_rate),
        "maintenance_rate_pct": float(maintenance_rate * 100),
        "elapsed_ms": int((time.time() - start) * 1000),
        "details": {"processed": processed, "skipped": skipped, "skipped_examples": skipped_examples},
        "csv_path": main_csv_path,
        "top_csv_path": top_csv_path,
    }


def fetch():
    try:
        out = compute_and_export()
    except Exception as e:
        return error_result(MI_MARGN_PER_STOCK, f"{type(e).__name__}: {e}")
    return make_result(MI_MARGN_PER_STOCK, {"maintenance_calc": out}, elapsed_ms=out["elapsed_ms"], details=out["details"])


def save_result(result):
    return save_json(result, "maintenance_calc")


if __name__ == "__main__":
    run_cli(fetch, save_result)
