# scrapers/maintenance_calc.py
"""
計算 大盤融資維持率（market-level）並輸出每檔計算明細 CSV（含精確數值、累積百分比、top contributors）
- 包含：
  - maintenance_calc_formula.csv: 每檔明細，含精確 fin_value 與 numerator_contribution_precise、cumulative_pct（以 denominator 計）
  - top_contributors.csv: 依 numerator_contribution_precise 排序的 top N（預設 top 50）
  - results/latest_maintenance_calc.json: summary（含 numerator, denominator, maintenance_rate, maintenance_rate_pct, numerator_billion, denominator_billion）
- 註記處理規則維持你的設定（'!'/'O'/'X'）
依賴: requests, csv, decimal
"""
import os
import time
import json
import csv
import requests
from decimal import Decimal, getcontext

getcontext().prec = 28

ROOT = os.path.dirname(__file__)
RESULT_DIR = os.path.join(ROOT, "..", "results")
os.makedirs(RESULT_DIR, exist_ok=True)

MI_MARGN_PER_STOCK = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"
STOCK_DAY_AVG_ALL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_AVG_ALL"
MI_MARGN_SUMMARY = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TWStockBot/1.0)"}

SHARE_PER_LOT = 1000  # 若 API 已是股請改為 1

def _to_int_safe(x):
    try:
        if x is None or x == "":
            return None
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return None

def _to_decimal_safe(x):
    try:
        if x is None or x == "":
            return None
        s = str(x).replace(",", "").strip()
        return Decimal(s)
    except Exception:
        return None

def _to_float_safe(x):
    try:
        if x is None or x == "":
            return None
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None

