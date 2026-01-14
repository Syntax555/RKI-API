import json
import math

COUNTY_TOPO = "docs/data/boundaries/counties.topo.json"
STATE_TOPO = "docs/data/boundaries/states.topo.json"

OUT_COUNTY = "docs/data/lookups/county_centroids.json"
OUT_STATE = "docs/data/lookups/state_centroids.json"

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)

def normalize_digits(x, pad):
    s = str(x).strip()
    return s.zfill(pad) if s.isdigit() else s

def decode_arc(arc, transform):
    # arc is a list of [dx, dy] points; convert to absolute coords.
    scale = transform["scale"]
    translate = transform["translate"]
    x = 0
    y = 0
    pts = []
    for dx, dy in arc:
        x += dx
        y += dy
        lon = x * scale[0] + translate[0]
        lat = y * scale[1] + translate[1]
        pts.append((lon, lat))
    return pts

def collect_geometry_points(geom, arcs, transform):
    """
    TopoJSON geometry types:
      Polygon: arcs: [ [arcIdx...], [holeArcIdx...] ... ]
      MultiPolygon: arcs: [ [ [arcIdx...] ], [ [arcIdx...] ] ... ]
    """
    points = []

    def add_arcidx(idx):
        # negative index means reverse direction
        if idx >= 0:
            pts = decode_arc(arcs[idx], transform)
        else:
            pts = list(reversed(decode_arc(arcs[~idx], transform)))
        points.extend(pts)

    gtype = geom.get("type")
    garcs = geom.get("arcs", [])

    if gtype == "Polygon":
        for ring in garcs:
            for a in ring:
                add_arcidx(a)
    elif gtype == "MultiPolygon":
        for poly in garcs:
            for ring in poly:
                for a in ring:
                    add_arcidx(a)

    return points

def rough_centroid(points):
    if not points:
        return None
    xs = sum(p[0] for p in points)
    ys = sum(p[1] for p in points)
    n = len(points)
    lon = xs / n
    lat = ys / n
    return (lat, lon)

def build_centroids(topo_path, out_path, level):
    topo = load_json(topo_path)
    arcs = topo["arcs"]
    transform = topo.get("transform")
    if not transform:
        raise RuntimeError("TopoJSON missing 'transform'. Export TopoJSON with quantization (default in mapshaper).")

    obj_name = list(topo["objects"].keys())[0]
    geoms = topo["objects"][obj_name]["geometries"]

    out = {}
    for g in geoms:
        props = g.get("properties", {}) or {}
        name = props.get("name") or props.get("NAME") or props.get("gen") or props.get("GEN") or None

        if level == "county":
            rid = props.get("ags") or props.get("AGS") or props.get("id") or props.get("ID") or g.get("id")
            rid = normalize_digits(rid, 5)
        else:
            rid = props.get("id") or props.get("ID") or props.get("ags") or props.get("AGS") or g.get("id")
            rid = normalize_digits(rid, 2)

        if not rid:
            continue

        pts = collect_geometry_points(g, arcs, transform)
        c = rough_centroid(pts)
        if not c:
            continue
        lat, lon = c
        out[rid] = {"lat": lat, "lon": lon, "name": name}

    save_json(out_path, out)
    print(f"Wrote {out_path} ({len(out)} regions)")

def main():
    build_centroids(COUNTY_TOPO, OUT_COUNTY, "county")
    build_centroids(STATE_TOPO, OUT_STATE, "state")

if __name__ == "__main__":
    main()