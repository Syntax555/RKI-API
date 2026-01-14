import csv
import json
import datetime as dt
import requests

OUT_COVID = "docs/data/signals/covid_7day_latest.json"
OUT_RSV = "docs/data/signals/rsv_state_latest.json"
OUT_FLU = "docs/data/signals/influenza_state_latest.json"

# RKI GitHub raw URLs (official RKI org)
COVID_URL = (
    "https://raw.githubusercontent.com/robert-koch-institut/"
    "COVID-19_7-Tage-Inzidenz_in_Deutschland/main/"
    "COVID-19-Faelle_7-Tage-Inzidenz_Landkreise.csv"
)
RSV_URL = (
    "https://raw.githubusercontent.com/robert-koch-institut/"
    "Respiratorische_Synzytialvirusfaelle_in_Deutschland/main/"
    "IfSG_RSVfaelle.tsv"
)
FLU_URL = (
    "https://raw.githubusercontent.com/robert-koch-institut/"
    "Influenzafaelle_in_Deutschland/main/"
    "IfSG_Influenzafaelle.tsv"
)

def fetch_text(url: str) -> str:
    r = requests.get(url, timeout=60, headers={"User-Agent": "gh-pages-health-map/1.0"})
    r.raise_for_status()
    return r.text

def norm_digits(x: str, pad: int) -> str:
    x = (x or "").strip()
    return x.zfill(pad) if x.isdigit() else x

def to_float(s: str):
    s = (s or "").strip().replace(",", ".")
    return float(s) if s else None

def write_json(path: str, payload: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

def build_covid_counties_latest():
    text = fetch_text(COVID_URL)
    reader = csv.DictReader(text.splitlines())

    rows = []
    max_date = None

    for r in reader:
        age = (r.get("Altersgruppe") or "").strip()
        if age and age != "00+":
            continue
        date = (r.get("Meldedatum") or "").strip()
        if not date:
            continue
        if (max_date is None) or (date > max_date):
            max_date = date
        rows.append(r)

    if not max_date:
        raise RuntimeError("No date found in COVID dataset")

    values = []
    for r in rows:
        if (r.get("Meldedatum") or "").strip() != max_date:
            continue

        ags = norm_digits(r.get("Landkreis_id") or r.get("IdLandkreis") or "", 5)
        if not ags:
            continue

        inc = r.get("Inzidenz_7-Tage") or r.get("Inzidenz_7_Tage") or ""
        cases7 = r.get("Faelle_7-Tage") or r.get("Faelle_7_Tage") or ""

        values.append({
            "region_id": ags,
            "incidence_7d_per_100k": to_float(inc),
            "cases_7d": to_float(cases7),
        })

    payload = {
        "signal": "COVID_7DAY",
        "level": "county",
        "date": max_date,
        "generated_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "values": values,
        "source": "RKI COVID-19 7-day incidence (counties)"
    }
    write_json(OUT_COVID, payload)

def parse_ifsg_state_weekly_latest(tsv_text: str, signal_id: str, out_path: str):
    """
    Generic parser for RKI IfSG TSVs on state-level.
    Field names vary slightly over time, so we map defensively.

    Expected columns often include:
      - Meldejahr / Jahr
      - Meldewoche / Woche
      - BundeslandId / IdBundesland
      - Fallzahl (cases)
      - Inzidenz (incidence)
      - Altersgruppe (we keep '00+' if present)
    """
    lines = [ln for ln in tsv_text.splitlines() if ln.strip()]
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        cols = ln.split("\t")
        if len(cols) != len(header):
            continue
        rows.append(dict(zip(header, cols)))

    def get(row, *keys):
        for k in keys:
            if k in row and row[k] != "":
                return row[k]
        return ""

    # Determine latest week
    latest = None  # tuple (year, week)
    filtered = []
    for r in rows:
        age = (get(r, "Altersgruppe") or "").strip()
        if age and age != "00+":
            continue

        year = get(r, "Meldejahr", "Jahr")
        week = get(r, "Meldewoche", "Woche")
        if not (year.isdigit() and week.isdigit()):
            continue
        yw = (int(year), int(week))
        if latest is None or yw > latest:
            latest = yw
        filtered.append(r)

    if latest is None:
        raise RuntimeError(f"No week found for {signal_id}")

    year, week = latest
    week_key = f"{year:04d}-W{week:02d}"

    values = []
    for r in filtered:
        year2 = get(r, "Meldejahr", "Jahr")
        week2 = get(r, "Meldewoche", "Woche")
        if not (year2.isdigit() and week2.isdigit()):
            continue
        if (int(year2), int(week2)) != latest:
            continue

        bl = get(r, "BundeslandId", "IdBundesland", "Bundesland")
        if not bl:
            continue
        rid = norm_digits(bl, 2)

        cases = get(r, "Fallzahl", "AnzahlFall", "Faelle", "Fälle")
        inc = get(r, "Inzidenz", "Inzidenz_100000", "Inzidenz_100k")

        values.append({
            "region_id": rid,
            "cases": to_float(cases),
            "incidence_per_100k": to_float(inc),
        })

    payload = {
        "signal": signal_id,
        "level": "state",
        "week": week_key,
        "generated_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "values": values,
        "source": f"RKI IfSG {signal_id} (states)"
    }
    write_json(out_path, payload)

def build_rsv_latest():
    text = fetch_text(RSV_URL)
    parse_ifsg_state_weekly_latest(text, "RSV", OUT_RSV)

def build_influenza_latest():
    text = fetch_text(FLU_URL)
    parse_ifsg_state_weekly_latest(text, "INFLUENZA", OUT_FLU)

def main():
    build_covid_counties_latest()
    build_rsv_latest()
    build_influenza_latest()
    print("Wrote latest signal JSON files.")

if __name__ == "__main__":
    main()