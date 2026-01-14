#!/usr/bin/env python3
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.request import urlopen, Request

RKI_LK_CSV = (
    "https://raw.githubusercontent.com/robert-koch-institut/"
    "COVID-19_7-Tage-Inzidenz_in_Deutschland/main/"
    "COVID-19-Faelle_7-Tage-Inzidenz_Landkreise.csv"
)

OUT_LATEST = "data/latest.json"
OUT_SERIES = "data/timeseries.json"

DAYS_BACK = 60

def safe_int(x):
    try:
        return int(float(x))
    except Exception:
        return None

def safe_float(x):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None

def fetch_csv(url: str) -> list[dict]:
    req = Request(url, headers={"User-Agent": "kids-risk-map/1.0 (github pages)"})
    with urlopen(req) as r:
        raw = r.read().decode("utf-8")
    reader = csv.DictReader(raw.splitlines())
    return list(reader)

def normalize_lk(lk_raw: str) -> str:
    if lk_raw is None:
        return ""
    s = "".join(ch for ch in str(lk_raw).strip() if ch.isdigit())
    if not s:
        return ""
    if len(s) > 5:
        s = s[:5]
    return s.zfill(5)

def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return ((new - old) / old) * 100.0

def main():
    os.makedirs("data", exist_ok=True)

    rows = fetch_csv(RKI_LK_CSV)
    if not rows:
        print("ERROR: CSV returned no rows.", file=sys.stderr)
        sys.exit(1)

    # Aggregate per (date, lk) — no age groups in this dataset
    per = defaultdict(dict)
    dates = set()

    for r in rows:
        date = (r.get("Meldedatum") or "").strip()
        lk = normalize_lk((r.get("Landkreis_id") or "").strip())
        if not date or not lk:
            continue

        cases_7d = safe_int(r.get("Faelle_7-Tage"))
        inc_7d = safe_float(r.get("Inzidenz_7-Tage"))

        if cases_7d is None and inc_7d is None:
            continue

        per[(date, lk)] = {
            "cases_7d": cases_7d,
            "incidence_7d": None if inc_7d is None else round(inc_7d, 2)
        }
        dates.add(date)

    if not dates:
        print("ERROR: No usable rows found.", file=sys.stderr)
        sys.exit(1)

    latest_date = max(dates)
    latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
    start_date = (latest_dt - timedelta(days=DAYS_BACK - 1)).strftime("%Y-%m-%d")
    prev_date = (latest_dt - timedelta(days=7)).strftime("%Y-%m-%d")

    # Build time series
    series = defaultdict(list)
    for (date, lk), v in per.items():
        if date < start_date or date > latest_date:
            continue
        series[lk].append({"date": date, "incidence_7d": v.get("incidence_7d")})

    for lk in list(series.keys()):
        series[lk].sort(key=lambda x: x["date"])

    # Build latest values + trend vs prev week (based on incidence)
    latest_values = {}
    for lk in series.keys():
        v_latest = per.get((latest_date, lk))
        if not v_latest:
            continue

        v_prev = per.get((prev_date, lk))
        inc_latest = v_latest.get("incidence_7d")
        inc_prev = v_prev.get("incidence_7d") if v_prev else None
        trend = pct_change(inc_latest, inc_prev)
        trend = None if trend is None else round(trend, 1)

        latest_values[lk] = {
            "incidence_7d": inc_latest,
            "cases_7d": v_latest.get("cases_7d"),
            "trend_pct": trend
        }

    if not latest_values:
        print("ERROR: latest_values is empty.", file=sys.stderr)
        sys.exit(1)

    # Metric min/max for styling
    def minmax(metric):
        vals = []
        for v in latest_values.values():
            x = v.get(metric)
            if isinstance(x, (int, float)) and math.isfinite(x):
                vals.append(float(x))
        return {"min": min(vals), "max": max(vals)} if vals else {"min": 0.0, "max": 1.0}

    latest_out = {
        "updated_at": latest_date,
        "notes": "No age breakdown available in this RKI dataset; values represent all ages.",
        "metric_meta": {
            "incidence_7d": minmax("incidence_7d"),
            "cases_7d": minmax("cases_7d"),
            "trend_pct": minmax("trend_pct"),
        },
        "values": latest_values
    }

    series_out = {
        "updated_at": latest_date,
        "window_days": DAYS_BACK,
        "series": series
    }

    with open(OUT_LATEST, "w", encoding="utf-8") as f:
        json.dump(latest_out, f, ensure_ascii=False, separators=(",", ":"))
    with open(OUT_SERIES, "w", encoding="utf-8") as f:
        json.dump(series_out, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Wrote {OUT_LATEST} and {OUT_SERIES} for date {latest_date}")
    print("Districts in latest:", len(latest_values))

if __name__ == "__main__":
    main()