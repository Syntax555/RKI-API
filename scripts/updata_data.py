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

AGE_GROUPS = {"00-04", "05-14"}  # babies + children
DAYS_BACK = 60                  # time series length

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def safe_int(x):
    try:
        return int(float(x))
    except Exception:
        return None

def fetch_csv(url: str) -> list[dict]:
    req = Request(url, headers={"User-Agent": "kids-risk-map/1.0 (github pages)"})
    with urlopen(req) as r:
        raw = r.read().decode("utf-8")
    reader = csv.DictReader(raw.splitlines())
    return list(reader)

def calc_incidence(cases_7d: int, population: int) -> float | None:
    if not population or population <= 0 or cases_7d is None:
        return None
    return (cases_7d / population) * 100000.0

def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return ((new - old) / old) * 100.0

def main():
    os.makedirs("data", exist_ok=True)

    rows = fetch_csv(RKI_LK_CSV)

    # We aggregate by (date, Landkreis_id) across age groups 00-04 and 05-14
    agg = defaultdict(lambda: {"pop": 0, "cases_7d": 0})
    dates = set()

    for r in rows:
        date = (r.get("Meldedatum") or "").strip()
        lk = (r.get("Landkreis_id") or "").strip()
        age = (r.get("Altersgruppe") or "").strip()

        if not date or not lk or age not in AGE_GROUPS:
            continue

        pop = safe_int(r.get("Bevoelkerung"))
        c7 = safe_int(r.get("Faelle_7-Tage"))

        if pop is None or c7 is None:
            continue

        key = (date, lk)
        agg[key]["pop"] += pop
        agg[key]["cases_7d"] += c7
        dates.add(date)

    if not dates:
        print("No data after filtering. Check source format.", file=sys.stderr)
        sys.exit(1)

    # Determine latest date
    latest_date = max(dates)
    latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")

    # Build time window
    start_dt = latest_dt - timedelta(days=DAYS_BACK - 1)
    start_date = start_dt.strftime("%Y-%m-%d")

    # Prepare time series per district
    series = defaultdict(list)
    for (date, lk), v in agg.items():
        if date < start_date or date > latest_date:
            continue
        inc = calc_incidence(v["cases_7d"], v["pop"])
        series[lk].append({
            "date": date,
            "incidence_7d": None if inc is None else round(inc, 2)
        })

    # Sort each series by date
    for lk in list(series.keys()):
        series[lk].sort(key=lambda x: x["date"])

    # Build latest values + trend vs previous week (7 days earlier)
    latest_values = {}
    for lk in series.keys():
        # Need exact matching dates for trend
        pts = {p["date"]: p["incidence_7d"] for p in series[lk]}
        v_latest = agg.get((latest_date, lk))
        if not v_latest:
            continue

        inc_latest = calc_incidence(v_latest["cases_7d"], v_latest["pop"])
        inc_latest = None if inc_latest is None else round(inc_latest, 2)

        # previous week incidence (date - 7)
        prev_dt = latest_dt - timedelta(days=7)
        prev_date = prev_dt.strftime("%Y-%m-%d")
        inc_prev = pts.get(prev_date)

        trend = pct_change(inc_latest, inc_prev)
        trend = None if trend is None else round(trend, 1)

        latest_values[lk] = {
            "incidence_7d": inc_latest,
            "cases_7d": int(v_latest["cases_7d"]),
            "trend_pct": trend
        }

    # Metric min/max for styling
    metric_meta = {}
    for metric in ["incidence_7d", "cases_7d", "trend_pct"]:
        vals = []
        for lk, v in latest_values.items():
            x = v.get(metric)
            if isinstance(x, (int, float)) and math.isfinite(x):
                vals.append(float(x))
        if vals:
            metric_meta[metric] = {"min": min(vals), "max": max(vals)}
        else:
            metric_meta[metric] = {"min": 0.0, "max": 1.0}

    latest_out = {
        "updated_at": latest_date,
        "notes": "Combined ages 00-04 and 05-14 (0-14).",
        "metric_meta": metric_meta,
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

if __name__ == "__main__":
    main()