"""Build the map data: regions, municipalities, towns, and (capital region) districts, hverfi,
neighbourhoods; postal areas and streets everywhere (outside the capital region only in towns). Area: region.py."""
import datetime, json, os, re, sys, unicodedata
from collections import Counter, defaultdict
import numpy as np
import shapely
from shapely.geometry import shape, mapping, LineString, MultiPoint, Point, Polygon, MultiPolygon
from shapely.ops import linemerge, polygonize, unary_union, polylabel
from scipy.spatial import cKDTree
import region as R
from land import land_mask

D = sys.argv[1]
OUT = sys.argv[2]
BBOX = R.BOX
LAT0 = 64.12
KX = np.cos(np.radians(LAT0))
KM = 111.2  # km per scaled degree

def scale(g):
    return shapely.transform(g, lambda c: c * np.array([KX, 1.0]))

def unscale(g):
    return shapely.transform(g, lambda c: c / np.array([KX, 1.0]))

def km2(g):
    return scale(g).area * KM * KM

def norm(s):
    s = s.lower().replace("þ", "th").replace("ð", "d").replace("æ", "ae")
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

def polys_only(g):
    if g.is_empty:
        return g
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    parts = [p for p in getattr(g, "geoms", []) if isinstance(p, (Polygon, MultiPolygon))]
    return unary_union(parts) if parts else Polygon()

def clean(g, tol=0.00012):
    g = polys_only(shapely.make_valid(g))
    g = g.simplify(tol, preserve_topology=True)
    g = polys_only(shapely.make_valid(g))
    return shapely.set_precision(g, 0.0001 if tol >= 0.0004 else 0.00001)   # rural areas: ~10 m is plenty

def label_pt(g):
    big = max(g.geoms, key=lambda p: p.area) if isinstance(g, MultiPolygon) else g
    try:
        p = unscale(polylabel(scale(big), tolerance=0.00005))
    except Exception:
        p = big.representative_point()
    return [round(p.x, 5), round(p.y, 5)]

def feat(g, tol=0.00012, min_km2=0, **props):
    g = clean(g, tol)
    if min_km2 and isinstance(g, MultiPolygon):           # drop skerries and islets on the big rural areas
        big = [p for p in g.geoms if km2(p) >= min_km2]
        g = unary_union(big) if big else max(g.geoms, key=lambda p: p.area)
    if g.is_empty:
        return None
    props["label"] = label_pt(g)
    props["km2"] = round(km2(g), 2)
    return {"type": "Feature", "properties": props, "geometry": mapping(g)}

# ---------------- land ----------------
coast = json.load(open(f"{D}/coast.json"))
lines = [LineString(c) for c in coast["coast"] if len(c) >= 2]
merged = linemerge(lines)
faces = [p for p in polygonize(merged) if p.intersects(BBOX)]
land = unary_union(faces).intersection(BBOX)
print("land km2", round(km2(land)), "faces", len(faces))

# ---------------- municipalities ----------------
CAP = R.MUNI_SHORT
munis = {}
for rid, r in coast["rels"].items():
    if r["name"] not in CAP:
        continue
    outer = [LineString(coast["ways"][str(w)]) for w, role in r["ways"] if str(w) in coast["ways"] and role != "inner"]
    inner = [LineString(coast["ways"][str(w)]) for w, role in r["ways"] if str(w) in coast["ways"] and role == "inner"]
    og = unary_union(list(polygonize(linemerge(outer))))
    if inner:
        og = og.difference(unary_union(list(polygonize(linemerge(inner)))))
    if CAP[r["name"]] not in R.CAP_MUNIS:
        og = og.intersection(R.LOWLAND)
    munis[CAP[r["name"]]] = og
missing = set(CAP.values()) - set(munis)
assert not missing, missing
for k, g in munis.items():
    print("muni", k, round(km2(g)), "land", round(km2(g.intersection(land))))
region = unary_union(list(munis.values()))
region_land = region.intersection(land)
muni_land = {k: g.intersection(land) for k, g in munis.items()}

def muni_of(pt):
    for k, g in munis.items():
        if g.contains(pt):
            return k
    return None

# ---------------- Reykjavík official layers ----------------
def load(fn):
    return json.load(open(f"{D}/{fn}"))["features"]

