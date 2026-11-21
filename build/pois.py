"""Shops, landmarks and bus hubs shown as icons on the map (and found by the search).

From the Iceland OSM extract:
  - every Bónus, Krónan and Nettó supermarket, and every Hagkaup (supermarket and department store)
  - shopping centres (Kringlan, Smáralind, Fjörður...), second-hand shops and Kolaportið flea market
  - big stores: Costco, IKEA, Elko, BYKO, Húsasmiðjan, Bauhaus, JYSK
  - Perlan
  - the public swimming pools (POOLS, by name: a heuristic would also catch pools inside pools, school pools,
    the seal pool at the zoo and a recording studio called Sundlaugin), Nauthólsvík beach and Sky Lagoon
  - parks, gardens and nature areas with a name (leisure=park/garden/common/nature_reserve; big named woods),
    shown as green labels: a label point inside the area, its size, and its bounding box for zooming to it
  - bus: Strætó's transfer hubs (straeto.is "Hubs": Fjörður, Ásgarður, Hamraborg, Mjódd, Ártún, Spöngin,
    Háholt), the city-centre hubs Hlemmur and Lækjartorg, the BSÍ terminal (airport and long-distance
    buses), and other big stops: any stop served by 4 or more Strætó lines (counted from OSM's bus route
    relations; lettered platforms like "Mjódd B" count as one stop) or with lettered platforms A and B.
    Every bus place lists its line numbers. Hlemmur is placed by hand: its
    stops are out of OSM while the square is rebuilt.
Only places inside the capital-region towns are kept (Akranes stores drop out).

Usage: python pois.py iceland-latest.osm.pbf MAPDATA_JSON OUT_JSON
"""
import json, math, re, sys
from collections import defaultdict
import osmium
from shapely.geometry import shape, Point, Polygon
from shapely.ops import unary_union

W, S, E, N = -22.15, 63.95, -21.30, 64.35
GROCERY = ("Bónus", "Krónan", "Nettó", "Hagkaup")
# big stores: brand -> OSM shop values it may carry
STORES = {"Costco": {"wholesale"}, "IKEA": {"furniture"}, "Elko": {"electronics"}, "BYKO": {"doityourself", "hardware"},
          "Húsasmiðjan": {"doityourself", "hardware"}, "Bauhaus": {"doityourself", "hardware"}, "JYSK": {"furniture"}}
STORE_SKIP = re.compile(r"Timbursala|Leigumarkað")          # BYKO's lumber yard and tool hire next to the shop
SIGHTS = {"Perlan": "attraction"}
# public pools: OSM name -> (name shown, kind, extra search words)
POOLS = {"Laugardalslaug": ("Laugardalslaug", "pool", []), "Vesturbæjarlaug": ("Vesturbæjarlaug", "pool", []),
         "Sundhöll Reykjavíkur": ("Sundhöll Reykjavíkur", "pool", ["sundhollin"]), "Árbæjarlaug": ("Árbæjarlaug", "pool", []),
         "Breiðholtslaug": ("Breiðholtslaug", "pool", []), "Grafarvogslaug": ("Grafarvogslaug", "pool", []),
         "Dalslaug": ("Dalslaug", "pool", []), "Klébergslaug": ("Klébergslaug", "pool", []),
         "Sundlaug Kópavogs": ("Sundlaug Kópavogs", "pool", ["kopavogslaug"]), "Salalaug": ("Salalaug", "pool", []),
         "Sundhöll Hafnarfjarðar": ("Sundhöll Hafnarfjarðar", "pool", []), "Suðurbæjarlaug": ("Suðurbæjarlaug", "pool", []),
         "Ásvallalaug": ("Ásvallalaug", "pool", []), "Ásgarðslaug": ("Ásgarðslaug", "pool", ["sundlaug gardabaejar"]),
         "Álftaneslaug": ("Álftaneslaug", "pool", []), "Urriðaholtslaug": ("Urriðaholtslaug", "pool", []),
         "Lágafellslaug": ("Lágafellslaug", "pool", []), "Varmárlaug": ("Varmárlaug", "pool", []),
         "Seltjarnarneslaug": ("Seltjarnarneslaug", "pool", []),
         "Ylströndin í Nauthólsvík": ("Nauthólsvík", "beach", ["ylstrondin", "beach"]),
         "Sky Lagoon": ("Sky Lagoon", "spa", ["lagoon", "spa"])}
