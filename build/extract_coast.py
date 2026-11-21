"""Extract coastline ways (whole Iceland) + municipality relations' member ways."""
import json, sys
import osmium

PBF, OUT = sys.argv[1], sys.argv[2]

class R(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rels = {}
    def relation(self, r):
        t = r.tags
        if t.get("boundary") == "administrative" and t.get("admin_level") == "6":
            self.rels[r.id] = {"name": t.get("name"), "ways": [(m.ref, m.role) for m in r.members if m.type == "w"]}

r = R(); r.apply_file(PBF)
need = {w for v in r.rels.values() for w, _ in v["ways"]}

class W(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.coast = []
        self.ways = {}
    def way(self, w):
        isc = w.tags.get("natural") == "coastline"
        if not isc and w.id not in need:
            return
        try:
            coords = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if isc:
            self.coast.append(coords)
        if w.id in need:
            self.ways[w.id] = coords

w = W(); w.apply_file(PBF, locations=True)
json.dump({"coast": w.coast, "rels": r.rels, "ways": {str(k): v for k, v in w.ways.items()}}, open(OUT, "w"))
print("coast ways", len(w.coast), "rels", len(r.rels), [v["name"] for v in r.rels.values()])