borgarhlutar = []
for f in load("rvk_Stjornsysluskipting.geojson"):
    nm = f["properties"]["HVERFI"]
    num, name = nm.split(". ", 1)
    name = {"Grafarholt-Úlfarsárd.": "Grafarholt og Úlfarsárdalur", "Háaleiti-Bústaðir": "Háaleiti og Bústaðir"}.get(name, name)
    borgarhlutar.append((int(num), name, shapely.make_valid(shape(f["geometry"]))))

def borgarhluti_of(pt):
    for num, name, g in borgarhlutar:
        if g.contains(pt):
            return name
    return None

# Planning hverfi (mid tier) dissolved by HVERFI code
hv = defaultdict(list); hv_name = defaultdict(Counter)
for f in load("rvk_Ibudahverfi_hverfaskipulags.geojson"):
    p = f["properties"]
    code = p.get("HVERFI")
    if not code:
        continue
    hv[code].append(shapely.make_valid(shape(f["geometry"])))
    if p.get("HVERFAHEITI"):
        hv_name[code][p["HVERFAHEITI"].strip()] += 1
HV_FIX = {"Háteigsvherfi": "Háteigshverfi", "Háaleiti- Múlar": "Háaleiti - Múlar", "Efra breiðholt": "Efra Breiðholt",
          "Leiti & Gerði": "Kringlan - Leiti - Gerði"}
HV_MISSING = {"3.1": "Háteigshverfi", "8.1": "Bryggjuhverfi - Höfðar - Ártúnshöfði"}

# ---------------- address points / postal areas ----------------
ex = json.load(open(f"{D}/osm_extract.json"))
pts = np.array([[p[0], p[1]] for p in ex["post_pts"]])
codes = np.array([p[2].strip()[:3] for p in ex["post_pts"]])
streets = [p[3] for p in ex["post_pts"]]
inside = shapely.contains_xy(region_land, pts[:, 0], pts[:, 1])
pts, codes = pts[inside], codes[inside]
streets = [s for s, ok in zip(streets, inside) if ok]
cnt = Counter(codes)
valid = {c for c, n in cnt.items() if n >= 5 and re.fullmatch(r"\d\d\d", c)}
print("codes", sorted(cnt.items()))
m = np.array([c in valid for c in codes])
pts, codes = pts[m], codes[m]
streets = [s for s, ok in zip(streets, m) if ok]

# majority-vote outlier removal
sp = pts * np.array([KX, 1.0])
tree = cKDTree(sp)
_, idx = tree.query(sp, k=11)
keep = np.ones(len(pts), bool)
for i in range(len(pts)):
    nb = codes[idx[i, 1:]]
    same = (nb == codes[i]).sum()
    if same <= 1 and Counter(nb).most_common(1)[0][1] >= 7:
        keep[i] = False
print("outliers dropped", (~keep).sum())
vp, vc = sp[keep], codes[keep]
# dedupe coordinates
uniq = {}
for (x, y), c in zip(np.round(vp, 6), vc):
    uniq.setdefault((x, y), Counter())[c] += 1
up = np.array(list(uniq.keys()))
uc = np.array([v.most_common(1)[0][0] for v in uniq.values()])
env = scale(region_land).envelope.buffer(0.05)
cells = shapely.voronoi_polygons(MultiPoint(up), extend_to=env, ordered=True)
cells = list(cells.geoms)
print("voronoi cells", len(cells), "points", len(up))
by = defaultdict(list)
for c, cell in zip(uc, cells):
    by[c].append(cell)
# which municipalities each code's addresses fall in (codes outside the capital region)
pt_muni = np.array([None] * len(pts), dtype=object)
for k, g in munis.items():
    hit = shapely.contains_xy(g, pts[:, 0], pts[:, 1])
    pt_muni[hit] = k
GEN = {}
for c in set(codes):
    mc = Counter(pt_muni[codes == c])
    tot = sum(mc.values())
    GEN[c] = [k for k, n in mc.items() if k and n >= max(3, 0.03 * tot)]
