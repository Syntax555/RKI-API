#!/usr/bin/env python3
import csv
import json
import math
import os
import sys
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from urllib.request import urlopen, Request

RKI_LK_CSV = (
    "https://raw.githubusercontent.com/robert-koch-institut/"
    "COVID-19_7-Tage-Inzidenz_in_Deutschland/main/"
    "COVID-19-Faelle_7-Tage-Inzidenz_Landkreise.csv"
)

OUT_LATEST = "data/latest.json"
OUT_SERIES = "data/timeseries.json"

# we'll discover actual labels; these are common expected values
TARGET_AGE_GROUPS = {"00-04", "05-14"}
DAYS_BACK = 60


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


def get_field(row: dict, *names: str) -> str:
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    return ""


def main():
    os.makedirs("data", exist_ok=True)

    rows = fetch_csv(RKI_LK_CSV)
    if not rows:
        print("ERROR: CSV returned no rows.", file=sys.stderr)
        sys.exit(1)

    # --- Diagnostics: print headers + some stats
    headers = list(rows[0].keys())
    print("CSV headers:", headers[:40], "..." if len(headers) > 40 else "")
    print("Total CSV rows:", len(rows))

    age_counter = Counter()
    lk_sample = []
    date_sample = []

    # Aggregate by (date, lk) across target age groups
    agg = defaultdict(lambda: {"pop": 0, "cases_7d": 0})
    dates = set()

    passed = 0
    missing_cols = 0

    for r in rows:
        date = get_field(r, "Meldedatum", "Datum").strip()
        lk_raw = get_field(r, "Landkreis_id", "Landkreis ID", "LK_ID", "IdLandkreis").strip()
        age = get_field(r, "Altersgruppe", "Altergruppe", "AgeGroup").strip()

        pop_raw = get_field(r, "Bevoelkerung", "Bevölkerung", "Population").strip()
        c7_raw = get_field(r, "Faelle_7-Tage", "Faelle_7_Tage", "Fälle_7-Tage", "Cases_7d").strip()

        if age:
            age_counter[age] += 1

        if lk_raw and len(lk_sample) < 5:
            lk_sample.append(lk_raw)
        if date and len(date_sample) < 5:
            date_sample.append(date)

        if not date or not lk_raw or not age:
            missing_cols += 1
            continue

        lk = normalize_lk(lk_raw)

        if age not in TARGET_AGE_GROUPS:
            continue

        pop = safe_int(pop_raw)
        c7 = safe_int(c7_raw)
        if pop is None or c7 is None:
            continue

        key = (date, lk)
        agg[key]["pop"] += pop
        agg[key]["cases_7d"] += c7
        dates.add(date)
        passed += 1

    print("Sample Landkreis_id values:", lk_sample)
    print("Sample dates:", date_sample)
    print("Top age groups in file:", age_counter.most_common(10))
    print("Rows passing filter (target ages + required cols):", passed)

    if not dates:
        print(
            "\nERROR: No data after filtering.\n"
            "Most likely: age labels are not exactly '00-04' and '05-14'.\n"
            "Look at 'Top age groups' above and update TARGET_AGE_GROUPS.\n",
            file=sys.stderr
        )
        sys.exit(1)

    latest_date = max(dates)
    latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")

    start_dt = latest_dt - timedelta(days=DAYS_BACK - 1)
    start_date = start_dt.strftime("%Y-%m-%d")

    # time series per district
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

    latest_values = {}
    prev_date = (latest_dt - timedelta(days=7)).strftime("%Y-%m-%d")

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

    if not latest_values:
        print("ERROR: latest_values is empty after processing.", file=sys.stderr)
        sys.exit(1)

    metric_meta = {}
    for metric in ["incidence_7d", "cases_7d", "trend_pct"]:
        vals = []
        for v in latest_values.values():
            x = v.get(metric)
            if isinstance(x, (int, float)) and math.isfinite(x):
                vals.append(float(x))
        metric_meta[metric] = {"min": min(vals), "max": max(vals)} if vals else {"min": 0.0, "max": 1.0}

    latest_out = {
        "updated_at": latest_date,
        "notes": "Combined two age groups from source. Landkreis_id normalized to 5 digits.",
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
    print("Districts in latest:", len(latest_values))


if __name__ == "__main__":
    main()