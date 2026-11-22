"""A rough outline of the land, so the page can say "Ocean" when someone taps the open sea.

Built from the OSM coastline (data/coast.json from extract_coast.py), grown by about 200 m so a tap right
at the shore still counts as land, then simplified to ~200 m. Islets under 0.3 km² are left out.

Usage: python land.py data/coast.json data/mapdata.json     (adds "land" to the map data)
build_data.py calls land_mask() itself, so this is only needed to update an existing mapdata.json.
"""
import json, sys
import shapely
from shapely.geometry import LineString, MultiPolygon, mapping
from shapely.ops import linemerge, polygonize, unary_union
import region as R



def land_mask(coast, margin_km=0.2):
    lines = [LineString(c) for c in coast["coast"] if len(c) >= 2]
    faces = [p for p in polygonize(linemerge(lines)) if p.intersects(R.BOX)]
    land = unary_union(faces).intersection(R.BOX.buffer(0.05))
    g = R.scale(land)                                                       # metres-ish: same scale both ways
    d = margin_km / 111.2
    g = g.buffer(d, quad_segs=2).simplify(d, preserve_topology=True)
    parts = list(g.geoms) if isinstance(g, MultiPolygon) else [g]
    g = unary_union([p for p in parts if p.area * 111.2 ** 2 >= 0.3])
    g = R.unscale(g)
    return shapely.set_precision(g, 0.0001)


if __name__ == "__main__":
    coast = json.load(open(sys.argv[1]))
    g = land_mask(coast)
    d = json.load(open(sys.argv[2], encoding="utf-8"))
    d["land"] = mapping(g)
    json.dump(d, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    n = sum(len(r.coords) for poly in (g.geoms if isinstance(g, MultiPolygon) else [g]) for r in [poly.exterior, *poly.interiors])
    print(f"land outline: {len(getattr(g, 'geoms', [g]))} pieces, {n} points, "
          f"{len(json.dumps(mapping(g), separators=(',', ':'))) / 1024:.0f} KB")
