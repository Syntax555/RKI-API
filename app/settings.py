from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    db_path: str = "data.sqlite3"

    # RKI: County-level COVID 7-day incidence CSV
    # Repo contains: COVID-19-Faelle_7-Tage-Inzidenz_Landkreise.csv  [oai_citation:3‡GitHub](https://github.com/robert-koch-institut/COVID-19_7-Tage-Inzidenz_in_Deutschland)
    rki_covid_7day_counties_csv_url: str = (
        "https://raw.githubusercontent.com/robert-koch-institut/"
        "COVID-19_7-Tage-Inzidenz_in_Deutschland/main/"
        "COVID-19-Faelle_7-Tage-Inzidenz_Landkreise.csv"
    )

    # County boundaries (GeoJSON) – derived from BKG VG250, served via an Open.NRW catalog entry  [oai_citation:4‡ckan.open.nrw.de](https://ckan.open.nrw.de/dataset/deutschland-2020-kreise-ne)
    # (Direct GeoJSON export endpoint; if it ever changes, you only update this URL)
    counties_geojson_url: str = (
        "https://opendata.rhein-kreis-neuss.de/api/v2/catalog/datasets/"
        "kreise-vintagemillesime-germany/exports/geojson"
    )

settings = Settings()