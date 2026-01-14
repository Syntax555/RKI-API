#!/usr/bin/env python3
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.request import urlopen, Request

# --- Sources (RKI Open Data on GitHub) ---
RKI_COVID_LK_CSV = (
    "https://raw.githubusercontent.com/robert-koch-institut/"
    "COVID-19_7-Tage-Inzidenz_in_Deutschland/main/"
    "COVID-19-Faelle_7-Tage-Inzidenz_Landkreise.csv"
)

RKI_INFLUENZA_TSV = (
    "https://raw.githubusercontent.com/robert-koch-institut/"
    "Influenzafaelle_in_Deutschland/main/"
    "IfSG_Influenzafaelle.tsv"
)

RKI_RSV_TSV = (
    "https://raw.githubusercontent.com/robert-koch-institut/"
    "Respiratorische_Synzytialvirusfaelle_in_Deutschland/main/"
    "IfSG_RSVfaelle.tsv"
)

# --- Output layout ---
OUT_INDEX = "data/diseases/index.json"
OUT_ROOT = "data/diseases"

# --- Windows ---
COVID_DAYS_BACK = 60      # daily points
WEEKLY_WEEKS_BACK = 104   # weekly points (2 years)

# --- Helpers ---
def safe_int(x):
    try:
        return int(float(str(x).strip()))
    except Exception:
        return None

def safe_float(x):
    try:
        s = str(x).strip()
        if s.upper() == "NA" or s == "":
            return None
        return float(s)
    except Exception:
        return None

def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "kids-risk-map/1.0 (github pages)"})
    with urlopen(req) as r:
        return r.read().decode("utf-8")

def fetch_csv_rows(url: str) -> list[dict]:
    raw = fetch_text(url)
    return list(csv.DictReader(raw.splitlines()))

def fetch_tsv_rows(url: str) -> list[dict]:
    raw = fetch_text(url)
    return list(csv.DictReader(raw.splitlines(), delimiter="\t"))

def normalize_lk(lk_raw: str) -> str:
    if lk_raw is None:
        return ""
    s = "".join(ch for ch in str(lk_raw).strip() if ch.isdigit())
    if not s:
        return ""
    if len(s) > 5:
        s = s[:5]
    return s.zfill(5)

def lk_to_state_id(lk5: str) -> str:
    # Kreis key is 5 digits; first two digits are Bundesland ID (01..16)
    if not lk5 or len(lk5) < 2:
        return ""
    return lk5[:2]

def metric_min_max(values: dict, metric: str) -> dict:
    vals = []
    for v in values.values():
        x = v.get(metric)
        if isinstance(x, (int, float)) and math.isfinite(x):
            vals.append(float(x))
    return {"min": min(vals), "max": max(vals)} if vals else {"min": 0.0, "max": 1.0}

def write_json(path: str, obj: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return ((new - old) / old) * 100.0

def calc_incidence(cases_7d: int, population: int) -> float | None:
    if cases_7d is None or population is None or population <= 0:
        return None
    return (cases_7d / population) * 100000.0

# --- Builders ---
def build_covid_landkreis():
    rows = fetch_csv_rows(RKI_COVID_LK_CSV)
    if not rows:
        raise RuntimeError("COVID CSV returned no rows")

    agg = defaultdict(lambda: {"pop": 0, "cases_7d": 0})
    dates = set()

    for r in rows:
        date = (r.get("Meldedatum") or "").strip()
        lk = normalize_lk((r.get("Landkreis_id") or "").strip())
        pop = safe_int(r.get("Bevoelkerung"))
        c7 = safe_int(r.get("Faelle_7-Tage"))

        if not date or not lk or pop is None or c7 is None:
            continue

        agg[(date, lk)]["pop"] += pop
        agg[(date, lk)]["cases_7d"] += c7
        dates.add(date)

    if not dates:
        raise RuntimeError("No dates found in COVID CSV")

    latest_date = max(dates)
    latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
    start_date = (latest_dt - timedelta(days=COVID_DAYS_BACK - 1)).strftime("%Y-%m-%d")

    series = defaultdict(list)
    for (date, lk), v in agg.items():
        if date < start_date or date > latest_date:
            continue
        inc = calc_incidence(v["cases_7d"], v["pop"])
        series[lk].append({"date": date, "incidence_7d": None if inc is None else round(inc, 2)})

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
            "trend_pct": trend,
        }

    latest_out = {
        "updated_at": latest_date,
        "notes": "COVID-19 Landkreis-level. This RKI CSV has no age breakdown; values are total population.",
        "metric_meta": {
            "incidence_7d": metric_min_max(latest_values, "incidence_7d"),
            "cases_7d": metric_min_max(latest_values, "cases_7d"),
            "trend_pct": metric_min_max(latest_values, "trend_pct"),
        },
        "values": latest_values,
    }

    series_out = {
        "updated_at": latest_date,
        "window_days": COVID_DAYS_BACK,
        "series": series,
    }

    base = os.path.join(OUT_ROOT, "covid")
    write_json(os.path.join(base, "latest.json"), latest_out)
    write_json(os.path.join(base, "timeseries.json"), series_out)

    return {
        "id": "covid",
        "label": "COVID-19 (RKI Landkreis, total population)",
        "metrics": ["incidence_7d", "cases_7d", "trend_pct"],
        "resolution": "landkreis",
    }

def _iso_week_to_sort_key(week: str) -> tuple[int, int]:
    # "YYYY-Www"
    y, w = week.split("-W")
    return (int(y), int(w))

