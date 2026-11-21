"""List candidate landmarks in the capital region from the Iceland OSM extract.

Usage: python find_landmarks.py iceland-latest.osm.pbf
Prints every town hall, plus features whose name matches the WANTED list, with coordinates,
so landmarks.json can be filled in from real data.
"""
import sys
import osmium

from region import W, S, E, N
WANTED = ["Ráðhús", "Hallgrímskirkja", "Kringlan", "Laugardalslaug", "Laugardalshöll", "Kjarvalsstaðir", "Árbæjarsafn",
          "Spöngin", "Mjódd", "Vesturbæjarlaug", "Guðríðarkirkja", "Klébergsskóli", "Bessastaðir", "Smáralind",
          "Bæjarskrifstofur", "Hamraborg", "Garðatorg", "Grótta", "Harpa", "Perlan", "Háskóli Íslands", "Fífan",
          "Kópavogskirkja", "Hafnarfjarðarkirkja", "Ásgarður", "Egilshöll", "Breiðholtslaug", "Árbæjarlaug",
          "Grafarvogslaug", "Kórinn", "Salalaug", "Hvalfjarðargöng", "Elliðaárdalur", "Lágafellslaug", "Varmárlaug"]


def wanted(name):
    return any(name.startswith(w) or name == w for w in WANTED)


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rows = []

    def add(self, kind, t, lon, lat):
        if not (W <= lon <= E and S <= lat <= N):
            return
        name = t.get("name", "")
        if t.get("amenity") == "townhall" or (name and wanted(name)):
            tags = ",".join(f"{k}={t.get(k)}" for k in ("amenity", "tourism", "leisure", "shop", "building", "historic", "place")
                            if t.get(k))
            self.rows.append((name, round(lat, 5), round(lon, 5), kind, tags))

    def node(self, n):
        if n.location.valid() and (n.tags.get("name") or n.tags.get("amenity")):
            self.add("node", n.tags, n.location.lon, n.location.lat)

    def area(self, a):
        if not (a.tags.get("name") or a.tags.get("amenity")):
            return
        try:
            outer = next(iter(a.outer_rings()))
            pts = [(p.lon, p.lat) for p in outer]
        except Exception:
            return
        self.add("area", a.tags, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


h = H()
h.apply_file(sys.argv[1], locations=True)
for r in sorted(set(h.rows)):
    print(" | ".join(map(str, r)))
