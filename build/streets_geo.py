"""Road lines of every named street, so "Nearest street" measures to the road itself.

Before this, the page only knew one middle point per street, so on a long street (Brautarholt) a short
cross street's middle point (Ásholt, Mjölnisholt) could be nearer to where you clicked than the street
you clicked on.

Reads named OSM highways on the map (region.py): every street in the capital region; elsewhere the streets in
towns and the big roads (numbered roads without a name are called "Route 35"). Simplifies each line to about
2 m and writes _assets/streets.js, which the page loads in the background:
  window.STREET_LINES = {"Brautarholt": "lat,lng;dlat,dlng;...|lat,lng;...", ...}
coordinates in 1e-5 degrees, each line's first point absolute, the rest as differences; "|" between lines.

Also writes ROADS_JSON (optional): the big roads, for the search: [{"name", "refs", "ll", "bb"}].

Usage: python streets_geo.py iceland-latest.osm.pbf MAPDATA_JSON OUT_JS [ROADS_JSON]
"""
import json, sys
from collections import defaultdict
import osmium
from shapely.geometry import shape, LineString
from shapely.ops import unary_union
from shapely.prepared import prep

from region import W, S, E, N, BIG_ROADS, town_filter
KINDS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "pedestrian", "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "road"}


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.lines = defaultdict(list)

    def way(self, w):
        name, hw, ref = w.tags.get("name"), w.tags.get("highway"), w.tags.get("ref")
        if name and not any(c.isalpha() for c in name):
            name = None                                             # roads named just "4" (OSM slips)
        if hw not in KINDS or not (name or (hw in BIG_ROADS and ref)):
            return
        try:
            pts = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 2 or not any(W <= x <= E and S <= y <= N for x, y in pts):
            return
        self.lines[name or f"Route {ref.split(';')[0]}"].append((pts, hw in BIG_ROADS, ref))


def main(pbf, mapdata, out, roads_out=None):
    d = json.load(open(mapdata, encoding="utf-8"))
    region = prep(unary_union([shape(f["geometry"]) for f in d["munis"]["features"]]).buffer(0.002))
    in_town = town_filter(d)
    h = H()
    h.apply_file(pbf, locations=True)
    outd, n_lines, n_pts, roads = {}, 0, 0, {}
    for name, lines in sorted(h.lines.items()):
        parts = []
        for pts, big, ref in lines:
            ls = LineString(pts)
            if not region.intersects(ls):
                continue
            if not big and not any(in_town(x, y) for x, y in pts[::max(1, len(pts) // 8)] + [pts[-1]]):
                continue                                            # rural farm tracks and side roads
            if big:
                r = roads.setdefault(name, {"refs": set(), "lines": []})
                if ref:
                    r["refs"].update(x.strip() for x in ref.split(";"))
                r["lines"].append(ls)
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
    if roads_out:
        out_r = []
        for name, r in sorted(roads.items()):
            u = unary_union(r["lines"])
            if u.length * 111.2 * 0.45 < 1.5:                     # under ~1.5 km: a slip road, not a road people name
                continue
            longest = max(getattr(u, "geoms", [u]), key=lambda g: g.length)
            mid = longest.interpolate(0.5, normalized=True)
            out_r.append({"name": name, "refs": sorted(r["refs"], key=lambda x: (len(x), x)),
                          "ll": [round(mid.x, 5), round(mid.y, 5)], "bb": [round(v, 5) for v in u.bounds]})
        json.dump(out_r, open(roads_out, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"{len(out_r)} big roads for the search")


if __name__ == "__main__":
    main(*sys.argv[1:5])
