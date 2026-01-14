from datetime import datetime
from sources.covid import build as build_covid
from sources.utils import write_json

OUT_ROOT = "data/diseases"

def main():
    datasets = [build_covid()]

    index = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "diseases": []
    }

    for d in datasets:
        base = f"{OUT_ROOT}/{d['id']}"
        write_json(f"{base}/latest.json", d["latest"])
        write_json(f"{base}/timeseries.json", d["timeseries"])

        index["diseases"].append({
            "id": d["id"],
            "label": d["label"],
            "metrics": d["metrics"]
        })

    write_json(f"{OUT_ROOT}/index.json", index)

if __name__ == "__main__":
    main()
