"""Assign postal colours (greedy graph colouring) and inline data (and optional audio) into the HTML template.

Usage: python inject.py MAPDATA_JSON TEMPLATE_HTML OUT_HTML [AUDIO_INDEX_JSON] [LANDMARKS_JSON] [POIS_JSON] [ALIASES_JSON] [ROADS_JSON]
AUDIO_INDEX_JSON comes from make_audio.py (no listen buttons without it);
LANDMARKS_JSON from landmarks.py (shares fall back to area middles without it);
POIS_JSON from pois.py (shops, Perlan, bus hubs; none shown without it);
ALIASES_JSON = aliases.json (other names people use, e.g. Holtin, Grandi);
ROADS_JSON from streets_geo.py (big roads, found by the search).
"""
import json, sys
from shapely.geometry import shape

data_fn, tpl_fn, out_fn = sys.argv[1:4]
audio_fn = sys.argv[4] if len(sys.argv) > 4 else None
landmarks_fn = sys.argv[5] if len(sys.argv) > 5 else None
pois_fn = sys.argv[6] if len(sys.argv) > 6 else None
aliases_fn = sys.argv[7] if len(sys.argv) > 7 else None
roads_fn = sys.argv[8] if len(sys.argv) > 8 else None
d = json.load(open(data_fn))
if landmarks_fn:
    d["landmarks"] = json.load(open(landmarks_fn, encoding="utf-8"))
    print("landmarks", len(d["landmarks"]))
d["pois"] = json.load(open(pois_fn, encoding="utf-8")) if pois_fn else []
print("pois", len(d["pois"]))
d["aliases"] = json.load(open(aliases_fn, encoding="utf-8")) if aliases_fn else {}
print("aliases", len(d["aliases"]))
d["roads"] = json.load(open(roads_fn, encoding="utf-8")) if roads_fn else []
print("roads", len(d["roads"]))
fs = d["postal"]["features"]
geoms = [shape(f["geometry"]).buffer(0.0008) for f in fs]
adj = {i: {j for j in range(len(fs)) if j != i and geoms[i].intersects(geoms[j])} for i in range(len(fs))}
# colour biggest-degree first
from collections import Counter
NCOL = 8
tally = Counter()
for i in sorted(adj, key=lambda i: -len(adj[i])):
    used = {fs[j]["properties"].get("ci") for j in adj[i]}
    free = [c for c in range(NCOL) if c not in used] or [c for c in range(20) if c not in used]
    c = min(free, key=lambda c: (tally[c], c))
    fs[i]["properties"]["ci"] = c
    tally[c] += 1
print("colours used", max(f["properties"]["ci"] for f in fs) + 1)
s = json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = open(tpl_fn).read().replace("/*__DATA__*/null", s).replace("__BUILT__", d["built"])
if audio_fn:
    a = open(audio_fn, encoding="utf-8").read()
    # escape "</" like the map data: a place name containing "</script>" must not end the script block
    html = html.replace("/*__AUDIO__*/null", a.replace("</", "<\\/"))
    print("audio clips", len(json.loads(a).get("clips", {})))
open(out_fn, "w").write(html)
print("wrote", out_fn, len(html) // 1024, "KB")