# shopping centres OSM does not tag as malls: name -> (lat, lng, street)
MANUAL_MALLS = {"Spöngin": (64.15060, -21.78830, "Spöngin")}
HUBS = ["Fjörður", "Ásgarður", "Hamraborg", "Mjódd", "Ártún", "Spöngin", "Háholt"]   # Strætó's own list
CENTRE = ["Hlemmur", "Lækjartorg"]
TERMINAL = "BSÍ"
# stops OSM does not show right now: name -> (lat, lng)
MANUAL_STOPS = {"Hlemmur": (64.14318, -21.91470)}
# second-hand shops and the flea market: extra words people search with
SECOND_WORDS = {"Góði hirðirinn": ["good shepherd", "sorpa"], "Kolaportið": ["kolaport", "flea market"]}
STORE_WORDS = {"Elko": ["electronics"], "BYKO": ["hardware", "diy"], "Húsasmiðjan": ["hardware", "diy"],
               "Bauhaus": ["hardware", "diy"], "JYSK": ["furniture"], "IKEA": ["furniture"], "Costco": ["wholesale"]}


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(math.radians(64.1)), (a[1] - b[1]) * 110540)


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.shops, self.malls, self.second, self.sights = [], {}, [], []
        self.platforms = defaultdict(list)      # base name -> [(letter, lon, lat)]
        self.stations = {}
        self.stop_nodes = {}                    # node id -> (stop name without platform letter, lon, lat)
        self.routes = []                        # (line number, [member node ids]) for Strætó bus routes
        self.parks = {}                         # name -> (kind, km2, (lon, lat), bbox)
        self.pools = {}                         # OSM name -> (lon, lat, is_area)

    def take(self, kind, t, lon, lat):
        if not (W <= lon <= E and S <= lat <= N):
            return
        name, brand = t.get("name", ""), t.get("brand", "")
        shop, street, num = t.get("shop"), t.get("addr:street", ""), t.get("addr:housenumber", "")
        if shop == "supermarket":
            b = next((g for g in GROCERY if brand == g or name.startswith(g)), None)
            if b:
                self.shops.append(("grocery", b, lon, lat, street, num))
        elif shop:
            b = next((s for s, kinds in STORES.items() if shop in kinds and (brand.lower() == s.lower() or name.lower().startswith(s.lower()))), None)
            if b and not STORE_SKIP.search(name):
                self.shops.append(("store", b, lon, lat, street, num))
        if shop == "mall" and name and (name not in self.malls or kind == "a"):
            self.malls[name] = (lon, lat, street, num)
        if name and (shop in ("second_hand", "charity") or (t.get("amenity") == "marketplace" and name == "Kolaportið")):
            self.second.append((name, lon, lat, street, num, "flea" if t.get("amenity") == "marketplace" else "shop"))
        if name in SIGHTS and t.get("tourism") == SIGHTS[name]:
            self.sights.append((name, lon, lat))
        if name in POOLS and (name not in self.pools or (kind == "a" and not self.pools[name][2])):
            self.pools[name] = (lon, lat, kind == "a")      # prefer the building/area over entrance nodes
        if t.get("highway") == "bus_stop" or t.get("public_transport") == "platform":
            m = re.fullmatch(r"(.+?) ([A-Z])(?: \(.*\))?", name)
            base, letter = (m.group(1), m.group(2)) if m else (name, t.get("local_ref", ""))
            if base:
                self.platforms[base].append((letter if re.fullmatch(r"[A-Z]", letter or "") else "", lon, lat))
        if t.get("amenity") == "bus_station" and name:
            self.stations[name] = (lon, lat)

    def node(self, n):
        if n.tags:
            self.take("n", n.tags, n.location.lon, n.location.lat)
            t = n.tags
            if (t.get("highway") == "bus_stop" or t.get("public_transport") in ("platform", "stop_position")) and t.get("name"):
                lon, lat = n.location.lon, n.location.lat
                if W <= lon <= E and S <= lat <= N:
                    m = re.fullmatch(r"(.+?)(?: [A-Z])?(?: \(.*\))?", t["name"])
                    self.stop_nodes[n.id] = (m.group(1) if m else t["name"], lon, lat)

    def relation(self, r):
        t = r.tags
        if t.get("type") == "route" and t.get("route") == "bus" and t.get("ref") and \
                ("Strætó" in t.get("operator", "") or t.get("network", "").startswith("Strætó Höfuðborgarsvæðið")):
            self.routes.append((t["ref"], [m.ref for m in r.members if m.type == "n"]))

    def park(self, a):
        t, name = a.tags, a.tags.get("name")
        le = t.get("leisure")
        wood = t.get("natural") == "wood" or t.get("landuse") == "forest"
        if not name or not (le in ("park", "garden", "common", "nature_reserve") or wood):
            return
        try:                                    # every piece (Heiðmörk is mapped as 100 separate areas)
            g = unary_union([Polygon([(p.lon, p.lat) for p in r]).buffer(0) for r in a.outer_rings()])
        except Exception:
            return
        if g.is_empty:
            return
        x0, y0, x1, y1 = g.bounds
        if x1 < W or x0 > E or y1 < S or y0 > N:
            return
        km2 = g.area * 111.32 * 111.32 * math.cos(math.radians(64.1))
        if wood and km2 < 0.3:                  # only big named woods (Heiðmörk...)
            return
        kind = ("botanical" if t.get("garden:type") == "botanical" else "garden") if le == "garden" else \
               "reserve" if le == "nature_reserve" else "wood" if wood else "park"
        c = (max(g.geoms, key=lambda x: x.area) if g.geom_type == "MultiPolygon" else g).representative_point()
        if name not in self.parks or km2 > self.parks[name][1]:
            self.parks[name] = (kind, km2, (c.x, c.y), (x0, y0, x1, y1))

    def area(self, a):
        self.park(a)
        if not (a.tags.get("shop") or a.tags.get("tourism") or a.tags.get("amenity") or a.tags.get("name") in POOLS):
            return
        try:
            pts = [(p.lon, p.lat) for p in next(iter(a.outer_rings()))]
        except Exception:
            return
        self.take("a", a.tags, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def main(pbf, mapdata, out):
    d = json.load(open(mapdata, encoding="utf-8"))
    munis = [(f["properties"]["name"], shape(f["geometry"])) for f in d["munis"]["features"]]
    postal = [(f["properties"]["code"], f["properties"]["town"], shape(f["geometry"])) for f in d["postal"]["features"]]
    streets = d["streets"]                                  # [name, postcode, lng, lat, count]

    def muni_at(lon, lat):
        pt = Point(lon, lat)
        return next((n for n, g in munis if g.contains(pt)), None)

    def postal_at(lon, lat):
        pt = Point(lon, lat)
        return next(((c, t) for c, t, g in postal if g.contains(pt)), (None, None))

    def nearest_street(lon, lat):
        return min(streets, key=lambda s: metres((s[2], s[3]), (lon, lat)))[0]

    h = H()
    h.apply_file(pbf, locations=True)
    pois, skipped = [], []

    def add(rec, lon, lat):
        muni = muni_at(lon, lat)
        if not muni:
            skipped.append(rec["name"])
            return
        pc, town = postal_at(lon, lat)
        rec.update(ll=[round(lon, 6), round(lat, 6)], muni=muni, postal=[pc] if pc else [])
        if rec.get("g"):
            rec["g"] = rec["g"].replace("{PC}", f"{pc} {town}" if pc else muni)
        pois.append(rec)

    # supermarkets and big stores; one per brand within 300 m (OSM often has the shop as a node and a building)
    seen = []
    for cat, brand, lon, lat, street, num in sorted(h.shops, key=lambda s: (s[1], -len(s[4]), s[4])):
        if any(b == brand and metres(p, (lon, lat)) < 300 for b, p in seen):
            continue
        seen.append((brand, (lon, lat)))
        street = street or nearest_street(lon, lat)
        addr = f"{street} {num}".strip()
        many = cat == "grocery" or sum(1 for s in h.shops if s[1] == brand) > 1
        rec = {"name": f"{brand} {street}" if many else brand, "cat": cat, "brand": brand, "addr": addr,
               "g": f"{brand}, {addr}, {{PC}}", "words": STORE_WORDS.get(brand, [])}
        if brand == "Hagkaup":
            rec.update(kind="department", words=["department store"])
        add(rec, lon, lat)
    # make store names unique if a brand has two shops on one street
    for name in {p["name"] for p in pois if sum(q["name"] == p["name"] for q in pois) > 1}:
        for p in (q for q in pois if q["name"] == name):
            p["name"] = f"{p['brand']} {p['addr']}"
    for name, (lat, lon, street) in MANUAL_MALLS.items():
        h.malls.setdefault(name, (lon, lat, street, ""))
    for name, (lon, lat, street, num) in sorted(h.malls.items()):
        addr = f"{street} {num}".strip()
        add({"name": name, "cat": "mall", "addr": addr, "g": f"{name}, {{PC}}"}, lon, lat)
    done = set()
    for name, lon, lat, street, num, kind in sorted(h.second):
        key = (name, round(lon, 2), round(lat, 2))
        if key in done:
            continue
        done.add(key)
        addr = f"{street} {num}".strip()
        add({"name": name, "cat": "second", "kind": kind, "addr": addr,
             "g": f"{name}, {addr + ', ' if addr else ''}{{PC}}", "words": SECOND_WORDS.get(name, [])}, lon, lat)
    for name, (kind, km2, (lon, lat), bb) in sorted(h.parks.items()):
        add({"name": name, "cat": "park", "kind": kind, "km2": round(km2, 3), "bb": [round(v, 5) for v in bb],
             "g": f"{name}, {{PC}}"}, lon, lat)
    for osm_name, (lon, lat, _) in sorted(h.pools.items()):
        name, kind, words = POOLS[osm_name]
        add({"name": name, "cat": "pool", "kind": kind, "words": words, "g": f"{name}, {{PC}}"}, lon, lat)
    missing = sorted(set(POOLS) - set(h.pools))
    if missing:
        print("  pools not found in OSM:", ", ".join(missing))
    for name, lon, lat in h.sights[:1]:
        add({"name": name, "cat": "sight", "g": name + ", Reykjavík"}, lon, lat)

    # bus: platforms inside the region only (a same-named stop in Akranes must not pull the middle away)
    def stop_group(name):
        pts = [(l, x, y) for l, x, y in h.platforms.get(name, []) if muni_at(x, y)]
        return pts

    # lines per stop: group same-named stop nodes within 400 m, then collect the routes that call at them
    clusters = defaultdict(list)                 # name -> [{"pts": [...], "nodes": set(), "lines": set()}]
    for nid, (base, lon, lat) in h.stop_nodes.items():
        for c in clusters[base]:
            if metres(c["pts"][0], (lon, lat)) < 400:
                c["pts"].append((lon, lat)); c["nodes"].add(nid); break
        else:
            clusters[base].append({"pts": [(lon, lat)], "nodes": {nid}, "lines": set()})
    node_cluster = {nid: c for cs in clusters.values() for c in cs for nid in c["nodes"]}
    for ref, members in h.routes:
        for m in members:
            if m in node_cluster:
                node_cluster[m]["lines"].add(ref)
    line_key = lambda x: (int(re.match(r"\d*", x).group() or 999), x)

    def lines_at(name, lon, lat):
        near = [c for c in clusters.get(name, []) if metres(c["pts"][0], (lon, lat)) < 600]
        return sorted(set().union(*(c["lines"] for c in near)) if near else set(), key=line_key)

    used = set()
    for name, kind in [(n, "hub") for n in HUBS] + [(n, "centre") for n in CENTRE] + [(TERMINAL, "terminal")]:
        pts = stop_group(name) + (stop_group(name + " Bus Terminal") if name == TERMINAL else [])
        if name in h.stations and muni_at(*h.stations[name]):
            lon, lat = h.stations[name]
        elif pts:
            lon, lat = sum(p[1] for p in pts) / len(pts), sum(p[2] for p in pts) / len(pts)
        elif name in MANUAL_STOPS:
            lat, lon = MANUAL_STOPS[name]
        else:
            print("  no stops found for", name); continue
        letters = "".join(sorted({p[0] for p in pts if p[0]}))
        add({"name": name, "cat": "bus", "kind": kind, "stops": letters, "lines": lines_at(name, lon, lat)}, lon, lat)
        used.add(name)
    for base, pts in sorted(h.platforms.items()):
        letters = {p[0] for p in pts if p[0]}
        if base in used or not {"A", "B"} <= letters:
            continue
        pts = [p for p in pts if p[0]]
        lon, lat = sum(p[1] for p in pts) / len(pts), sum(p[2] for p in pts) / len(pts)
        add({"name": base, "cat": "bus", "kind": "stop", "stops": "".join(sorted(letters)), "lines": lines_at(base, lon, lat)}, lon, lat)
        used.add(base)
    # any other stop served by 4 or more lines (busiest first, so a same-named smaller stop is skipped)
    taken = {(p["name"], p["muni"]) for p in pois if p["cat"] == "bus"}
    for base, c in sorted(((b, c) for b, cs in clusters.items() for c in cs if len(c["lines"]) >= 4),
                          key=lambda bc: -len(bc[1]["lines"])):
        if base in used:
            continue
        lon = sum(x for x, _ in c["pts"]) / len(c["pts"]); lat = sum(y for _, y in c["pts"]) / len(c["pts"])
        muni = muni_at(lon, lat)
        if not muni or (base, muni) in taken:
            continue
        taken.add((base, muni))
        add({"name": base, "cat": "bus", "kind": "stop", "stops": "", "lines": sorted(c["lines"], key=line_key)}, lon, lat)

    count = defaultdict(int)
    for p in pois:
        count[(p["name"], p["muni"], p["cat"])] += 1
    dup = [k for k, v in count.items() if v > 1]
    assert not dup, f"duplicate names: {dup}"
    json.dump(pois, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tally = defaultdict(int)
    for p in pois:
        tally[p.get("brand") or p["cat"]] += 1
    print(f"{len(pois)} places:", dict(tally))
    for cat in ("pool", "park"):
        print(f"  {cat}:", ", ".join(p["name"] + (f" ({p['kind']}{' ' + p['stops'] if p.get('stops') else ''})" if cat == "bus" else "")
                                    for p in pois if p["cat"] == cat))
    if skipped:
        print("outside the capital region, skipped:", ", ".join(skipped))


if __name__ == "__main__":
    main(*sys.argv[1:4])
