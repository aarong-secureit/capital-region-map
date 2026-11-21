"""Landmarks used when sharing a place to Google Maps.

Big areas (towns, districts, postal codes) share a well-known spot inside them, e.g. the town hall;
everything else shares the middle of the area. Coordinates come from OpenStreetMap (find_landmarks.py).
Each landmark is checked to lie inside the area it represents before it is written out.
Outside the capital region, municipalities and postal codes without a landmark below share their biggest town.

Usage: python landmarks.py MAPDATA_JSON OUT_JSON
"""
import json, sys
from shapely.geometry import shape, Point

# (kind, area name, town or None, landmark name, lat, lng)
LANDMARKS = [
    # forecast zones: the main town
    ("zones", "Höfuðborgarsvæðið", None, "Hallgrímskirkja (Reykjavík)", 64.14177, -21.92667),
    ("zones", "Faxaflói", None, "Akranes", 64.32179, -22.07490),
    ("zones", "Breiðafjörður", None, "Stykkishólmur", 65.07507, -22.72981),
    ("zones", "Suðurland", None, "Selfoss", 63.93311, -20.99707),
    # towns: town hall, or the best-known spot
    ("munis", "Reykjavík", None, "Ráðhús Reykjavíkur (City Hall)", 64.14613, -21.94238),
    ("munis", "Kópavogur", None, "Ráðhús Kópavogs (town hall)", 64.11125, -21.90805),
    ("munis", "Hafnarfjörður", None, "Ráðhús Hafnarfjarðar (town hall)", 64.06960, -21.95767),
    ("munis", "Garðabær", None, "Ráðhús Garðabæjar (town hall)", 64.08805, -21.91945),
    ("munis", "Mosfellsbær", None, "Bæjarskrifstofur Mosfellsbæjar (town hall)", 64.16729, -21.69706),
    ("munis", "Seltjarnarnes", None, "Grótta lighthouse", 64.16458, -22.02119),
    ("munis", "Kjósarhreppur", None, "Ásgarður (municipal office)", 64.34172, -21.59338),
    # Reykjavík districts
    ("districts", "Miðborg", "Reykjavík", "Hallgrímskirkja", 64.14177, -21.92667),
    ("districts", "Vesturbær", "Reykjavík", "Vesturbæjarlaug (swimming pool)", 64.14446, -21.96310),
    ("districts", "Hlíðar", "Reykjavík", "Kjarvalsstaðir (Klambratún)", 64.13787, -21.91395),
    ("districts", "Laugardalur", "Reykjavík", "Laugardalslaug (swimming pool)", 64.14616, -21.87968),
    ("districts", "Háaleiti og Bústaðir", "Reykjavík", "Kringlan (shopping centre)", 64.13023, -21.89483),
    ("districts", "Breiðholt", "Reykjavík", "Mjódd", 64.10970, -21.84152),
    ("districts", "Árbær", "Reykjavík", "Árbæjarsafn (open-air museum)", 64.11876, -21.81853),
    ("districts", "Grafarvogur", "Reykjavík", "Spöngin", 64.15011, -21.79109),
    ("districts", "Grafarholt og Úlfarsárdalur", "Reykjavík", "Guðríðarkirkja", 64.12538, -21.75643),
    ("districts", "Kjalarnes", "Reykjavík", "Klébergsskóli (Grundarhverfi)", 64.23764, -21.82592),
    # Kópavogur / Garðabær districts
    ("districts", "Smárinn", "Kópavogur", "Smáralind (shopping centre)", 64.10097, -21.88391),
    ("districts", "Vatnsendi", "Kópavogur", "Kórinn", 64.08260, -21.82506),
    ("districts", "Álftanes", "Garðabær", "Bessastaðir (President's residence)", 64.10601, -21.99504),
    # postal codes
    ("postal", "101", None, "Hallgrímskirkja", 64.14177, -21.92667),
    ("postal", "103", None, "Kringlan (shopping centre)", 64.13023, -21.89483),
    ("postal", "104", None, "Laugardalshöll (sports hall)", 64.14035, -21.87727),
    ("postal", "105", None, "Kjarvalsstaðir (Klambratún)", 64.13787, -21.91395),
    ("postal", "107", None, "Vesturbæjarlaug (swimming pool)", 64.14446, -21.96310),
    ("postal", "109", None, "Mjódd", 64.10970, -21.84152),
    ("postal", "110", None, "Árbæjarsafn (open-air museum)", 64.11876, -21.81853),
    ("postal", "112", None, "Spöngin", 64.15011, -21.79109),
    ("postal", "113", None, "Guðríðarkirkja", 64.12538, -21.75643),
    ("postal", "116", None, "Klébergsskóli (Grundarhverfi)", 64.23764, -21.82592),
    ("postal", "170", None, "Grótta lighthouse", 64.16458, -22.02119),
    ("postal", "200", None, "Ráðhús Kópavogs (town hall)", 64.11125, -21.90805),
    ("postal", "201", None, "Smáralind (shopping centre)", 64.10097, -21.88391),
    ("postal", "203", None, "Kórinn", 64.08260, -21.82506),
    ("postal", "210", None, "Ráðhús Garðabæjar (town hall)", 64.08805, -21.91945),
    ("postal", "220", None, "Ráðhús Hafnarfjarðar (town hall)", 64.06960, -21.95767),
    ("postal", "225", None, "Bessastaðir (President's residence)", 64.10601, -21.99504),
    ("postal", "270", None, "Bæjarskrifstofur Mosfellsbæjar (town hall)", 64.16729, -21.69706),
    # neighbourhoods named after (or famous for) one landmark
    ("nbh", "Skólavörðuholt", "Reykjavík", "Hallgrímskirkja", 64.14177, -21.92667),
    ("nbh", "Öskjuhlíð", "Reykjavík", "Perlan", 64.12925, -21.91901),
    ("nbh", "Kringla", "Reykjavík", "Kringlan (shopping centre)", 64.13023, -21.89483),
    ("nbh", "Háskóli", "Reykjavík", "Háskóli Íslands (University of Iceland)", 64.14178, -21.94654),
    ("nbh", "Klambratún", "Reykjavík", "Kjarvalsstaðir", 64.13787, -21.91395),
    ("nbh", "Laugardalur", "Reykjavík", "Laugardalslaug (swimming pool)", 64.14616, -21.87968),
    ("nbh", "Austurhöfn", "Reykjavík", "Harpa (concert hall)", 64.15037, -21.93281),
]


