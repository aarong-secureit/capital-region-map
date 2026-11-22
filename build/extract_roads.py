"""Street centre lines, for lining up the boundary layers with the streets on the background map.

Neighbourhood, district and postal borders in towns mostly run along streets, but each source draws them a
few metres off, so on the map they wander beside the road instead of on it. build_data.py moves a border
onto a street when it runs close to one (conform.py); this writes the streets it uses: every OSM road a
border could follow (not service roads, tracks or paths), as [[lon, lat], ...] lines rounded to ~0.1 m.

Usage: python extract_roads.py iceland-latest.osm.pbf OUT_JSON
"""
import json, sys
import osmium
from region import W, S, E, N

KINDS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "pedestrian", "road", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def way(self, w):
        if w.tags.get("highway") not in KINDS or w.tags.get("area") == "yes":
            return
        try:
            pts = [(round(n.lon, 6), round(n.lat, 6)) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) >= 2 and any(W <= x <= E and S <= y <= N for x, y in pts):
            self.lines.append(pts)


if __name__ == "__main__":
    pbf, out = sys.argv[1], sys.argv[2]
    h = H()
    h.apply_file(pbf, locations=True)
    json.dump(h.lines, open(out, "w"), separators=(",", ":"))
    print("roads", len(h.lines), "points", sum(len(l) for l in h.lines))
