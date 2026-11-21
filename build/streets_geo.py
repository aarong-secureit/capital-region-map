"""Road lines of every named street, so "Nearest street" measures to the road itself.

Before this, the page only knew one middle point per street, so on a long street (Brautarholt) a short
cross street's middle point (Ásholt, Mjölnisholt) could be nearer to where you clicked than the street
you clicked on.

Reads named OSM highways in the capital region, simplifies each line to about 2 m, and writes
_assets/streets.js, which the page loads in the background:
  window.STREET_LINES = {"Brautarholt": "lat,lng;dlat,dlng;...|lat,lng;...", ...}
coordinates in 1e-5 degrees, each line's first point absolute, the rest as differences; "|" between lines.

Usage: python streets_geo.py iceland-latest.osm.pbf MAPDATA_JSON OUT_JS
"""
import json, sys
from collections import defaultdict
import osmium
from shapely.geometry import shape, LineString
from shapely.ops import unary_union
from shapely.prepared import prep

W, S, E, N = -22.15, 63.95, -21.30, 64.35
KINDS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "pedestrian", "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "road"}


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.lines = defaultdict(list)

    def way(self, w):
        name, hw = w.tags.get("name"), w.tags.get("highway")
        if not name or hw not in KINDS:
            return
        try:
            pts = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 2 or not any(W <= x <= E and S <= y <= N for x, y in pts):
            return
        self.lines[name].append(pts)


def main(pbf, mapdata, out):
    d = json.load(open(mapdata, encoding="utf-8"))
    region = prep(unary_union([shape(f["geometry"]) for f in d["munis"]["features"]]).buffer(0.002))
    h = H()
    h.apply_file(pbf, locations=True)
    outd, n_lines, n_pts = {}, 0, 0
    for name, lines in sorted(h.lines.items()):
        parts = []
        for pts in lines:
            ls = LineString(pts)
            if not region.intersects(ls):
                continue
            ls = ls.simplify(0.00002, preserve_topology=False)          # ~2 m
            coords = [(round(y * 1e5), round(x * 1e5)) for x, y in ls.coords]
            enc, prev = [], None
            for la, lo in coords:
                enc.append(f"{la},{lo}" if prev is None else f"{la - prev[0]},{lo - prev[1]}")
                prev = (la, lo)
            parts.append(";".join(enc)); n_lines += 1; n_pts += len(coords)
        if parts:
            outd[name] = "|".join(parts)
    js = "window.STREET_LINES=" + json.dumps(outd, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ";\n"
    open(out, "w", encoding="utf-8").write(js)
    print(f"{len(outd)} streets, {n_lines} lines, {n_pts} points, {len(js.encode()) / 1024:.0f} KB")


if __name__ == "__main__":
    main(*sys.argv[1:4])
