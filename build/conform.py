"""Make the boundary layers agree with each other and with the streets.

Each layer comes from a different source (OSM municipalities, Reykjavík's own districts and neighbourhoods,
postal areas grown from address points), and each used to be simplified on its own. A border shared by three
layers was drawn as three lines a few metres apart that crossed back and forth when zoomed in, and borders
that follow a street ran beside it instead of on it. All of this works in region.scale's near-metric plane
(M is one metre there):

- fit(): moves a lower layer's border onto a street when it runs within a few metres of one, then onto the
  border of a layer above it (municipality, district, sub-district, neighbourhood) when it runs close to that.
- tidy(): for a layer that splits up its parent (Reykjavík's districts, postal areas...): clips each area to
  the parent, gives thin leftover slivers to the neighbour they border most, and cleans the set into a GEOS
  coverage (no overlaps, narrow gaps closed, shared edges identical).
- simplify_together(): cuts every border of every layer into pieces where borders meet, simplifies each piece
  once, and rebuilds every area from the simplified pieces, so a border shared by several areas or layers is
  exactly the same line in all of them.
"""
from collections import defaultdict
import numpy as np
import shapely
from shapely import STRtree
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
from shapely.ops import unary_union

M = 1 / 111200          # one metre in the scaled plane (a degree of latitude is 111.2 km)
GRID = 0.2 * M          # borders closer than this are one line


def polys(g):
    """The polygonal part of g, made valid."""
    if g is None or g.is_empty:
        return Polygon()
    g = shapely.make_valid(g)
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    parts = [p for p in getattr(g, "geoms", []) if isinstance(p, (Polygon, MultiPolygon))]
    return unary_union(parts) if parts else Polygon()


def parts(g):
    return list(g.geoms) if isinstance(g, MultiPolygon) else ([g] if isinstance(g, Polygon) and not g.is_empty else [])


def rings(g):
    return [LineString(r.coords) for p in parts(g) for r in [p.exterior, *p.interiors]]


class Lines:
    """Reference lines (streets, or the borders of the layers above) for fit(): split into 2-point segments,
    each remembering which line it comes from and where in it."""

    def __init__(self, lines):
        self.coords, segs, line, pos = [], [], [], []
        for l in lines:
            c = shapely.get_coordinates(l)
            if len(c) < 2:
                continue
            self.coords.append(c)
            segs.append(np.stack([c[:-1], c[1:]], axis=1))
            line.append(np.full(len(c) - 1, len(self.coords) - 1))
            pos.append(np.arange(len(c) - 1))
        self.segs = shapely.linestrings(np.concatenate(segs)) if segs else np.array([], dtype=object)
        self.line = np.concatenate(line) if line else np.array([], dtype=int)
        self.pos = np.concatenate(pos) if pos else np.array([], dtype=int)
        self.tree = STRtree(self.segs)


