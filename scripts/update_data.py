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
    """
    Normalize Landkreis_id to a 5-digit key (with leading zeros).
    Examples:
      '6533' -> '06533'
      '01001' -> '01001'
    """
    if lk_raw is None:
        return ""
    s = str(lk_raw).strip()

    # keep digits only (defensive)
    s = "".join(ch for ch in s if ch.isdigit())
    if not s:
        return ""

    # Some datasets might provide longer codes; take first 5
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
    """Return the first matching field value for possible column name variants."""
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    return ""


def main():
    os.makedirs("data", exist_ok=True)

    rows = fetch_csv(RKI_LK_CSV)
    if not rows:
        print("CSV returned no rows.", file=sys.stderr)
        sys.exit(1)

    # Aggregate by (date, lk) across age groups 00-04 and 05-14
    agg = defaultdict(lambda: {"pop": 0, "cases_7d": 0})
    dates = set()

    for r in rows:
        date = get_field(r, "Meldedatum", "Datum").strip()

        lk_raw = get_field(r, "Landkreis_id", "Landkreis ID", "LK_ID", "IdLandkreis").strip()
        lk = normalize_lk(lk_raw)

        age = get_field(r, "Altersgruppe", "Altergruppe", "AgeGroup").strip()

        # Column variants for population/cases
        pop_raw = get_field(r, "Bevoelkerung", "Bevölkerung", "Population").strip()
        c7_raw = get_field(r, "Faelle_7-Tage", "Faelle_7_Tage", "Fälle_7-Tage", "Cases_7d").strip()

        if not date or not lk or age not in AGE_GROUPS:
            continue

        pop = safe_int(pop_raw)
        c7 = safe_int(c7_raw)
        if pop is None or c7 is None:
            continue

        key = (date, lk)
        agg[key]["pop"] += pop
        agg[key]["cases_7d"] += c7
        dates.add(date)

    if not dates:
        print(
            "No data after filtering.\n"
            "Likely causes:\n"
            "- Age group labels differ from {'00-04','05-14'}\n"
            "- Column names changed\n"
            "- Landkreis_id missing\n",
            file=sys.stderr,
        )
        sys.exit(1)

    latest_date = max(dates)
    latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")

    start_dt = latest_dt - timedelta(days=DAYS_BACK - 1)
    start_date = start_dt.strftime("%Y-%m-%d")

    # time series per lk
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

    # latest values + trend vs previous week
    latest_values = {}
    prev_dt = latest_dt - timedelta(days=7)
    prev_date = prev_dt.strftime("%Y-%m-%d")

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

    metric_meta = {}
    for metric in ["incidence_7d", "cases_7d", "trend_pct"]:
        vals = []
        for _, v in latest_values.items():
            x = v.get(metric)
            if isinstance(x, (int, float)) and math.isfinite(x):
                vals.append(float(x))
        metric_meta[metric] = {"min": min(vals), "max": max(vals)} if vals else {"min": 0.0, "max": 1.0}

    latest_out = {
        "updated_at": latest_date,
        "notes": "Combined ages 00-04 and 05-14 (0-14). Landkreis_id normalized to 5 digits.",
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
    print(f"Districts in latest: {len(latest_values)}")


if __name__ == "__main__":
    main()