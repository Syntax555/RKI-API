#!/usr/bin/env python3
import csv
import json
import math
import os
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

# -----------------------
# helpers
# -----------------------
def safe_int(x):
    try:
        return int(float(str(x).strip()))
    except Exception:
        return None

def safe_float(x):
    try:
        s = str(x).strip()
        if s == "" or s.upper() == "NA":
            return None
        return float(s)
    except Exception:
        return None

def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "kids-risk-map/1.0 (github pages)"})
    with urlopen(req) as r:
        # utf-8-sig strips BOM if present (common in TSV exports)
        return r.read().decode("utf-8-sig", errors="replace")

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

def norm_age(s: str) -> str:
    # normalize various dash types and spacing
    if s is None:
        return ""
    s = str(s).strip()
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = s.replace(" ", "")
    return s

def _iso_week_to_sort_key(week: str) -> tuple[int, int]:
    # accepts "YYYY-Www"
    y, w = week.split("-W")
    return (int(y), int(w))

# -----------------------
# builders
# -----------------------
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
        "resolution": "landkreis",
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
        "resolution": "landkreis",
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

def build_weekly_state_dataset(
    *,
    disease_id: str,
    label: str,
    tsv_url: str,
    target_age_groups: list[str],
    note: str,
):
    rows = fetch_tsv_rows(tsv_url)
    if not rows:
        raise RuntimeError(f"{disease_id}: TSV returned no rows")

    # column detection
    WEEK_COLS = ["Meldewoche", "Meldwoche", "Week"]
    REGION_ID_COLS = ["Region_Id", "Region_ID", "RegionId"]
    AGE_COLS = ["Altersgruppe", "Altergruppe", "AgeGroup"]
    CASES_COLS = ["Fallzahl", "Faelle", "Fälle", "Cases"]
    INC_COLS = ["Inzidenz", "Inzidenz_7Tage", "Incidence"]

    def pick(row, cols):
        for c in cols:
            if c in row and row[c] not in (None, ""):
                return row[c]
        return ""

    # detect age column + available ages
    age_present = any(c in rows[0] for c in AGE_COLS)
    available_ages = set()

    if age_present:
        for r in rows:
            a = norm_age(pick(r, AGE_COLS))
            if a:
                available_ages.add(a)

    wanted = {norm_age(a) for a in target_age_groups if norm_age(a)}

    # --- AGE SELECTION STRATEGY ---
    if age_present and wanted & available_ages:
        # preferred: desired child groups exist
        selected_ages = wanted & available_ages
        age_mode = "filtered"
    elif age_present and "00+" in available_ages:
        # fallback: total population
        selected_ages = {"00+"}
        age_mode = "fallback-total"
    else:
        # final fallback: do not filter by age
        selected_ages = None
        age_mode = "unfiltered"

    by_week_state = defaultdict(lambda: {"inc": None, "cases": 0})
    weeks = set()

    for r in rows:
        week = pick(r, WEEK_COLS).strip()
        state_id = pick(r, REGION_ID_COLS).strip()
        age = norm_age(pick(r, AGE_COLS)) if age_present else ""

        if not week or not state_id or state_id in ("00", "NA"):
            continue

        if selected_ages is not None and age not in selected_ages:
            continue

        cases = safe_int(pick(r, CASES_COLS))
        inc = safe_float(pick(r, INC_COLS))

        if cases is None:
            continue

        k = (week, state_id)
        by_week_state[k]["cases"] += cases
        if inc is not None:
            by_week_state[k]["inc"] = inc
        weeks.add(week)

    if not weeks:
        raise RuntimeError(f"{disease_id}: no usable rows after age selection")

    weeks_sorted = sorted(weeks, key=_iso_week_to_sort_key)
    latest_week = weeks_sorted[-1]
    prev_week = weeks_sorted[-2] if len(weeks_sorted) > 1 else None
    keep_weeks = set(weeks_sorted[-WEEKLY_WEEKS_BACK:])

    state_series = defaultdict(list)
    for (week, state_id), v in by_week_state.items():
        if week not in keep_weeks:
            continue
        state_series[state_id].append({
            "date": week,
            "incidence_7d": None if v["inc"] is None else round(v["inc"], 2),
            "cases_7d": int(v["cases"]),
        })

    for sid in state_series:
        state_series[sid].sort(key=lambda x: _iso_week_to_sort_key(x["date"]))

    state_latest = {}
    for sid, pts in state_series.items():
        cur = next((p for p in pts if p["date"] == latest_week), None)
        if not cur:
            continue
        prev = next((p for p in pts if p["date"] == prev_week), None)

        trend = pct_change(
            cur["incidence_7d"],
            prev["incidence_7d"] if prev else None
        )
        trend = None if trend is None else round(trend, 1)

        state_latest[sid] = {
            "incidence_7d": cur["incidence_7d"],
            "cases_7d": cur["cases_7d"],
            "trend_pct": trend,
        }

    values = {f"STATE:{sid}": v for sid, v in state_latest.items()}
    series = {f"STATE:{sid}": pts for sid, pts in state_series.items()}

    latest_out = {
        "updated_at": latest_week,
        "notes": f"{note} (age mode: {age_mode})",
        "resolution": "bundesland",
        "age_groups_used": sorted(selected_ages) if selected_ages else None,
        "metric_meta": {
            "incidence_7d": metric_min_max(values, "incidence_7d"),
            "cases_7d": metric_min_max(values, "cases_7d"),
            "trend_pct": metric_min_max(values, "trend_pct"),
        },
        "values": values,
    }

    series_out = {
        "updated_at": latest_week,
        "window_days": WEEKLY_WEEKS_BACK * 7,
        "resolution": "bundesland",
        "age_groups_used": sorted(selected_ages) if selected_ages else None,
        "series": series,
    }

    base = os.path.join(OUT_ROOT, disease_id)
    write_json(os.path.join(base, "latest.json"), latest_out)
    write_json(os.path.join(base, "timeseries.json"), series_out)

    return {
        "id": disease_id,
        "label": label,
        "metrics": ["incidence_7d", "cases_7d", "trend_pct"],
        "resolution": "bundesland",
    }

def main():
    os.makedirs(OUT_ROOT, exist_ok=True)

    diseases = []
    diseases.append(build_covid_landkreis())

    # Influenza: try children 0–14, but fallback automatically if TSV has different age labels or no age column
    diseases.append(build_weekly_state_dataset(
        disease_id="influenza",
        label="Influenza (RKI IfSG, Bundesland, weekly)",
        tsv_url=RKI_INFLUENZA_TSV,
        target_age_groups=["00-14", "0-14", "05-14", "0-4", "00-04"],  # flexible
        note="Influenza is provided weekly on Bundesland level (Region_Id). Map colors Landkreise by their Bundesland value.",
    ))

    # RSV: best signal is babies/toddlers, but also fallback if ages differ/missing
    diseases.append(build_weekly_state_dataset(
        disease_id="rsv",
        label="RSV (RKI IfSG, Bundesland, weekly)",
        tsv_url=RKI_RSV_TSV,
        target_age_groups=["00-04", "0-4", "00-14", "0-14"],  # flexible
        note="RSV is provided weekly on Bundesland level (Region_Id). Map colors Landkreise by their Bundesland value.",
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
