import csv
import datetime as dt
import httpx
from dateutil import tz
from app.db import conn
from app.settings import settings

BERLIN_TZ = tz.gettz("Europe/Berlin")

def now_iso() -> str:
    return dt.datetime.now(tz=BERLIN_TZ).replace(microsecond=0).isoformat()

async def download_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": "baby-health-blackbox/1.0"}) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text

def upsert_signal(*, signal: str, metric: str, region_id: str, date: str, value: float, source: str):
    with conn() as c:
        c.execute(
            """
            INSERT INTO signals(signal, metric, region_id, date, value, source, updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(signal, metric, region_id, date)
            DO UPDATE SET value=excluded.value, source=excluded.source, updated_at=excluded.updated_at
            """,
            (signal, metric, region_id, date, value, source, now_iso()),
        )

async def cache_get(key: str) -> str | None:
    with conn() as c:
        row = c.execute("SELECT value FROM cache WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

async def cache_set(key: str, value: str):
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache(key, value, updated_at) VALUES(?,?,?)",
            (key, value, now_iso()),
        )

async def get_counties_geojson_cached() -> str:
    """
    Returns county GeoJSON (Landkreise). Cached in DB to keep frontend fast.
    Source catalog: Germany: 2020 Kreise.  [oai_citation:7‡ckan.open.nrw.de](https://ckan.open.nrw.de/dataset/deutschland-2020-kreise-ne)
    """
    key = "geojson_counties"
    cached = await cache_get(key)
    if cached:
        return cached

    text = await download_text(settings.counties_geojson_url)
    await cache_set(key, text)
    return text

def _normalize_ags(raw: str) -> str:
    # AGS is 5 digits for counties; sometimes leading zeros are needed.
    raw = (raw or "").strip()
    if raw.isdigit():
        return raw.zfill(5)
    return raw

async def ingest_rki_covid_7day_counties():
    """
    Ingest RKI COVID 7-day incidence/cases for counties.
    CSV file is in the official RKI repository.  [oai_citation:8‡GitHub](https://github.com/robert-koch-institut/COVID-19_7-Tage-Inzidenz_in_Deutschland)

    Columns (typical): Meldedatum, Landkreis_id, Altersgruppe, Faelle_7-Tage, Inzidenz_7-Tage, ...
    We keep only Altersgruppe "00+" (overall), so the map is simple by default.
    """
    text = await download_text(settings.rki_covid_7day_counties_csv_url)

    reader = csv.DictReader(text.splitlines())
    for r in reader:
        age = (r.get("Altersgruppe") or "").strip()
        if age and age != "00+":
            continue

        date = (r.get("Meldedatum") or "").strip()  # ISO date
        if not date:
            continue

        county_id = _normalize_ags(r.get("Landkreis_id") or r.get("IdLandkreis") or "")
        if not county_id:
            continue

        # metrics
        inc = r.get("Inzidenz_7-Tage") or r.get("Inzidenz_7_Tage") or ""
        cases7 = r.get("Faelle_7-Tage") or r.get("Faelle_7_Tage") or ""

        if inc:
            try:
                upsert_signal(
                    signal="COVID_7DAY",
                    metric="incidence_7d_per_100k",
                    region_id=county_id,
                    date=date,
                    value=float(inc.replace(",", ".")),
                    source="RKI COVID 7-day incidence (counties)"
                )
            except ValueError:
                pass

        if cases7:
            try:
                upsert_signal(
                    signal="COVID_7DAY",
                    metric="cases_7d",
                    region_id=county_id,
                    date=date,
                    value=float(cases7.replace(",", ".")),
                    source="RKI COVID 7-day incidence (counties)"
                )
            except ValueError:
                pass

async def run_full_ingest():
    await ingest_rki_covid_7day_counties()
    await get_counties_geojson_cached()