CAP_CODE = lambda c: c[0] == "1" and c != "190" or c[:2] in ("20", "21", "22", "27")
def code_munis(c):
    if not CAP_CODE(c): return GEN.get(c) or list(muni_land)
    if c == "170": return ["Seltjarnarnes"]
    if c[0] == "1": return ["Reykjavík"]
    if c.startswith("20"): return ["Kópavogur"]
    if c in ("210", "212", "225"): return ["Garðabær"]
    if c.startswith("22"): return ["Hafnarfjörður"]
    if c == "276": return ["Mosfellsbær", "Kjósarhreppur"]
    if c.startswith("27"): return ["Mosfellsbær"]
    return list(muni_land)
postal = {}
for c, cs in by.items():
    allowed = unary_union([muni_land[m] for m in code_munis(c)])
    g = shapely.union_all(cs).intersection(scale(allowed))
    postal[c] = unscale(polys_only(g))
# drop tiny fragments then reassign leftovers to neighbour with longest shared edge
for c, g in list(postal.items()):
    parts = list(g.geoms) if isinstance(g, MultiPolygon) else [g]
    mainA = max(p.area for p in parts)
    kept = [p for p in parts if km2(p) >= 0.03 or p.area >= 0.5 * mainA]
    postal[c] = unary_union(kept)
left = polys_only(region_land.difference(unary_union(list(postal.values()))))
lparts = list(left.geoms) if isinstance(left, MultiPolygon) else ([left] if not left.is_empty else [])
for lp in lparts:
    best, bl = None, -1
    lm = muni_of(lp.representative_point())
    for c, g in postal.items():
        if lm and lm not in code_munis(c):
            continue
        l = lp.boundary.intersection(g.buffer(1e-7)).length
        if l > bl:
            best, bl = c, l
    if best and bl > 0:
        postal[best] = unary_union([postal[best], lp.buffer(1e-7)])
TOWN = lambda c: (R.POSTAL_TOWN.get(c, "") if not CAP_CODE(c) else "Seltjarnarnes" if c == "170" else "Reykjavík" if c[0] == "1" else
                  "Kópavogur" if c.startswith("20") else "Hafnarfjörður" if c.startswith("22") and c != "225" else
                  "Garðabær" if c in ("210", "212", "225") else "Mosfellsbær" if c.startswith("27") else "")

# ---------------- neighbourhoods ----------------
nbh = []     # main tier
small = []   # sub-areas
NAME_FIX = {"Kjalarn.-dreifb.": "Kjalarnes (dreifbýli)"}
rvk_names = set()
for f in load("rvk_Hverfaheiti.geojson"):
    nm = NAME_FIX.get(f["properties"]["HEITI"], f["properties"]["HEITI"])
    g = shapely.make_valid(shape(f["geometry"]))
    gl = g.intersection(land.buffer(0.002))
    if km2(gl) > 0.6 * km2(g):
        g = gl
    rp = g.representative_point()
    nbh.append({"name": nm, "muni": "Reykjavík", "district": borgarhluti_of(rp), "g": g, "src": "Reykjavíkurborg"})
    rvk_names.add(norm(nm))

areas = ex["areas"]["features"]
districts = []
for num, name, g in borgarhlutar:
    districts.append({"name": name, "muni": "Reykjavík", "g": g, "num": num})
for f in areas:
    p = f["properties"]
    g = shapely.make_valid(shape(f["geometry"]))
    rp = g.representative_point()
    mu = muni_of(rp)
    if not mu or not p.get("name") or mu not in R.CAP_MUNIS:
        continue
    if p["kind"] == "admin" and p.get("admin_level") in ("8", "9") and mu != "Reykjavík":
        districts.append({"name": p["name"], "muni": mu, "g": g.intersection(land.buffer(0.002))})
    elif p["kind"] == "admin" and p.get("admin_level") == "10" and mu != "Reykjavík":
        nbh.append({"name": p["name"], "muni": mu, "district": None, "g": g.intersection(land.buffer(0.002)),
                    "src": "OpenStreetMap"})
# district for non-RVK neighbourhoods
for n in nbh:
    if n["district"] is None:
        rp = n["g"].representative_point()
        for d in districts:
            if d["muni"] == n["muni"] and d["g"].contains(rp):
                n["district"] = d["name"]