def build_weekly_state_dataset(
    *,
    disease_id: str,
    label: str,
    tsv_url: str,
    age_groups: list[str],   # <-- CHANGED (list!)
    note: str,
):
    rows = fetch_tsv_rows(tsv_url)
    if not rows:
        raise RuntimeError(f"{disease_id}: TSV returned no rows")

    # Expected columns:
    # Meldewoche, Region, Region_Id, Altersgruppe, Fallzahl, Inzidenz
    by_week_state = defaultdict(lambda: {"cases": 0, "inc": []})
    weeks = set()

    for r in rows:
        week = (r.get("Meldewoche") or "").strip()
        state_id = (r.get("Region_Id") or "").strip()
        age = (r.get("Altersgruppe") or "").strip()

        if not week or not state_id or state_id in ("00", "NA"):
            continue
        if age not in age_groups:
            continue

        cases = safe_int(r.get("Fallzahl"))
        inc = safe_float(r.get("Inzidenz"))

        if cases is None:
            continue

        k = (week, state_id)
        by_week_state[k]["cases"] += cases
        if inc is not None:
            by_week_state[k]["inc"].append(inc)

        weeks.add(week)

    if not weeks:
        raise RuntimeError(
            f"{disease_id}: no rows after filtering for age_groups={age_groups}"
        )

    def week_key(w):
        y, wk = w.split("-W")
        return (int(y), int(wk))

    weeks_sorted = sorted(weeks, key=week_key)
    latest_week = weeks_sorted[-1]
    keep_weeks = set(weeks_sorted[-WEEKLY_WEEKS_BACK:])
    
    # Build per-state series
    state_series = defaultdict(list)
    for (week, state_id), v in by_week_state.items():
        if week not in keep_weeks:
            continue

        # Average incidence if multiple age bands were combined
        inc_val = None
        if v["inc"]:
            inc_val = sum(v["inc"]) / len(v["inc"])

        state_series[state_id].append({
            "date": week,
            "incidence_7d": None if inc_val is None else round(inc_val, 2),
            "cases_7d": int(v["cases"]),
        })

    for sid in state_series:
        state_series[sid].sort(key=lambda x: week_key(x["date"]))

    # Trend vs previous week
    prev_week = weeks_sorted[-2] if len(weeks_sorted) >= 2 else None
    state_latest = {}

    for sid, pts in state_series.items():
        cur = next((p for p in pts if p["date"] == latest_week), None)
        prev = next((p for p in pts if p["date"] == prev_week), None) if prev_week else None

        inc_latest = cur["incidence_7d"] if cur else None
        inc_prev = prev["incidence_7d"] if prev else None

        trend = pct_change(inc_latest, inc_prev)
        trend = None if trend is None else round(trend, 1)

        state_latest[sid] = {
            "incidence_7d": inc_latest,
            "cases_7d": cur["cases_7d"] if cur else None,
            "trend_pct": trend,
        }

    values = {f"STATE:{sid}": v for sid, v in state_latest.items()}
    series = {f"STATE:{sid}": pts for sid, pts in state_series.items()}

    latest_out = {
        "updated_at": latest_week,
        "notes": note,
        "metric_meta": {
            "incidence_7d": metric_min_max(values, "incidence_7d"),
            "cases_7d": metric_min_max(values, "cases_7d"),
            "trend_pct": metric_min_max(values, "trend_pct"),
        },
        "values": values,
        "resolution": "bundesland",
        "age_group": "+".join(age_groups),
    }

    series_out = {
        "updated_at": latest_week,
        "window_days": WEEKLY_WEEKS_BACK * 7,
        "series": series,
        "resolution": "bundesland",
        "age_group": "+".join(age_groups),
    }

    base = os.path.join(OUT_ROOT, disease_id)
    write_json(os.path.join(base, "latest.json"), latest_out)
    write_json(os.path.join(base, "timeseries.json"), series_out)

    return {
        "id": disease_id,
        "label": label,
        "metrics": ["incidence_7d", "cases_7d", "trend_pct"],
        "resolution": "bundesland",
        "age_group": "+".join(age_groups),
    }


def main():
    os.makedirs(OUT_ROOT, exist_ok=True)

    diseases = []
    diseases.append(build_covid_landkreis())

    diseases.append(build_weekly_state_dataset(
        disease_id="influenza",
        label="Influenza (RKI IfSG, Bundesland, children 0–14)",
        tsv_url=RKI_INFLUENZA_TSV,
        age_groups=["0-4", "5-14", "00-04", "00-14"],
        note="Influenza weekly IfSG data, Bundesland-level. Children 0–14 years combined.",
    ))

    diseases.append(build_weekly_state_dataset(
        disease_id="rsv",
        label="RSV (RKI IfSG, Bundesland, babies 0–4)",
        tsv_url=RKI_RSV_TSV,
        age_groups=["0-4", "00-04"],
        note="RSV weekly IfSG data, Bundesland-level. Babies and toddlers (0–4 years).",
    ))


    index = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "diseases": diseases,
    }
    write_json(OUT_INDEX, index)

    print("Wrote:")
    print(" -", OUT_INDEX)
    for d in diseases:
        print(" -", f"{OUT_ROOT}/{d['id']}/latest.json")
        print(" -", f"{OUT_ROOT}/{d['id']}/timeseries.json")

if __name__ == "__main__":
    main()
