from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    db_path: str = "data.sqlite3"
    # RKI Open Data (TSV)
    grippeweb_tsv_url: str = (
        "https://raw.githubusercontent.com/robert-koch-institut/"
        "GrippeWeb_Daten_des_Wochenberichts/main/GrippeWeb_Daten_des_Wochenberichts.tsv"
    )
    ifsg_influenza_tsv_url: str = (
        "https://raw.githubusercontent.com/robert-koch-institut/"
        "Influenzafaelle_in_Deutschland/main/IfSG_Influenzafaelle.tsv"
    )
    ifsg_rsv_tsv_url: str = (
        "https://raw.githubusercontent.com/robert-koch-institut/"
        "Respiratorische_Synzytialvirusfaelle_in_Deutschland/main/IfSG_RSVfaelle.tsv"
    )

    # Bundesländer als GeoJSON (ArcGIS REST, GeoJSON output)
    # Hinweis: Das ist ein FeatureLayer, der geoJSON unterstützt.
    bundeslaender_geojson_url: str = (
        "https://geoportal.bafg.de/arcgis/rest/services/BFG/Bundeslaender/MapServer/0/query"
        "?where=1%3D1&outFields=*&f=geojson"
    )

settings = Settings()