def fetch_prices():
    """
    取得每日個股價格陣列，回傳 (price_map, name_map).
    若 API 回傳非 JSON 或解析失敗，回傳 ({}, {}).
    """
    try:
        # 延遲 import safe_parse_json（避免執行時相對 import 的問題）
        try:
            from .utils import safe_parse_json
        except Exception:
            from scrapers.utils import safe_parse_json

        resp = requests.get(STOCK_DAY_AVG_ALL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[fetch_prices] request error: {e}")
        return {}, {}

    arr = safe_parse_json(resp)
    if arr is None:
        try:
            os.makedirs(RESULT_DIR, exist_ok=True)
            dump = os.path.join(RESULT_DIR, f"prices_raw_{int(time.time())}.txt")
            with open(dump, "w", encoding="utf-8") as f:
                f.write(resp.text)
            print(f"[fetch_prices] saved raw response to {dump}")
        except Exception as e:
            print(f"[fetch_prices] failed to save raw: {e}")
        return {}, {}

    price_map = {}
    name_map = {}
    try:
        for item in arr:
            code = item.get("Code") or item.get("股票代號")
            price = _to_float_safe(item.get("ClosingPrice") or item.get("MonthlyAveragePrice") or item.get("Close"))
            name = item.get("Name") or item.get("股票名稱") or item.get("Name_zh")
            if code:
                key = str(code).zfill(4)
                price_map[key] = price
                price_map[str(code)] = price
                name_map[key] = name
                name_map[str(code)] = name
    except Exception as e:
        print(f"[fetch_prices] parse error: {e}")
        return {}, {}

    return price_map, name_map


def fetch_margin_per_stock():
    """
    取得每檔融資融券明細（list）。
    若回傳非 JSON 或解析失敗，回傳空 list。
    """
    try:
        try:
            from .utils import safe_parse_json
        except Exception:
            from scrapers.utils import safe_parse_json

        resp = requests.get(MI_MARGN_PER_STOCK, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[fetch_margin_per_stock] request error: {e}")
        return []

    data = safe_parse_json(resp)
    if data is None:
        try:
            os.makedirs(RESULT_DIR, exist_ok=True)
            dump = os.path.join(RESULT_DIR, f"mi_margn_per_stock_raw_{int(time.time())}.txt")
            with open(dump, "w", encoding="utf-8") as f:
                f.write(resp.text)
            print(f"[fetch_margin_per_stock] saved raw response to {dump}")
        except Exception as e:
            print(f"[fetch_margin_per_stock] failed to save raw: {e}")
        return []

    # Expecting a list of dicts; if endpoint returns a dict wrapper, try to extract sensible list
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "items", "result", "dataList", "tables"):
            if key in data and isinstance(data[key], list):
                return data[key]
    # fallback: unable to normalize
    print("[fetch_margin_per_stock] unexpected JSON structure; returning empty list")
    return []

def fetch_margin_summary():
    """
    取得融資彙總 (summary) 並回傳 {"ok": True, "margin_amount_thousands": Decimal(...)} 或錯誤字典。
    若回傳非 JSON 或解析失敗，回傳 {"ok": False, "error": "...", "saved_raw": "..."}。
    """
    try:
        try:
            from .utils import safe_parse_json
        except Exception:
            from scrapers.utils import safe_parse_json

        resp = requests.get(MI_MARGN_SUMMARY, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        msg = f"request error: {e}"
        print(f"[fetch_margin_summary] {msg}")
        return {"ok": False, "error": msg}

    js = safe_parse_json(resp)
    if js is None:
        try:
            os.makedirs(RESULT_DIR, exist_ok=True)
            dump = os.path.join(RESULT_DIR, f"mi_margn_summary_raw_{int(time.time())}.txt")
            with open(dump, "w", encoding="utf-8") as f:
                f.write(resp.text)
            print(f"[fetch_margin_summary] saved raw response to {dump}")
            return {"ok": False, "error": "invalid or non-json response", "saved_raw": dump}
        except Exception as e:
            print(f"[fetch_margin_summary] failed to save raw: {e}")
            return {"ok": False, "error": "invalid or non-json response"}

    try:
        # typical shape: js is dict with "tables" key containing list where tables[0]["data"] is rows
        tables = js.get("tables", []) if isinstance(js, dict) else []
        if not tables:
            return {"ok": False, "error": "no tables", "raw": js}
        # tolerate either dict-with-data or list-of-rows
        first_table = tables[0]
        data_rows = first_table.get("data", []) if isinstance(first_table, dict) else first_table
        for row in data_rows:
            if isinstance(row, (list, tuple)) and len(row) >= 6:
                first = row[0] or ""
                if "融資金額" in str(first):
                    today_val = row[5]
                    amt_thousands = _to_decimal_safe(today_val)
                    if amt_thousands is None:
                        return {"ok": False, "error": "cannot parse margin amount", "raw": today_val}
                    return {"ok": True, "margin_amount_thousands": amt_thousands}
    except Exception as e:
        return {"ok": False, "error": str(e), "raw": js}

    return {"ok": False, "error": "融資金額 row not found", "raw": js}

def parse_note_flags(note):
    s = (note or "").strip()
    flags = {"O": False, "X": False, "!": False}
    present = []
    for ch in ["O", "X", "!"]:
        if ch in s:
            flags[ch] = True
            present.append(ch)
    return flags, ",".join(present)

def compute_and_export(top_n=50):
    start = time.time()
    prices, names = fetch_prices()
    margin_list = fetch_margin_per_stock()
    summary = fetch_margin_summary()
    if not summary.get("ok"):
        return {"ok": False, "error": "failed to get margin summary", "detail": summary}
    denom_thousands = summary["margin_amount_thousands"]
    denominator = (denom_thousands * Decimal(1000)) if isinstance(denom_thousands, Decimal) else Decimal(denom_thousands) * Decimal(1000)

    numerator = Decimal('0')
    processed = 0
    skipped = 0
    skipped_examples = []

    main_csv_path = os.path.join(RESULT_DIR, "maintenance_calc_formula.csv")
    top_csv_path = os.path.join(RESULT_DIR, "top_contributors.csv")
    csv_header = [
        "code","name","note","note_flags","is_etf","closing_price",
        "fin_lots_raw","short_lots_raw",
        "fin_lots_used","fin_shares_used",
        "fin_value_used","fin_value_precise",
        "numerator_contribution","numerator_contribution_precise",
        "formula_text","cumulative_pct"
    ]

    rows_out = []

    for item in margin_list:
        code = item.get("股票代號") or item.get("Code")
        if not code:
            continue
        code_s = str(code).zfill(4)
        note = (item.get("註記") or item.get("Note") or item.get("remarks") or "").strip()
        flags, flags_str = parse_note_flags(note)
        is_etf = str(code).startswith("00")

        fin_lots_raw = _to_int_safe(item.get("融資今日餘額") or item.get("融資今日餘額(股)") or item.get("融資"))
        short_lots_raw = _to_int_safe(item.get("融券今日餘額") or item.get("融券今日餘額(張)") or item.get("融券"))

        # '!' -> 全部跳過
        if flags.get("!"):
            skipped += 1
            if len(skipped_examples) < 10:
                skipped_examples.append({"code": code_s, "reason": "note_exclamation", "note": note})
            # still append a row for auditing with zero contribution
            rows_out.append({
                "code": code_s,
                "name": names.get(code_s) or "",
                "note": note,
                "note_flags": flags_str,
                "is_etf": "True" if is_etf else "False",
                "closing_price": "",
                "fin_lots_raw": fin_lots_raw or 0,
                "short_lots_raw": short_lots_raw or 0,
                "fin_lots_used": 0,
                "fin_shares_used": 0,
                "fin_value_used": 0.0,
                "fin_value_precise": "0",
                "numerator_contribution": 0.0,
                "numerator_contribution_precise": "0",
                "formula_text": "skipped due to !",
                "cumulative_pct": 0.0
            })
            continue

        fin_lots_used = fin_lots_raw or 0
        if flags.get("O") and not flags.get("X"):
            fin_lots_used = 0
        if flags.get("O") and flags.get("X"):
            fin_lots_used = 0

        price = prices.get(code_s) or prices.get(str(int(code_s))) if code_s.isdecimal() else prices.get(code_s)
        name = names.get(code_s) or names.get(str(int(code_s))) or item.get("股票名稱") or item.get("Name")

        if fin_lots_used == 0 or fin_lots_raw is None:
            fin_shares_used = 0
            fin_value_used_decimal = Decimal('0')
        else:
            fin_shares_used = fin_lots_used * SHARE_PER_LOT
            if price is None:
                skipped += 1
                if len(skipped_examples) < 10:
                    skipped_examples.append({"code": code_s, "reason": "no_price", "note": note})
                fin_value_used_decimal = Decimal('0')
            else:
                fin_value_used_decimal = Decimal(fin_shares_used) * Decimal(str(price))

        numerator += fin_value_used_decimal
        if fin_value_used_decimal > 0:
            processed += 1

        fin_value_precise = format(fin_value_used_decimal, 'f')
        numerator_contrib_precise = fin_value_precise

        rows_out.append({
            "code": code_s,
            "name": name or "",
            "note": note,
            "note_flags": flags_str,
            "is_etf": "True" if is_etf else "False",
            "closing_price": price if price is not None else "",
            "fin_lots_raw": fin_lots_raw or 0,
            "short_lots_raw": short_lots_raw or 0,
            "fin_lots_used": fin_lots_used,
            "fin_shares_used": fin_shares_used,
            "fin_value_used": float(round(fin_value_used_decimal, 2)),
            "fin_value_precise": fin_value_precise,
            "numerator_contribution": float(round(fin_value_used_decimal, 2)),
            "numerator_contribution_precise": numerator_contrib_precise,
            "formula_text": "fin_value = fin_lots_used * SHARE_PER_LOT * closing_price",
            "cumulative_pct": 0.0  # placeholder, fill later
        })

    # sort rows by precise contribution descending for cumulative calc
    rows_sorted = sorted(rows_out, key=lambda r: Decimal((r.get("numerator_contribution_precise") or "0").replace(',', '')), reverse=True)

    # compute cumulative pct relative to denominator
    cumulative = Decimal('0')
    for r in rows_sorted:
        contrib = Decimal((r.get("numerator_contribution_precise") or "0").replace(',', ''))
        cumulative += contrib
        pct = (cumulative / denominator * Decimal(100)) if denominator else Decimal('0')
        # write cumulative pct as float with 6 decimal places for precision
        r["cumulative_pct"] = float(round(pct, 6))

    # write main CSV in original (unsorted) order but with cumulative pct value filled from sorted mapping
    # build mapping from code -> cumulative_pct by finding position in sorted list
    cumulative_map = {}
    cum_acc = Decimal('0')
    for r in rows_sorted:
        code = r.get("code")
        contrib = Decimal((r.get("numerator_contribution_precise") or "0").replace(',', ''))
        cum_acc += contrib
        cumulative_map[code] = float(round((cum_acc / denominator * Decimal(100)) if denominator else Decimal('0'), 6))

    # write main CSV in original order (rows_out)
    with open(main_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_header)
        writer.writeheader()
        for r in rows_out:
            code = r.get("code")
            r["cumulative_pct"] = cumulative_map.get(code, 0.0)
            writer.writerow(r)

    # write top contributors CSV (top_n)
    top_header = ["rank","code","name","numerator_contribution_precise","numerator_contribution","cumulative_pct"]
    with open(top_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=top_header)
        writer.writeheader()
        for idx, r in enumerate(rows_sorted[:top_n], start=1):
            writer.writerow({
                "rank": idx,
                "code": r.get("code"),
                "name": r.get("name"),
                "numerator_contribution_precise": r.get("numerator_contribution_precise"),
                "numerator_contribution": r.get("numerator_contribution"),
                "cumulative_pct": r.get("cumulative_pct")
            })

    if denominator == 0:
        return {
            "ok": False,
            "error": "denominator zero",
            "numerator": float(numerator),
            "denominator": float(denominator),
            "details": {"processed": processed, "skipped": skipped, "skipped_examples": skipped_examples},
            "csv_path": main_csv_path,
            "top_csv_path": top_csv_path
        }

    maintenance_rate = numerator / denominator
    elapsed_ms = int((time.time() - start) * 1000)

    # add friendly units (billion = 億) to JSON
    numerator_billion = float(numerator / Decimal('100000000'))  # 億
    denominator_billion = float(denominator / Decimal('100000000'))  # 億

    summary = {
        "ok": True,
        "numerator": float(numerator),
        "numerator_billion": numerator_billion,
        "denominator": float(denominator),
        "denominator_billion": denominator_billion,
        "maintenance_rate": float(maintenance_rate),
        "maintenance_rate_pct": float(maintenance_rate * Decimal(100)),
        "elapsed_ms": elapsed_ms,
        "details": {"processed": processed, "skipped": skipped, "skipped_examples": skipped_examples},
        "csv_path": main_csv_path,
        "top_csv_path": top_csv_path
    }
    return summary

def fetch():
    try:
        out = compute_and_export()
        if not out.get("ok"):
            return {"timestamp": int(time.time()), "source": MI_MARGN_PER_STOCK, "data": {}, "meta": {"status": "error", "message": out.get("error"), "detail": out}}
        result = {
            "timestamp": int(time.time()),
            "source": MI_MARGN_PER_STOCK,
            "data": {"maintenance_calc": out},
            "meta": {"status": "ok", "elapsed_ms": out.get("elapsed_ms", None), "details": out.get("details", {})}
        }
        return result
    except Exception as e:
        return {"timestamp": int(time.time()), "source": MI_MARGN_PER_STOCK, "data": {}, "meta": {"status": "error", "message": str(e)}}

def save_result(result):
    os.makedirs(RESULT_DIR, exist_ok=True)
    latest = os.path.join(RESULT_DIR, "latest_maintenance_calc.json")
    tmp = latest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, latest)
    return latest

if __name__ == "__main__":
    r = fetch()
    if r.get("meta", {}).get("status") == "ok":
        save_result(r)

    mc = r.get("data", {}).get("maintenance_calc", {})
    num = mc.get("numerator")
    den = mc.get("denominator")
    pct = mc.get("maintenance_rate_pct")

    if num is not None:
        try:
            print("所有融資股票市值 (numerator): {:,}".format(int(round(num))))
        except Exception:
            print("所有融資股票市值 (numerator):", num)
    else:
        print("numerator: None")
    if den is not None:
        try:
            print("大盤融資餘額 (denominator): {:,}".format(int(round(den))))
        except Exception:
            print("大盤融資餘額 (denominator):", den)
    else:
        print("denominator: None")
    if pct is not None:
        print("大盤融資維持率: {:.4f}%".format(pct))
    else:
        print("maintenance_rate_pct: None")

    # JSON 輸出（已清理與加入友善單位）
    print(json.dumps(r, ensure_ascii=False, indent=2))
