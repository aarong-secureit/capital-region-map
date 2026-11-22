"""Extract the map area's features from the Iceland OSM extract (area: region.py)."""
import json, sys
import osmium
from region import W, S, E, N

PBF = sys.argv[1]
OUT = sys.argv[2]
def inb(lon, lat):
    return W <= lon <= E and S <= lat <= N

gj = osmium.geom.GeoJSONFactory()


def street_of(t):
    """addr:street, first spelling only where OSM lists two ("Elísabetarhagi;Elísarbetarhagi")"""
    st = t.get("addr:street")
    return st.split(";")[0].strip() if st else st

PLACES = {"suburb", "neighbourhood", "quarter", "locality", "village", "town", "city", "hamlet", "city_block", "borough"}

class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.post_pts = []
        self.place_nodes = []
        self.areas = []

    def node(self, n):
        if not n.location.valid():
            return
        lon, lat = n.location.lon, n.location.lat
        if not inb(lon, lat):
            return
        t = n.tags
        pc = t.get("addr:postcode")
        if pc:
            self.post_pts.append([round(lon, 6), round(lat, 6), pc, street_of(t), t.get("addr:city") or t.get("addr:place")])
        if t.get("place") in PLACES and t.get("name"):
            self.place_nodes.append({"name": t["name"], "place": t["place"], "lon": lon, "lat": lat,
                                     "tags": {k.k: k.v for k in t}})

    def area(self, a):
        t = a.tags
        pc = t.get("addr:postcode")
        keep = None
        if t.get("boundary") == "postal_code":
            keep = "postal"
        elif t.get("boundary") == "administrative" and t.get("admin_level") in ("5", "6", "7", "8", "9", "10"):
            keep = "admin"
        elif t.get("place") in PLACES and t.get("name"):
            keep = "place"
        elif t.get("landuse") == "residential" and t.get("name"):
            keep = "residential"
        if not keep and not pc:
            return
        try:
            g = json.loads(gj.create_multipolygon(a))
        except Exception:
            return
        # quick bbox check on first coordinate
        c = g["coordinates"][0][0][0]
        if not inb(c[0], c[1]) and keep != "admin":
            return
        if pc and not keep:
            # centroid-ish: mean of outer ring
            ring = g["coordinates"][0][0]
            lon = sum(p[0] for p in ring) / len(ring)
            lat = sum(p[1] for p in ring) / len(ring)
            if inb(lon, lat):
                self.post_pts.append([round(lon, 6), round(lat, 6), pc, street_of(t), t.get("addr:city") or t.get("addr:place")])
            return
        if keep == "admin":
            xs = [p[0] for p in g["coordinates"][0][0]]
            ys = [p[1] for p in g["coordinates"][0][0]]
            if max(xs) < W or min(xs) > E or max(ys) < S or min(ys) > N:
                return
        self.areas.append({"type": "Feature", "properties": {"kind": keep, **{k.k: k.v for k in t}},
                           "geometry": g})
        if pc:
            ring = g["coordinates"][0][0]
            self.post_pts.append([round(sum(p[0] for p in ring) / len(ring), 6),
                                  round(sum(p[1] for p in ring) / len(ring), 6), pc, street_of(t),
                                  t.get("addr:city") or t.get("addr:place")])

h = H()
h.apply_file(PBF, locations=True)
json.dump({"post_pts": h.post_pts, "place_nodes": h.place_nodes,
           "areas": {"type": "FeatureCollection", "features": h.areas}}, open(OUT, "w"), ensure_ascii=False)
print("post_pts", len(h.post_pts), "place_nodes", len(h.place_nodes), "areas", len(h.areas))
