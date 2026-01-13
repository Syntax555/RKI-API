import csv, json, urllib.request, datetime

RKI_URL = (
    "https://raw.githubusercontent.com/robert-koch-institut/"
    "COVID-19_7-Tage-Inzidenz_in_Deutschland/main/"
    "COVID-19-Faelle_7-Tage-Inzidenz_Landkreise.csv"
)

OUT = "docs/data/covid_7day_latest.json"

def norm_ags(x: str) -> str:
    x = (x or "").strip()
    return x.zfill(5) if x.isdigit() else x

def main():
    with urllib.request.urlopen(RKI_URL) as resp:
        text = resp.read().decode("utf-8", errors="replace").splitlines()

    reader = csv.DictReader(text)

    # We want the latest date available in the file, for overall age group (00+)
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
        raise SystemExit("No date found in dataset")

    values = []
    for r in rows:
        if (r.get("Meldedatum") or "").strip() != max_date:
            continue

        ags = norm_ags(r.get("Landkreis_id") or r.get("IdLandkreis") or "")
        if not ags:
            continue

        inc = r.get("Inzidenz_7-Tage") or r.get("Inzidenz_7_Tage") or ""
        cases = r.get("Faelle_7-Tage") or r.get("Faelle_7_Tage") or ""

        def to_float(s):
            s = (s or "").strip().replace(",", ".")
            return float(s) if s else None

        values.append({
            "region_id": ags,
            "incidence_7d_per_100k": to_float(inc),
            "cases_7d": to_float(cases),
        })

    payload = {
        "signal": "COVID_7DAY",
        "date": max_date,
        "generated_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "values": values,
        "source": "RKI COVID-19 7-day incidence (counties)",
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    print(f"Wrote {OUT} with {len(values)} counties for {max_date}")

if __name__ == "__main__":
    main()