def project_ring(xy, ref, tol, far=0, run_m=50):
    """A ring's vertices, those within tol of a reference line moved onto it; also each stretch of ring (at
    least run_m long) that stays within far of the reference lines and runs along them, not across: the same
    border drawn by another source along the other side or the middle of a wide road, or zigzagging beside it.
    Where two neighbouring vertices landed on different segments of the same line, the line's own vertices
    between them are put in too, so the ring follows the line exactly, corners included."""
    pts = shapely.points(xy)
    pi, si = ref.tree.query_nearest(pts, max_distance=max(tol, far), all_matches=False)
    if not len(pi):
        return xy
    near = shapely.get_coordinates(shapely.shortest_line(pts[pi], ref.segs[si]))[1::2]
    ok = shapely.distance(pts[pi], ref.segs[si]) <= tol
    if far > tol:
        hit = np.zeros(len(xy), bool)
        hit[pi] = True
        at = np.full(len(xy), -1)
        at[pi] = np.arange(len(pi))
        k, n = 0, len(xy)
        while k < n:                                     # each run of consecutive vertices within far
            if not hit[k]:
                k += 1
                continue
            e = k
            while e + 1 < n and hit[e + 1]:
                e += 1
            run = np.arange(k, e + 1)
            seg_len = np.hypot(*np.diff(xy[run], axis=0).T).sum() if len(run) > 1 else 0
            if seg_len >= run_m * M:
                chord = xy[e] - xy[k]
                pch = near[at[e]] - near[at[k]]
                lc, lp = np.hypot(*chord), np.hypot(*pch)
                if lp >= 0.8 * lc and (chord @ pch) / max(lc * lp, 1e-15) > 0.95:    # along the line, not across
                    ok[at[run]] = True
            k = e + 1
    pi, si, near = pi[ok], si[ok], near[ok]
    if not len(pi):
        return xy
    xy = xy.copy()
    xy[pi] = near
    seg = np.full(len(xy), -1)
    seg[pi] = si
    out = [xy[0]]
    for k in range(1, len(xy)):
        a, b = seg[k - 1], seg[k]
        if a >= 0 and b >= 0 and a != b and ref.line[a] == ref.line[b]:
            pa, pb, c = ref.pos[a], ref.pos[b], ref.coords[ref.line[a]]
            n = len(c) - 1                                    # segments in the line
            ring = (c[0] == c[-1]).all()                      # a closed line: go round the short way
            fwd = (pb - pa) % n if ring else pb - pa
            back = (pa - pb) % n if ring else pa - pb
            if 0 < fwd <= 40 and (back <= 0 or fwd <= back):
                out.extend(c[[(pa + i) % n for i in range(1, fwd + 1)]])        # vertices pa+1 .. pb
            elif 0 < back <= 40:
                out.extend(c[[(pa - i) % n for i in range(back)]])               # vertices pa .. pb+1
        out.append(xy[k])
    return np.array(out)


def project(g, ref, tol, far=0):
    """g with every border vertex within tol of a reference line (or within far of one it runs parallel to)
    moved onto that line (see project_ring)."""
    if ref is None or not len(ref.segs) or g.is_empty:
        return g
    out = []
    for p in parts(g):
        ext = project_ring(np.asarray(p.exterior.coords)[:, :2], ref, tol, far)
        holes = [project_ring(np.asarray(r.coords)[:, :2], ref, tol, far) for r in p.interiors]
        if len(ext) >= 4:
            out.append(polys(Polygon(ext, [h for h in holes if len(h) >= 4])))
    return polys(unary_union(out)) if out else Polygon()


def fit(g, roads=None, road_m=0, edges=None, edge_m=0, parallel_m=0, step_m=2):
    """g with its border on the streets it runs along (within road_m) and then on the borders of the layers
    above it (within edge_m, or parallel_m where it runs alongside one), which win where both are close. The
    border first gets a vertex every step_m, so it can follow a street's curves."""
    if g.is_empty:
        return g
    g = shapely.segmentize(g, step_m * M)
    if roads is not None and road_m:
        g = project(g, roads, road_m * M)
    if edges is not None and edge_m:
        width = 2 * g.area / max(g.length, 1e-15) / M            # about how wide the area is, in metres
        g = project(g, edges, edge_m * M, min(parallel_m, width / 4) * M)     # a narrow area keeps its shape
    return polys(g.simplify(0.05 * M))          # drop the extra points again where the border is straight


def tidy(geoms, parent, gap_m=60):
    """Areas that split up `parent`, clipped to it, its thin leftover slivers (narrower than gap_m) given to
    the neighbour they border most, then cleaned into a coverage: no overlaps, narrow gaps closed, shared
    edges identical. Returns a list in the same order (an area may come back empty)."""
    out = [polys(g.intersection(parent)) for g in geoms]
    left = polys(parent.difference(unary_union([g for g in out if not g.is_empty])))
    for lp in parts(left):
        if 2 * lp.area / max(lp.length, 1e-12) > gap_m * M:      # about its width: a real gap, not a sliver
            continue
        edge = lp.boundary.buffer(GRID)
        best = max(range(len(out)), key=lambda i: out[i].boundary.intersection(edge).length if not out[i].is_empty else -1,
                   default=None)
        if best is not None and not out[best].is_empty and out[best].boundary.intersection(edge).length > 0:
            out[best] = polys(unary_union([out[best], lp]))
    keep = [i for i, g in enumerate(out) if not g.is_empty]
    if len(keep) > 1:
        clean = shapely.coverage_clean(np.array([out[i] for i in keep]), gap_width=gap_m * M, snapping_distance=0.5 * M)
        for i, g in zip(keep, clean):
            out[i] = polys(polys(g).intersection(parent)) if g is not None else Polygon()
    return out


