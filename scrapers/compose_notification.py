# scrapers/compose_notification.py
import os
import json
import math
from datetime import datetime, timezone

# primary summary path (existing pipeline)
SUMMARY_PATH = os.path.join(os.path.dirname(__file__), "..", "results", "latest_summary.json")
# fallback to maintenance calc summary if primary not present
MAINT_PATH = os.path.join(os.path.dirname(__file__), "..", "results", "latest_maintenance_calc.json")

def _fmt_number(v, decimals=None):
    if v is None:
        return "-"
    try:
        if isinstance(v, str):
            vv = float(str(v).replace(",", ""))
        else:
            vv = float(v)
    except Exception:
        return str(v)
    if decimals is None:
        if abs(vv - int(vv)) < 1e-8:
            return f"{int(vv):,}"
        return f"{vv:,}"
    else:
        fmt = f"{{:,.{decimals}f}}"
        s = fmt.format(vv)
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s

def _fmt_percent_value(v, ndigits=2):
    try:
        val = float(v)
    except Exception:
        return "-"
    return f"{val:.{ndigits}f}%"

def _fmt_pct(value):
    try:
        v = float(value)
    except Exception:
        return "-"
    return f"{v*100:+.2f}%"

def _sign_symbol(delta):
    try:
        d = float(delta)
    except Exception:
        return ""
    if d > 0:
        return "▲"
    if d < 0:
        return "▼"
    return "→"

def _vix_interpret(v):
    try:
        v = float(v)
    except Exception:
        return ""
    if v < 15:
        return "情緒平穩，波動預期低"
    if 15 <= v < 20:
        return "略有不安，波動溫和"
    if 20 <= v < 30:
        return "情緒警惕，波動增加"
    return "市場恐慌，波動性極高"