SKIP = re.compile(r"(garðar|garður|Hrafnista|Völundarlóð)$")
have = {(norm(n["name"]), n["muni"]) for n in nbh}
for f in areas:
    p = f["properties"]
    if p["kind"] not in ("place", "residential") or not p.get("name") or SKIP.search(p["name"]):
        continue
    g = shapely.make_valid(shape(f["geometry"]))
    rp = g.representative_point()
    mu = muni_of(rp)
    if not mu or mu not in R.CAP_MUNIS or (norm(p["name"]), mu) in have:
        continue
    have.add((norm(p["name"]), mu))
    parent = next((n["name"] for n in nbh if n["muni"] == mu and n["g"].contains(rp)), None)
    small.append({"name": p["name"], "muni": mu, "parent": parent, "g": g, "src": "OpenStreetMap",
                  "kind": p.get("place") or "residential area"})

# place nodes not covered by a same-named polygon
allpolys = [(norm(x["name"]), x["g"]) for x in nbh + small + districts]
points = []
for n in ex["place_nodes"]:
    pt = Point(n["lon"], n["lat"])
    if not region.contains(pt) or n["place"] in ("town", "city") or muni_of(pt) not in R.CAP_MUNIS:
        continue
    nn = norm(n["name"])
    if any(nm == nn and g.distance(pt) < 0.012 for nm, g in allpolys):
        continue
    mu = muni_of(pt)
    points.append({"name": n["name"], "place": n["place"], "muni": mu,
                   "ll": [round(n["lon"], 5), round(n["lat"], 5)]})

# ---------------- towns (outside the capital region) ----------------
TOWN_CLASS = {"town": "town", "village": "village", "hamlet": "hamlet", "suburb": "hamlet"}
towns = []
seen_t = set()
for n in ex["place_nodes"]:
    cls = TOWN_CLASS.get(n["place"])
    pt = Point(n["lon"], n["lat"])
    mu = muni_of(pt) if cls else None
    if not mu or mu in R.CAP_MUNIS or n["name"] in R.TOWN_DROP:
        continue
    name = R.TOWN_RENAME.get(n["name"], n["name"])
    if (name, mu) in seen_t:
        continue
    seen_t.add((name, mu))
    towns.append({"name": name, "place": cls, "muni": mu, "zone": R.ZONE_OF[mu],
                  "ll": [round(n["lon"], 5), round(n["lat"], 5)]})
towns.sort(key=lambda t: ({"town": 0, "village": 1, "hamlet": 2}[t["place"]], norm(t["name"])))
print("towns", len(towns), Counter(t["place"] for t in towns))
RAD = {"town": R.TOWN_RADIUS_KM["town"], "village": R.TOWN_RADIUS_KM["village"], "hamlet": 0.6}
town_xy = np.array([[t["ll"][0] * KX, t["ll"][1]] for t in towns]) if towns else np.zeros((0, 2))
town_r = np.array([RAD[t["place"]] / KM for t in towns])
cap_union = shapely.prepared.prep(unary_union([munis[m] for m in R.CAP_MUNIS]))
def in_town(x, y):
    """inside the capital region, or within a town's radius elsewhere"""
    if cap_union.contains(Point(x, y)):
        return True
    if not len(town_xy):
        return False
    d = np.hypot(town_xy[:, 0] - x * KX, town_xy[:, 1] - y)
    return bool((d <= town_r).any())

# ---------------- streets ----------------
sacc = defaultdict(list)
for (x, y), c, s in zip(pts, codes, streets):
    if s and in_town(x, y):
        sacc[(s, c)].append((x, y))
street_list = []
for (s, c), ps in sacc.items():
    a = np.array(ps)
    med = np.median(a, axis=0)
    # pick actual address point closest to median (so it lies on the street)
    j = np.argmin(((a - med) ** 2).sum(1))
    street_list.append([s, c, round(a[j, 0], 5), round(a[j, 1], 5), len(ps)])
street_list.sort(key=lambda r: (norm(r[0]), r[1]))
print("streets", len(street_list))

# ---------------- postal descriptions ----------------
postal_feats = []
for c in sorted(postal):
    g = postal[c]
    inside_n = []
    for n in nbh:
        ov = n["g"].intersection(g)
        if not ov.is_empty and km2(ov) > 0.5 * km2(n["g"]):
            inside_n.append(n["name"])
    in_towns = [t["name"] for t in towns if g.contains(Point(*t["ll"]))]
    outer = not CAP_CODE(c)
    f = feat(g, tol=0.0008 if outer else 0.00012, min_km2=0.1 if outer else 0, code=c, town=TOWN(c),
             contains=sorted(set(inside_n), key=norm), towns=in_towns, addresses=int(cnt[c]))
    if f:
        postal_feats.append(f)

