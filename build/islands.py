"""Named islands for the map: labels, search, "What's here", and land for the "Ocean" check.

Islands come from OSM (place=island, islet or archipelago, with a name). Which ones are kept, for a learning
map rather than a chart:
  - the capital region and Vestmannaeyjar: every named island (Viðey, Engey, Akurey, Heimaey, Surtsey,
    Elliðaey, the Þrídrangar skerries...), down to about 0.001 km²
  - elsewhere: islands and island groups of 0.1 km² or more (Brokey, Flatey, Vigur, Drangey, Hrísey,
    Grímsey, Papey, Árnes in Þjórsá, Sandey in Þingvallavatn...); Breiðafjörður alone has hundreds of named
    skerries.
An island belongs to the municipality whose boundary contains it, or failing that the nearest one within
10 km (municipality boundaries hug the coast in some places). The Flatey group (Vestureyjar) belonged to
Flateyjarhreppur, now part of Reykhólahreppur, though Barðaströnd is closer.

Usage: python islands.py osm/iceland-latest.osm.pbf data/coast.json data/mapdata.json
Adds "islands" to the map data and adds the islands to its "land" outline. Run after build_data.py.
"""
import json, sys
import osmium
import shapely
from shapely.geometry import LineString, MultiPolygon, Polygon, mapping, shape
from shapely.ops import linemerge, polygonize, polylabel, unary_union
import region as R

M = 1 / 111200                                  # one metre in degrees of latitude
scale, unscale, km2 = R.scale, R.unscale, R.km2  # near-metric plane, right at every latitude
MIN_KM2 = 0.1                                   # outside the capital region and Vestmannaeyjar
MIN_KM2_ALL = 0.001                             # inside them
ALL_NAMED = R.CAP_MUNIS | {"Vestmannaeyjar"}


def scan(pbf):
    gj = osmium.geom.GeoJSONFactory()
    out = []

    class H(osmium.SimpleHandler):
        def area(self, a):
            t = a.tags
            if t.get("place") not in ("island", "islet", "archipelago") or not t.get("name"):
                return
            try:
                g = shape(json.loads(gj.create_multipolygon(a)))
            except Exception:
                return
            if not g.is_valid:
                g = g.buffer(0)
            c = g.representative_point()
            if R.inb(c.x, c.y):
                out.append({"name": t["name"], "place": t["place"], "g": g})
    H().apply_file(pbf, locations=True)
    return out


def municipalities(coast):
    rels = []
    for r in coast["rels"].values():
        outer = [LineString(coast["ways"][str(w)]) for w, role in r["ways"] if str(w) in coast["ways"] and role != "inner"]
        g = unary_union(list(polygonize(linemerge(outer))))
        if not g.is_empty:
            rels.append((r["name"], g))
    return rels


# Vestureyjar of Breiðafjörður (Flatey, Hergilsey, Svefneyjar, Hvallátur, Bjarneyjar...)
FLATEY_GROUP = Polygon([(-23.10, 65.24), (-22.74, 65.24), (-22.74, 65.47), (-23.10, 65.47)])


def muni_of(pt, rels):
    d, name = min((g.distance(pt), n) for n, g in rels)
    km = d * R.KM * R.kx(pt.y)
    if km > 0.05 and FLATEY_GROUP.contains(pt):
        return "Reykhólahreppur"
    short = R.MUNI_SHORT.get(name)
    if not short or km > 10:
        return None
    return short


def label_pt(g):
    big = max(g.geoms, key=lambda p: p.area) if isinstance(g, MultiPolygon) else g
    try:
        p = unscale(polylabel(scale(big), tolerance=0.00003))
    except Exception:
        p = big.representative_point()
    return [round(p.x, 5), round(p.y, 5)]


def outline(g, place, a):
    """A light outline for tapping: a little wider than the island, simplified to 12-30 m. An island group
    grows 150 m, so the narrow sounds between its islands count as part of it."""
    grow, tol = (150, 40) if place == "archipelago" else (25, 12 if a < 0.5 else 20 if a < 5 else 30)
    s = scale(g).buffer(grow * M, quad_segs=3).simplify(tol * M, preserve_topology=True)
    return shapely.set_precision(unscale(s), 0.00005)


def build(pbf, coast, d):
    raw = scan(pbf)
    rels = municipalities(coast)
    keep = []
    for o in raw:
        pt = o["g"].representative_point()
        mu = muni_of(pt, rels)
        if not mu:
            continue
        a = km2(o["g"])
        if a < (MIN_KM2_ALL if mu in ALL_NAMED else MIN_KM2) or a > 5000:
            continue                            # > 5000 km²: Iceland itself (place=island, name Ísland)
        if o["place"] == "archipelago" and (o["name"] == mu or o["name"] in R.MUNI_SHORT.values()):
            continue                            # Vestmannaeyjar: the municipality already has the name
        keep.append({**o, "muni": mu, "km2": a})
    groups = [o for o in keep if o["place"] == "archipelago"]
    isles = []
    for o in keep:
        if o["place"] == "archipelago":
            continue
        pt = o["g"].representative_point()
        grp = next((gr for gr in groups if gr["muni"] == o["muni"] and gr["g"].buffer(0.0005).contains(pt)), None)
        if grp and grp["name"] == o["name"]:
            continue                            # an islet named like its group: the group stands for it
        o["group"] = grp["name"] if grp else None
        isles.append(o)
    for gr in groups:
        gr["isles"] = sorted({o["name"] for o in isles if o.get("group") == gr["name"]})
    feats = []
    for o in sorted(isles + groups, key=lambda o: -o["km2"]):
        props = {"name": o["name"], "place": o["place"], "muni": o["muni"], "zone": R.ZONE_OF[o["muni"]],
                 "km2": round(o["km2"], 3), "label": label_pt(o["g"])}
        if o.get("group"):
            props["group"] = o["group"]
        if o.get("isles"):
            props["isles"] = o["isles"]
        feats.append({"type": "Feature", "properties": props, "geometry": mapping(outline(o["g"], o["place"], o["km2"]))})
    extra =unary_union([unscale(scale(o["g"]).buffer(60 * M, quad_segs=2)) for o in isles + groups])
    land = shapely.set_precision(unary_union([shape(d["land"]), extra.simplify(0.0003, preserve_topology=True)]), 0.0001)
    return feats, land


if __name__ == "__main__":
    pbf, coast_fn, data_fn = sys.argv[1:4]
    coast = json.load(open(coast_fn))
    d = json.load(open(data_fn, encoding="utf-8"))
    feats, land = build(pbf, coast, d)
    d["islands"] = {"type": "FeatureCollection", "features": feats}
    d["land"] = mapping(land)
    json.dump(d, open(data_fn, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    from collections import Counter
    print("islands", len(feats), Counter(f["properties"]["place"] for f in feats),
          Counter(f["properties"]["muni"] for f in feats).most_common(8))
    print("islands KB", len(json.dumps(d["islands"], ensure_ascii=False, separators=(",", ":"))) // 1024,
          "land KB", len(json.dumps(d["land"], separators=(",", ":"))) // 1024)