def main(mapdata, out):
    d = json.load(open(mapdata, encoding="utf-8"))
    out_map, problems = {}, []
    for kind, name, town, poi, lat, lng in LANDMARKS:
        feats = d[kind]["features"]
        if kind == "postal":
            f = next((f for f in feats if f["properties"]["code"] == name), None)
        else:
            f = next((f for f in feats if f["properties"]["name"] == name and (town is None or f["properties"].get("muni") == town)), None)
        if not f:
            problems.append(f"no area found: {kind} {name}")
            continue
        g = shape(f["geometry"])
        if not g.buffer(0.002).contains(Point(lng, lat)):        # ~100-200 m slack for shoreline points
            problems.append(f"outside its area: {poi} not in {kind} {name}")
            continue
        out_map["|".join([kind, name] + ([town] if town else []))] = {"poi": poi, "ll": [lat, lng]}
    # biggest town (by addresses within 2 km) for rural municipalities and postal codes without one
    import math
    def size(t):
        kx = math.cos(math.radians(t["ll"][1]))
        return sum(s[4] for s in d["streets"] if math.hypot((s[2] - t["ll"][0]) * kx, s[3] - t["ll"][1]) * 111.2 < 2)
    towns = sorted(d.get("towns", []), key=lambda t: ({"town": 0, "village": 1}.get(t["place"], 2), -size(t)))
    for kind in ("munis", "postal"):
        for f in d[kind]["features"]:
            p = f["properties"]
            key = f"munis|{p['name']}" if kind == "munis" else f"postal|{p['code']}"
            if key in out_map or (kind == "munis" and "towns" not in p) or (kind == "postal" and not p.get("towns")):
                continue
            g = shape(f["geometry"])
            t = next((t for t in towns if g.contains(Point(*t["ll"]))), None)
            if t:
                out_map[key] = {"poi": t["name"], "ll": [t["ll"][1], t["ll"][0]]}
    json.dump(out_map, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(out_map)} landmarks written")
    for p in problems:
        print("  SKIPPED:", p)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