# postal code(s) for each neighbourhood / small area
def postals_for(g):
    out = []
    for c, pg in postal.items():
        ov = pg.intersection(g)
        if not ov.is_empty:
            share = km2(ov) / max(km2(g), 1e-9)
            if share > 0.08:
                out.append((c, share))
    return [c for c, _ in sorted(out, key=lambda t: -t[1])]

hv_union = {code: shapely.make_valid(unary_union(gs)) for code, gs in hv.items()}
hv_feats = []
for code, g in sorted(hv_union.items(), key=lambda t: [float(x) for x in t[0].split(".")]):
    name = hv_name[code].most_common(1)[0][0] if hv_name[code] else HV_MISSING.get(code, code)
    name = HV_FIX.get(name, name)
    if code == "0.0":
        name = "Elliðaárdalur"
    gl = g.intersection(land.buffer(0.002))
    f = feat(gl, name=name, muni="Reykjavík", district=borgarhluti_of(g.representative_point()),
             postal=postals_for(gl))
    if f:
        hv_feats.append(f)

def hv_name_of(g):
    rp = g.representative_point()
    for f in hv_feats:
        if shape(f["geometry"]).buffer(0.0003).contains(rp):
            return f["properties"]["name"]
    return None

nbh_feats = [feat(n["g"], name=n["name"], muni=n["muni"], district=n["district"],
                  hverfi=hv_name_of(n["g"]) if n["muni"] == "Reykjavík" else None,
                  postal=postals_for(n["g"]), src=n["src"]) for n in nbh]
small_feats = [feat(s["g"], name=s["name"], muni=s["muni"], parent=s["parent"],
                    postal=postals_for(s["g"]), src=s["src"]) for s in small]
dist_feats = [feat(d["g"], name=d["name"], muni=d["muni"], postal=postals_for(d["g"])) for d in districts]
muni_feats = []
for k, g in muni_land.items():
    outer = k not in R.CAP_MUNIS
    muni_feats.append(feat(g, tol=0.001 if outer else 0.00012, min_km2=0.2 if outer else 0, name=k,
                           zone=R.ZONE_OF[k], towns=[t["name"] for t in towns if t["muni"] == k and t["place"] != "hamlet"]))
zone_feats = []
for z, ms in R.ZONES.items():
    zg = unary_union([muni_land[m] for m in ms])
    zone_feats.append(feat(zg, tol=0.002, min_km2=1.0, name=z, en=R.ZONE_EN[z], munis=ms,
                           towns=[t["name"] for t in towns if t["zone"] == z and t["place"] == "town"]))
for t in towns:
    pt = Point(*t["ll"])
    t["postal"] = [c for c, g in postal.items() if g.contains(pt)][:1]
for p in points:
    pt = Point(*p["ll"])
    p["postal"] = [c for c, g in postal.items() if g.contains(pt)][:1]

fc = lambda fs: {"type": "FeatureCollection", "features": [f for f in fs if f]}
for t in towns:
    t.pop("zone")                                  # used above for the regions' town lists; the page reads munis
built = datetime.date.fromtimestamp(os.path.getmtime(os.path.join(D, "osm_extract.json"))).isoformat()
data = {"zones": fc(zone_feats), "towns": towns, "munis": fc(muni_feats), "districts": fc(dist_feats), "hverfi": fc(hv_feats), "nbh": fc(nbh_feats),
        "small": fc(small_feats), "postal": fc(postal_feats), "points": points, "streets": street_list,
        "land": mapping(land_mask(coast)), "built": built}
s = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
open(OUT, "w").write(s)
print("sizes KB", {k: len(json.dumps(v, ensure_ascii=False, separators=(",", ":"))) // 1024 for k, v in data.items()})
print("nbh", len(nbh_feats), "small", len(small_feats), "districts", len(dist_feats), "hverfi", len(hv_feats),
      "postal", len(postal_feats), "points", len(points))
for f in postal_feats:
    p = f["properties"]
    print(p["code"], p["town"], p["km2"], ", ".join(p["contains"]))
