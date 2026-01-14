#!/usr/bin/env python3
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.request import urlopen, Request

RKI_COVID_LK_CSV = (
    "https://raw.githubusercontent.com/robert-koch-institut/"
    "COVID-19_7-Tage-Inzidenz_in_Deutschland/main/"
    "COVID-19-Faelle_7-Tage-Inzidenz_Landkreise.csv"
)

DAYS_BACK = 60

OUT_INDEX = "data/diseases/index.json"
OUT_ROOT = "data/diseases"

def safe_int(x):
    try:
        return int(float(x))
    except Exception:
        return None

def fetch_csv(url: str) -> list[dict]:
    req = Request(url, headers={"User-Agent": "kids-risk-map/1.0 (github pages)"} )
    with urlopen(req) as r:
        raw = r.read().decode("utf-8")
    reader = csv.DictReader(raw.splitlines())
    return list(reader)

def normalize_lk(lk_raw: str) -> str:
    if lk_raw is None:
        return ""
    s = str(lk_raw).strip()
    s = "".join(ch for ch in s if ch.isdigit())
    if not s:
        return ""
    if len(s) > 5:
        s = s[:5]
    return s.zfill(5)

def calc_incidence(cases_7d: int, population: int) -> float | None:
    if cases_7d is None or population is None or population <= 0:
        return None
    return (cases_7d / population) * 100000.0

def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return ((new - old) / old) * 100.0

def metric_min_max(values: dict, metric: str) -> dict:
    vals = []
    for _, v in values.items():
        x = v.get(metric)
        if isinstance(x, (int, float)) and math.isfinite(x):
            vals.append(float(x))
    return {"min": min(vals), "max": max(vals)} if vals else {"min": 0.0, "max": 1.0}

def write_json(path: str, obj: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

def build_covid():
    rows = fetch_csv(RKI_COVID_LK_CSV)
    if not rows:
        raise RuntimeError("COVID CSV returned no rows")

    # Expected headers (no age groups here):
    # Meldedatum, Landkreis_id, Bevoelkerung, Faelle_7-Tage, Inzidenz_7-Tage, ...
    agg = defaultdict(lambda: {"pop": 0, "cases_7d": 0})
    dates = set()

    for r in rows:
        date = (r.get("Meldedatum") or "").strip()
        lk = normalize_lk((r.get("Landkreis_id") or "").strip())
        pop = safe_int((r.get("Bevoelkerung") or "").strip())
        c7 = safe_int((r.get("Faelle_7-Tage") or "").strip())

        if not date or not lk:
            continue
        if pop is None or c7 is None:
            continue

        key = (date, lk)
        agg[key]["pop"] += pop
        agg[key]["cases_7d"] += c7
        dates.add(date)

    if not dates:
        raise RuntimeError("No dates found in COVID CSV")

    latest_date = max(dates)
    latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
    start_dt = latest_dt - timedelta(days=DAYS_BACK - 1)
    start_date = start_dt.strftime("%Y-%m-%d")

    series = defaultdict(list)
    for (date, lk), v in agg.items():
        if date < start_date or date > latest_date:
            continue
        inc = calc_incidence(v["cases_7d"], v["pop"])
        series[lk].append({
            "date": date,
            "incidence_7d": None if inc is None else round(inc, 2)
        })

    for lk in list(series.keys()):
        series[lk].sort(key=lambda x: x["date"])

    prev_date = (latest_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    latest_values = {}

    for lk in series.keys():
        pts = {p["date"]: p["incidence_7d"] for p in series[lk]}
        v_latest = agg.get((latest_date, lk))
        if not v_latest:
            continue

        inc_latest = calc_incidence(v_latest["cases_7d"], v_latest["pop"])
        inc_latest = None if inc_latest is None else round(inc_latest, 2)

        inc_prev = pts.get(prev_date)
        trend = pct_change(inc_latest, inc_prev)
        trend = None if trend is None else round(trend, 1)

        latest_values[lk] = {
            "incidence_7d": inc_latest,
            "cases_7d": int(v_latest["cases_7d"]),
            "trend_pct": trend
        }

    latest_out = {
        "updated_at": latest_date,
        "notes": "COVID-19 Landkreis-level. This RKI CSV has no age breakdown; values are total population.",
        "metric_meta": {
            "incidence_7d": metric_min_max(latest_values, "incidence_7d"),
            "cases_7d": metric_min_max(latest_values, "cases_7d"),
            "trend_pct": metric_min_max(latest_values, "trend_pct"),
        },
        "values": latest_values
    }

    series_out = {
        "updated_at": latest_date,
        "window_days": DAYS_BACK,
        "series": series
    }

    base = os.path.join(OUT_ROOT, "covid")
    write_json(os.path.join(base, "latest.json"), latest_out)
    write_json(os.path.join(base, "timeseries.json"), series_out)

    return {
        "id": "covid",
        "label": "COVID-19 (RKI Landkreis, total)",
        "metrics": ["incidence_7d", "cases_7d", "trend_pct"]
    }

def main():
    os.makedirs(OUT_ROOT, exist_ok=True)

    diseases = []
    try:
        diseases.append(build_covid())
    except Exception as e:
        print("Failed to build covid dataset:", e, file=sys.stderr)
        raise

    index = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "diseases": diseases
    }
    write_json(OUT_INDEX, index)

    print("Wrote:")
    print(" -", OUT_INDEX)
    for d in diseases:
        print(" -", f"{OUT_ROOT}/{d['id']}/latest.json")
        print(" -", f"{OUT_ROOT}/{d['id']}/timeseries.json")

if __name__ == "__main__":
    main()
