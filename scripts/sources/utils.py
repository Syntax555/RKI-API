import json, os, math
from urllib.request import Request, urlopen

def fetch_csv(url: str) -> list[dict]:
    req = Request(url, headers={"User-Agent": "kids-risk-map/1.0"})
    with urlopen(req) as r:
        return list(csv.DictReader(r.read().decode("utf-8").splitlines()))

def write_json(path: str, obj: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

def metric_min_max(values: dict, metric: str) -> dict:
    vals = [v[metric] for v in values.values()
            if isinstance(v.get(metric), (int, float)) and math.isfinite(v[metric])]
    return {"min": min(vals), "max": max(vals)} if vals else {"min": 0, "max": 1}

