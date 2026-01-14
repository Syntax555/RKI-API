def build():
    ...
    return {
        "id": "covid",
        "label": "COVID-19 (RKI, Landkreis)",
        "metrics": ["incidence_7d", "cases_7d", "trend_pct"],
        "latest": latest_out,
        "timeseries": series_out
    }
