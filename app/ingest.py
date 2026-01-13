import datetime as dt
import httpx
from dateutil import tz
from app.db import conn
from app.settings import settings

BERLIN_TZ = tz.gettz("Europe/Berlin")

def now_iso():
    return dt.datetime.now(tz=BERLIN_TZ).replace(microsecond=0).isoformat()

def iso_week_key(year: int, week: int) -> str:
    return f"{year:04d}-W{week:02d}"

def _split_tsv(text: str):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = lines[0].split("\t")
    for ln in lines[1:]:
        cols = ln.split("\t")
        if len(cols) != len(header):
            continue
        yield dict(zip(header, cols))

async def download_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text

def upsert_signal(*, disease: str, region_id: str, week: str, value: float, metric: str, source: str):
    with conn() as c:
        c.execute(
            """
            INSERT INTO signals(disease, region_id, week, value, metric, source, updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(disease, region_id, week, metric)
            DO UPDATE SET value=excluded.value, source=excluded.source, updated_at=excluded.updated_at
            """,
            (disease, region_id, week, value, metric, source, now_iso()),
        )

async def ingest_ifsg_influenza():
    """
    Influenza IfSG TSV: Bundeslandebene, wöchentlich.
    Datei liegt im Repo als IfSG_Influenzafaelle.tsv.  [oai_citation:6‡robert-koch-institut.github.io](https://robert-koch-institut.github.io/Influenzafaelle_in_Deutschland/?utm_source=chatgpt.com)
    """
    text = await download_text(settings.ifsg_influenza_tsv_url)
    rows = list(_split_tsv(text))

    # Feldnamen können sich ändern; wir machen defensives Mapping.
    # Typisch: "Meldewoche", "Meldejahr", "BundeslandId" oder "IdBundesland", "Inzidenz", "Fallzahl"
    for r in rows:
        year = int(r.get("Meldejahr") or r.get("Jahr") or 0)
        week = int(r.get("Meldewoche") or r.get("Woche") or 0)
        if not year or not week:
            continue

        # Bundesland-Id häufig 2-stellig ("01" ... "16") oder 1..16
        bl = r.get("BundeslandId") or r.get("IdBundesland") or r.get("Bundesland") or ""
        if not bl:
            continue
        region_id = f"{int(bl):02d}" if bl.isdigit() else bl.zfill(2)

        # cases/incidence
        cases = r.get("Fallzahl") or r.get("AnzahlFall") or r.get("Fälle") or ""
        inc = r.get("Inzidenz") or r.get("Inzidenz_100000") or ""

        wk = iso_week_key(year, week)
        if cases:
            try:
                upsert_signal(disease="INFLUENZA", region_id=region_id, week=wk,
                              value=float(cases.replace(",", ".")), metric="cases",
                              source="RKI IfSG Influenza TSV")
            except ValueError:
                pass
        if inc:
            try:
                upsert_signal(disease="INFLUENZA", region_id=region_id, week=wk,
                              value=float(inc.replace(",", ".")), metric="incidence_per_100k",
                              source="RKI IfSG Influenza TSV")
            except ValueError:
                pass

async def ingest_ifsg_rsv():
    """
    RSV IfSG TSV: Bundeslandebene, wöchentlich.
    Datei liegt im Repo als IfSG_RSVfaelle.tsv.  [oai_citation:7‡GitHub](https://github.com/robert-koch-institut/Respiratorische_Synzytialvirusfaelle_in_Deutschland?utm_source=chatgpt.com)
    """
    text = await download_text(settings.ifsg_rsv_tsv_url)
    rows = list(_split_tsv(text))

    for r in rows:
        year = int(r.get("Meldejahr") or r.get("Jahr") or 0)
        week = int(r.get("Meldewoche") or r.get("Woche") or 0)
        if not year or not week:
            continue

        bl = r.get("BundeslandId") or r.get("IdBundesland") or r.get("Bundesland") or ""
        if not bl:
            continue
        region_id = f"{int(bl):02d}" if bl.isdigit() else bl.zfill(2)

        cases = r.get("Fallzahl") or r.get("AnzahlFall") or r.get("Fälle") or ""
        inc = r.get("Inzidenz") or r.get("Inzidenz_100000") or ""

        wk = iso_week_key(year, week)
        if cases:
            try:
                upsert_signal(disease="RSV", region_id=region_id, week=wk,
                              value=float(cases.replace(",", ".")), metric="cases",
                              source="RKI IfSG RSV TSV")
            except ValueError:
                pass
        if inc:
            try:
                upsert_signal(disease="RSV", region_id=region_id, week=wk,
                              value=float(inc.replace(",", ".")), metric="incidence_per_100k",
                              source="RKI IfSG RSV TSV")
            except ValueError:
                pass

async def ingest_grippeweb_are():
    """
    GrippeWeb: bevölkerungsbasierte Schätzungen (ARE/ILI).
    Datei: GrippeWeb_Daten_des_Wochenberichts.tsv  [oai_citation:8‡GitHub](https://github.com/robert-koch-institut/GrippeWeb_Daten_des_Wochenberichts)
    Für ein MVP speichern wir (wenn vorhanden) nationale oder Regionswerte als "ARE_EST".
    """
    text = await download_text(settings.grippeweb_tsv_url)
    rows = list(_split_tsv(text))

    # In GrippeWeb gibt es mehrere Dimensionen (Alter, Region etc.).
    # Wir versuchen, pro Zeile: Jahr/Woche + RegionId zu finden.
    for r in rows:
        year = r.get("Jahr") or r.get("Meldejahr") or ""
        week = r.get("Woche") or r.get("Meldewoche") or ""
        if not (year and week and year.isdigit() and week.isdigit()):
            continue
        wk = iso_week_key(int(year), int(week))

        # region: manche Dateien haben "Region" textlich. Für die Karte brauchen wir IDs.
        # Als Blackbox speichern wir erst mal "DE" (national), falls keine ID existiert.
        region_id = (r.get("RegionId") or r.get("AGS") or "DE").strip()

        are = r.get("ARE") or r.get("ARE_Inzidenz") or r.get("ARE_pro_100000") or ""
        if are:
            try:
                upsert_signal(disease="ARE_EST", region_id=region_id, week=wk,
                              value=float(are.replace(",", ".")),
                              metric="incidence_per_100k",
                              source="RKI GrippeWeb TSV")
            except ValueError:
                pass

async def run_full_ingest():
    # Reihenfolge ist egal, aber so ist’s schön lesbar
    await ingest_ifsg_rsv()
    await ingest_ifsg_influenza()
    await ingest_grippeweb_are()

async def get_cached_geojson():
    """
    GeoJSON wird remote geladen und in cache-Tabelle gespeichert,
    damit das Frontend nicht jedes Mal ArcGIS stresst.
    """
    cache_key = "bundeslaender_geojson"
    with conn() as c:
        row = c.execute("SELECT value FROM cache WHERE key=?", (cache_key,)).fetchone()
        if row:
            return row["value"]

    text = await download_text(settings.bundeslaender_geojson_url)
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache(key, value, updated_at) VALUES(?,?,?)",
            (cache_key, text, now_iso()),
        )
    return text