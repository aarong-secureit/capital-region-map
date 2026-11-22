"""Every street address (street + house number) on the map, for the Home / Work settings: the whole capital
region, and the towns elsewhere (region.py).

Reads OSM nodes and buildings tagged addr:street + addr:housenumber, keeps those in the capital region and
in towns elsewhere, takes the postcode from the map's postal areas, and writes a small JavaScript file the page loads
only when someone uses Home / Work. The lookup happens in the browser, so typed addresses never leave
the device.

Output (_assets/addresses.js):  window.ADDRESSES = {"Laugavegur|101": "<number>,<dlat>,<dlng>;...", ...}
  numbers sorted; coordinates in 1e-5 degrees, the first relative to the street's first point (stored as
  "base" before it), the rest as differences from the previous one, which keeps the file small.

Usage: python addresses.py iceland-latest.osm.pbf MAPDATA_JSON OUT_JS
"""
import json, re, sys
from collections import defaultdict
import osmium
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

from region import W, S, E, N, town_filter


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rows = []

    def take(self, t, lon, lat):
        st, num = t.get("addr:street"), t.get("addr:housenumber")
        st = st.split(";")[0].strip() if st else st          # first spelling where OSM lists two
        if st and num and W <= lon <= E and S <= lat <= N:
            self.rows.append((st.strip(), num.strip(), lon, lat))

    def node(self, n):
        if n.tags and "addr:housenumber" in n.tags:
            self.take(n.tags, n.location.lon, n.location.lat)

    def area(self, a):
        if "addr:housenumber" not in a.tags:
            return
        try:
            pts = [(p.lon, p.lat) for p in next(iter(a.outer_rings()))]
        except Exception:
            return
        self.take(a.tags, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def num_key(n):
    m = re.match(r"(\d+)(.*)", n)
    return (int(m.group(1)), m.group(2)) if m else (10**6, n)


def main(pbf, mapdata, out):
    d = json.load(open(mapdata, encoding="utf-8"))
    postal = [(f["properties"]["code"], shape(f["geometry"])) for f in d["postal"]["features"]]
    tree = STRtree([g for _, g in postal])
    in_town = town_filter(d)
    h = H()
    h.apply_file(pbf, locations=True)
    h.rows = [r for r in h.rows if in_town(r[2], r[3])]
    by = defaultdict(dict)                     # (street, postcode) -> {number: (lat, lon)}
    for st, num, lon, lat in h.rows:
        pt = Point(lon, lat)
        pc = next((postal[i][0] for i in tree.query(pt) if postal[i][1].contains(pt)), None)
        if not pc:
            continue                           # outside the map's postal areas
        num = re.sub(r"\s+", "", num).lower()  # "11 A" -> "11a"
        by[(st, pc)].setdefault(num, (lat, lon))
    outd, total = {}, 0
    for (st, pc), nums in sorted(by.items()):
        parts, plat, plon = [], None, None
        for num in sorted(nums, key=num_key):
            lat, lon = (round(v * 1e5) for v in nums[num])
            if plat is None:
                parts.append(f"{lat},{lon}")   # base
                dl, dn = 0, 0
            else:
                dl, dn = lat - plat, lon - plon
            parts.append(f"{num},{dl},{dn}")
            plat, plon = lat, lon
        outd[f"{st}|{pc}"] = ";".join(parts)
        total += len(nums)
    js = "window.ADDRESSES=" + json.dumps(outd, ensure_ascii=False, separators=(",", ":")) + ";\n"
    open(out, "w", encoding="utf-8").write(js)
    print(f"{total} addresses on {len(outd)} streets, {len(js.encode()) / 1024:.0f} KB")


if __name__ == "__main__":
    main(*sys.argv[1:4])