def _load_json_try(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def build_message(summary):
    gen = summary.get("generated_at") or datetime.now(timezone.utc).astimezone().isoformat()
    lines = []
    header = f"📊 今日大盤指標彙整  {gen}\n"
    lines.append(header)

    scrapers = summary.get("scrapers", {})

    # 1) 發行量加權股價指數 (收盤) — 放首位
    if "twse_mi_index" in scrapers:
        info = scrapers["twse_mi_index"]
        v = info.get("data", {}).get("mi_index_close", {})
        val = v.get("value") or v.get("raw")
        lines.append(f"• 發行量加權股價指數 (收盤): {_fmt_number(val, 0)}")

    # 2) 券資比 (TWSE)
    if "twse_margin_api" in scrapers:
        info = scrapers["twse_margin_api"]
        ratio = info.get("data", {}).get("ratio", {})
        today = ratio.get("today")
        delta = ratio.get("delta")
        prev = ratio.get("previous")
        if today is not None:
            pct_str = _fmt_pct(today)
            sym = _sign_symbol(delta or 0)
            delta_pct = ""
            try:
                if delta is not None:
                    delta_pct = f"{(float(delta))*100:+.2f}pt"
            except Exception:
                delta_pct = ""
            rel_pct = ""
            try:
                if prev is not None and delta is not None and float(prev) != 0:
                    rel_pct = f"{(float(delta)/abs(float(prev))*100):.2f}%"
                    rel_pct = f"+{rel_pct}" if float(delta) > 0 else rel_pct
            except Exception:
                rel_pct = ""
            extras = []
            if delta_pct:
                extras.append(delta_pct)
            if rel_pct:
                extras.append(rel_pct)
            extras_text = ", ".join(extras) if extras else "-"
            lines.append(f"• 券資比 (TWSE): {pct_str} {sym} ({extras_text})")

    # 3) VIX
    if "VIXTWN" in scrapers:
        info = scrapers["VIXTWN"]
        v = info.get("data", {}).get("vix", {})
        val = v.get("value") or v.get("raw")
        if val is not None:
            vstr = _fmt_number(val, 2)
            interp = _vix_interpret(val)
            lines.append(f"• 臺指選擇權波動率 (VIX): {vstr}  — {interp}")

    # 4) 臺股期貨未平倉口數
    if "taifex_futures" in scrapers:
        info = scrapers["taifex_futures"]
        data = info.get("data", {})
        foreign = data.get("foreign") or {}
        dealer = data.get("dealer") or {}
        inv = data.get("inv_trust") or data.get("inv") or {}
        def pick(item):
            if not item:
                return None, None
            if isinstance(item, dict):
                cur = item.get("current")
                raw = item.get("raw")
                return cur, raw
            return item, item
        f_cur, f_raw = pick(foreign)
        d_cur, d_raw = pick(dealer)
        i_cur, i_raw = pick(inv)
        lines.append("• 臺股期貨未平倉口數:")
        def need_raw_display(cur, raw):
            if cur is None or raw is None:
                return False
            try:
                cur_s = str(int(cur))
            except Exception:
                try:
                    cur_s = str(float(cur))
                except Exception:
                    cur_s = str(cur)
            raw_s = str(raw).replace(",", "").replace(" ", "")
            return raw_s != cur_s and raw_s != f"+{cur_s}" and raw_s != f"-{cur_s}"
        lines.append(f"  - 外資未平倉: {_fmt_number(f_cur,0)}" + (f"  (原始: {f_raw})" if need_raw_display(f_cur, f_raw) else ""))
        lines.append(f"  - 自營商未平倉: {_fmt_number(d_cur,0)}" + (f"  (原始: {d_raw})" if need_raw_display(d_cur, d_raw) else ""))
        lines.append(f"  - 投信未平倉: {_fmt_number(i_cur,0)}" + (f"  (原始: {i_raw})" if need_raw_display(i_cur, i_raw) else ""))

    # 5) 取出 maintenance_calc 或 cmoney_margin 提供的大盤融資相關值
    # 首先，嘗試在 summary['scrapers'] 裡找 maintenance_calc
    numerator = None
    maintenance_rate = None

    # helper to extract from nested dicts with multiple possible shapes
    def extract_from_obj(obj):
        if not obj:
            return None, None
        # possible shapes:
        # 1) obj is {"data": {"maintenance_calc": {...}}}
        # 2) obj is {"data": {...}} where data has numerator directly
        # 3) obj is the inner dict itself
        try:
            if isinstance(obj, dict):
                # case 1
                d = obj.get("data") or obj
                if isinstance(d, dict) and "maintenance_calc" in d and isinstance(d["maintenance_calc"], dict):
                    inner = d["maintenance_calc"]
                    return inner.get("numerator"), inner.get("maintenance_rate") or inner.get("maintenance_rate_pct")
                # case 2
                if isinstance(d, dict):
                    if "numerator" in d or "maintenance_rate" in d or "maintenance_rate_pct" in d:
                        return d.get("numerator"), d.get("maintenance_rate") or d.get("maintenance_rate_pct")
                # case 3: maybe obj itself has numerator
                if "numerator" in obj or "maintenance_rate" in obj or "maintenance_rate_pct" in obj:
                    return obj.get("numerator"), obj.get("maintenance_rate") or obj.get("maintenance_rate_pct")
        except Exception:
            pass
        return None, None

    # try scrapers dict first
    if "maintenance_calc" in scrapers:
        numerator, maintenance_rate = extract_from_obj(scrapers.get("maintenance_calc"))
    if numerator is None and "cmoney_margin" in scrapers:
        numerator, maintenance_rate = extract_from_obj(scrapers.get("cmoney_margin"))
    # fallback: try summary top-level in case the structure is different
    if numerator is None or maintenance_rate is None:
        # try scanning all scrapers for candidates
        for nm, obj in scrapers.items():
            if numerator is None or maintenance_rate is None:
                n, m = extract_from_obj(obj)
                if n is not None:
                    numerator = numerator or n
                if m is not None:
                    maintenance_rate = maintenance_rate or m

    # if still None, try loading latest_maintenance_calc.json directly
    if numerator is None:
        j = _load_json_try(MAINT_PATH)
        if j:
            # expect j['data']['maintenance_calc']
            try:
                mc = j.get("data", {}).get("maintenance_calc", {}) or j.get("data") or j.get("maintenance_calc") or {}
                numerator = mc.get("numerator") or mc.get("numerator_billion")
                maintenance_rate = mc.get("maintenance_rate") or mc.get("maintenance_rate_pct")
            except Exception:
                numerator = None
                maintenance_rate = None

    # Format and display if available
    if numerator is not None:
        try:
            num_val = float(numerator)
            if num_val < 1_000_000:  # likely already in 億 (e.g., 5402)
                num_in_billion = num_val
            else:
                num_in_billion = num_val / 100000000.0
            num_display = f"{num_in_billion:.0f}"
        except Exception:
            num_display = str(numerator)
        lines.append(f"• 所有融資上市股票市值: {num_display} 億")

    if maintenance_rate is not None:
        try:
            mr = float(maintenance_rate)
            if mr > 1.5:
                mr_pct = mr if mr > 10 else mr * 100
            elif mr > 1:
                mr_pct = mr * 100
            else:
                mr_pct = mr * 100
            mr_display = f"{mr_pct:.2f}%"
        except Exception:
            mr_display = str(maintenance_rate)
        lines.append(f"• 大盤融資維持率: {mr_display}")

    # other scrapers: fallback brief display
    special = {"twse_mi_index", "twse_margin_api", "VIXTWN", "taifex_futures", "cmoney_margin", "maintenance_calc"}
    for name, info in scrapers.items():
        if name in special:
            continue
        data = info.get("data", {})
        display = None
        for k in ("vix", "maintenance_rate", "mi_index_close", "ratio"):
            if k in data:
                val = data[k].get("value") if isinstance(data[k], dict) else data[k]
                display = f"{k}: {_fmt_number(val)}"
                break
        if not display and isinstance(data, dict):
            for k2, v2 in data.items():
                if isinstance(v2, dict) and ("value" in v2 or "current" in v2):
                    val = v2.get("value") or v2.get("current") or v2.get("raw")
                    display = f"{k2}: {_fmt_number(val)}"
                    break
        if display:
            lines.append(f"• {name}: {display}")

    message = "\n".join(lines)
    return message

def load_summary(path=SUMMARY_PATH):
    # try primary path then fallback to maintenance calc path
    j = _load_json_try(path)
    if j:
        return j
    j2 = _load_json_try(MAINT_PATH)
    if j2:
        # wrap maintenance calc into summary-shaped dict for backward compatibility
        return {"generated_at": j2.get("timestamp") or None, "scrapers": {"maintenance_calc": j2.get("data", {}).get("maintenance_calc", j2.get("data", {}))}}
    raise FileNotFoundError(f"Neither {path} nor {MAINT_PATH} found")

def main():
    summary = load_summary()
    msg = build_message(summary)
    print(msg)
    return msg

if __name__ == "__main__":
    main()