def simplify_together(geoms, detail, land, own_lines=None, detail_m=5, detail_coast_m=12, rural_m=80, rural_coast_m=150):
    """Every border of every area in `geoms` (any number of layers, overlapping freely) cut into pieces where
    borders meet; each piece simplified once and every area rebuilt from the simplified pieces it is made of.
    Pieces are simplified to detail_m within (300 m of) `detail` and rural_m elsewhere; coastline pieces (with
    sea on one side: outside `land`) more, since the background map draws the coast anyway. own_lines[i] False:
    area i's borders are all borders of other areas (a region is its municipalities), so it adds no lines of
    its own. Returns the areas in the same order."""
    geoms = [shapely.set_precision(polys(g.simplify(0.05 * M)), GRID) for g in geoms]
    own = own_lines if own_lines is not None else [True] * len(geoms)
    net = shapely.unary_union([r for g, o in zip(geoms, own) if o for r in rings(g)], grid_size=GRID)
    arcs = shapely.line_merge(net)
    arcs = list(arcs.geoms) if hasattr(arcs, "geoms") else [arcs]
    near = detail.buffer(300 * M)
    shapely.prepare(near)
    shapely.prepare(land)
    pieces = []                        # (line, in detail?)
    for a in arcs:
        if near.contains(a):
            pieces.append((a, True))
        elif not near.intersects(a):
            pieces.append((a, False))
        else:
            pieces += [(a.intersection(near), True), (a.difference(near), False)]
    # coast or not: is there sea a metre to one side of the piece's middle?
    mids = []
    for line, _ in pieces:
        c = shapely.get_coordinates(line)
        k = max(1, len(c) // 2)
        p, q = (c[k - 1], c[k]) if len(c) >= 2 else (c[0], c[0] + [1e-9, 0])
        d = q - p
        n = np.array([-d[1], d[0]]) / max(np.hypot(*d), 1e-15) * M
        mids.append(((p + q) / 2 + n, (p + q) / 2 - n))
    if mids:
        a1 = np.array([m[0] for m in mids]); a2 = np.array([m[1] for m in mids])
        coast = ~(shapely.contains_xy(land, a1[:, 0], a1[:, 1]) & shapely.contains_xy(land, a2[:, 0], a2[:, 1]))
    simple = []
    for (line, det), sea in zip(pieces, coast if mids else []):
        if line.is_empty:
            continue
        tol = (detail_coast_m if sea else detail_m) if det else (rural_coast_m if sea else rural_m)
        s = line.simplify(tol * M, preserve_topology=True)
        simple.append(line if (getattr(line, "is_ring", False) and shapely.get_num_coordinates(s) < 4) else s)
    faces = list(shapely.polygonize(list(shapely.unary_union(simple, grid_size=GRID).geoms)).geoms)
    if not faces:
        return geoms
    inside = shapely.point_on_surface(np.array(faces, dtype=object))
    owners = defaultdict(list)
    fi, gi = STRtree(geoms).query(inside, predicate="within")
    for f, g in zip(fi, gi):
        owners[g].append(faces[f])
    out = []
    for i, g in enumerate(geoms):
        fs = owners.get(i)
        if not fs:                      # too small to keep a face of its own: simplified alone
            out.append(polys(g.simplify(detail_m * M, preserve_topology=True)))
            continue
        try:
            u = shapely.coverage_union_all(fs)
        except shapely.errors.GEOSException:
            u = unary_union(fs)
        out.append(polys(u))
    return out


def _tick(what, t0=None):
    import time
    t = time.time()
    if t0 is not None:
        print(f"  borders: {what} in {t - t0:.0f} s", flush=True)
    return t


def make_borders(muni_land, zones, districts, hverfi, nbh, small, postal, roads, detail,
                 road_m=10, edge_m=15, parallel_m=40, postal_road_m=20, postal_edge_m=25, postal_parallel_m=55):
    """The finished borders of every layer, in lon/lat. Inputs in lon/lat:
    muni_land {name: area}, zones {name: [munis]}, districts/nbh/small [{"name", "muni", "g"}],
    hverfi [g] (Reykjavík), postal {code: area}, roads [[lon, lat], ...],
    detail: the municipalities shown in full (capital region, Akureyri), where borders are fitted to the streets
    and each other. Returns {"munis": {..}, "zones": {..}, "districts": [..], "hverfi": [..], "nbh": [..],
    "small": [..], "postal": {..}}, areas in the order given."""
    import region as R
    S = R.scale
    ml = {k: polys(S(g)) for k, g in muni_land.items()}
    det = polys(unary_union([ml[m] for m in detail]))
    road_lines = [LineString(r) for r in roads if len(r) >= 2]
    road_lines = [S(l) for l in road_lines]
    near = STRtree(road_lines).query(det.buffer(200 * M), predicate="intersects")
    road_ref = Lines([road_lines[i] for i in near])
    edges = [r for m in detail for r in rings(ml[m])]

    def layer(items, edge_lines, partition):
        ref = Lines(edge_lines)
        out = [fit(polys(S(it["g"])).intersection(ml[it["muni"]]), road_ref, road_m, ref, edge_m, parallel_m) for it in items]
        out = [polys(g.intersection(ml[it["muni"]])) for g, it in zip(out, items)]
        if partition:
            for m in {it["muni"] for it in items}:
                idx = [i for i, it in enumerate(items) if it["muni"] == m]
                for i, g in zip(idx, tidy([out[i] for i in idx], ml[m])):
                    out[i] = g
        return out

    t = _tick("start")
    d_out = layer(districts, edges, True)
    t = _tick("districts", t)
    edges += [r for g in d_out for r in rings(g)]
    h_out = layer([{"g": g, "muni": "Reykjavík"} for g in hverfi], edges, True)
    edges += [r for g in h_out for r in rings(g)]
    n_out = layer(nbh, edges, True)
    edges += [r for g in n_out for r in rings(g)]
    s_out = layer(small, edges, False)
    t = _tick("hverfi, neighbourhoods, small areas", t)
    # postal areas in the detailed municipalities: fitted, then tidied within the area they covered together
    # (so their outer edge still meets the neighbouring postal areas exactly)
    p_in = {c: polys(S(g)) for c, g in postal.items()}
    group = [c for c, g in p_in.items() if g.intersects(det)]
    ref = Lines([r for g in d_out + h_out + n_out for r in rings(g)] + [r for m in detail for r in rings(ml[m])])
    fitted = [fit(p_in[c], road_ref, postal_road_m, ref, postal_edge_m, postal_parallel_m) for c in group]
    p_out = dict(p_in)
    for c, g in zip(group, tidy(fitted, polys(unary_union([p_in[c] for c in group])))):
        p_out[c] = g
    # one set of lines for everything
    zl = {z: polys(unary_union([ml[m] for m in ms])) for z, ms in zones.items()}
    keys = ([("munis", k) for k in ml] + [("zones", z) for z in zl] + [("districts", i) for i in range(len(d_out))] +
            [("hverfi", i) for i in range(len(h_out))] + [("nbh", i) for i in range(len(n_out))] +
            [("small", i) for i in range(len(s_out))] + [("postal", c) for c in p_out])
    src = {"munis": ml, "zones": zl, "districts": d_out, "hverfi": h_out, "nbh": n_out, "small": s_out, "postal": p_out}
    t = _tick("postal areas", t)
    done = simplify_together([src[k][i] for k, i in keys], det, polys(unary_union(list(ml.values()))),
                             own_lines=[k != "zones" for k, _ in keys])
    _tick("simplified", t)
    res = {"munis": {}, "zones": {}, "districts": [None] * len(d_out), "hverfi": [None] * len(h_out),
           "nbh": [None] * len(n_out), "small": [None] * len(s_out), "postal": {}}
    # coordinates to 5 decimals (~1 m) in the detailed municipalities, 4 (~5-10 m) elsewhere, where borders are
    # simplified to 80 m anyway; by each point's own position, so a shared point is rounded the same everywhere
    near = R.unscale(det.buffer(300 * M))
    shapely.prepare(near)

    def rounded(xy):
        fine = shapely.contains_xy(near, xy[:, 0], xy[:, 1])
        return np.where(fine[:, None], np.round(xy, 5), np.round(xy, 4))
    for (k, i), g in zip(keys, done):
        res[k][i] = polys(shapely.transform(R.unscale(g), rounded))
    return res
