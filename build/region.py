"""The map's area, shared by every build script.

The map covers four of the Icelandic Met Office's forecast zones (spásvæði): the capital region, Faxaflói,
Breiðafjörður and South Iceland. The Met Office publishes the zones only as pictures, so each zone here is a
group of whole municipalities, with their highland parts cut off (the Central Highlands are a forecast
zone of their own).

Detail differs by zone: the capital region has neighbourhoods, districts and every street; elsewhere the map
has towns and villages, the streets inside them, and the big roads (this is a learning map, not a
navigation tool).
"""
from shapely.geometry import Polygon, box

# whole map, and the capital region's detailed part (lon/lat)
W, S, E, N = -24.40, 63.25, -18.50, 65.80
CAP_BOX = (-22.15, 63.95, -21.30, 64.35)

# OSM municipality name -> name shown on the map
MUNI_SHORT = {
    "Reykjavíkurborg": "Reykjavík", "Kópavogsbær": "Kópavogur", "Seltjarnarnesbær": "Seltjarnarnes",
    "Garðabær": "Garðabær", "Hafnarfjarðarkaupstaður": "Hafnarfjörður", "Mosfellsbær": "Mosfellsbær",
    "Kjósarhreppur": "Kjósarhreppur",
    "Reykjanesbær": "Reykjanesbær", "Suðurnesjabær": "Suðurnesjabær", "Sveitarfélagið Vogar": "Vogar",
    "Grindavíkurbær": "Grindavík", "Akraneskaupstaður": "Akranes", "Hvalfjarðarsveit": "Hvalfjarðarsveit",
    "Borgarbyggð": "Borgarbyggð", "Eyja- og Miklaholtshreppur": "Eyja- og Miklaholtshreppur",
    "Snæfellsbær": "Snæfellsbær", "Grundarfjarðarbær": "Grundarfjörður",
    "Sveitarfélagið Stykkishólmur": "Stykkishólmur", "Dalabyggð": "Dalabyggð", "Reykhólahreppur": "Reykhólahreppur",
    "Sveitarfélagið Ölfus": "Ölfus", "Hveragerðisbær": "Hveragerði", "Sveitarfélagið Árborg": "Árborg",
    "Flóahreppur": "Flóahreppur", "Grímsnes- og Grafningshreppur": "Grímsnes- og Grafningshreppur",
    "Bláskógabyggð": "Bláskógabyggð", "Hrunamannahreppur": "Hrunamannahreppur",
    "Skeiða- og Gnúpverjahreppur": "Skeiða- og Gnúpverjahreppur", "Ásahreppur": "Ásahreppur",
    "Rangárþing ytra": "Rangárþing ytra", "Rangárþing eystra": "Rangárþing eystra",
    "Mýrdalshreppur": "Mýrdalshreppur", "Vestmannaeyjabær": "Vestmannaeyjar",
}

# forecast zone -> municipalities (short names). Snæfellsbær goes with Breiðafjörður (its towns face it).
ZONES = {
    "Höfuðborgarsvæðið": ["Reykjavík", "Kópavogur", "Seltjarnarnes", "Garðabær", "Hafnarfjörður", "Mosfellsbær",
                          "Kjósarhreppur"],
    "Faxaflói": ["Reykjanesbær", "Suðurnesjabær", "Vogar", "Grindavík", "Akranes", "Hvalfjarðarsveit", "Borgarbyggð",
                 "Eyja- og Miklaholtshreppur"],
    "Breiðafjörður": ["Snæfellsbær", "Grundarfjörður", "Stykkishólmur", "Dalabyggð", "Reykhólahreppur"],
    "Suðurland": ["Ölfus", "Hveragerði", "Árborg", "Flóahreppur", "Grímsnes- og Grafningshreppur", "Bláskógabyggð",
                  "Hrunamannahreppur", "Skeiða- og Gnúpverjahreppur", "Ásahreppur", "Rangárþing ytra",
                  "Rangárþing eystra", "Mýrdalshreppur", "Vestmannaeyjar"],
}
ZONE_EN = {"Höfuðborgarsvæðið": "Capital Region", "Faxaflói": "Faxaflói (Southwest)",
           "Breiðafjörður": "Breiðafjörður (West)", "Suðurland": "South Iceland"}
ZONE_OF = {m: z for z, ms in ZONES.items() for m in ms}
CAP_MUNIS = set(ZONES["Höfuðborgarsvæðið"])

# Lowland outline: municipalities outside the capital region are cut to this, dropping their highland parts
# (Borgarbyggð, Bláskógabyggð and the Rangárþing municipalities reach far into the highlands). Keeps
# Húsafell, Geysir, Gullfoss, Þjórsárdalur, Hekla, Þórsmörk and Mýrdalur.
LOWLAND = Polygon([
    (-24.40, 65.80), (-21.60, 65.80), (-21.05, 65.35), (-20.75, 64.95), (-20.75, 64.62), (-20.35, 64.42),
    (-19.95, 64.40), (-19.75, 64.25), (-19.55, 64.12), (-19.45, 64.05), (-19.25, 63.95), (-19.15, 63.80),
    (-18.95, 63.70), (-18.50, 63.62), (-18.50, 63.25), (-24.40, 63.25),
])
BOX = box(W, S, E, N)

# Outside the capital region, streets and addresses are kept only in towns: within this many km of a
# town or village (OSM place=town / village).
TOWN_RADIUS_KM = {"town": 2.5, "village": 1.2}


def inb(lon, lat):
    return W <= lon <= E and S <= lat <= N


def in_cap_box(lon, lat):
    w, s, e, n = CAP_BOX
    return w <= lon <= e and s <= lat <= n

# Postal codes outside the capital region -> the town name Pósturinn uses for them
POSTAL_TOWN = {
    "190": "Vogar", "230": "Reykjanesbær", "233": "Reykjanesbær", "235": "Reykjanesbær", "240": "Grindavík",
    "241": "Grindavík", "245": "Suðurnesjabær", "246": "Suðurnesjabær", "250": "Suðurnesjabær",
    "251": "Suðurnesjabær", "260": "Reykjanesbær", "262": "Reykjanesbær",
    "300": "Akranes", "301": "Akranes", "310": "Borgarnes", "311": "Borgarnes", "320": "Reykholt í Borgarfirði",
    "340": "Stykkishólmur", "341": "Stykkishólmur", "342": "Stykkishólmur", "345": "Flatey á Breiðafirði",
    "350": "Grundarfjörður", "351": "Grundarfjörður", "355": "Ólafsvík", "356": "Snæfellsbær",
    "360": "Hellissandur", "370": "Búðardalur", "371": "Búðardalur", "380": "Reykhólahreppur",
    "381": "Reykhólahreppur",
    "800": "Selfoss", "801": "Selfoss", "803": "Selfoss", "804": "Selfoss", "805": "Selfoss", "806": "Selfoss",
    "810": "Hveragerði", "815": "Þorlákshöfn", "816": "Ölfus", "820": "Eyrarbakki", "825": "Stokkseyri",
    "840": "Laugarvatn", "845": "Flúðir", "846": "Flúðir", "850": "Hella", "851": "Hella", "860": "Hvolsvöllur",
    "861": "Hvolsvöllur", "870": "Vík", "871": "Vík", "900": "Vestmannaeyjar",
}
# OSM town names shown differently (or dropped: the municipality already carries the name)
TOWN_RENAME = {"Vestmannaeyjabær": "Vestmannaeyjar"}
TOWN_DROP = {"Reykjanesbær"}

BIG_ROADS = {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link", "secondary_link"}


def town_filter(d):
    """For map data d (mapdata.json): a function (lon, lat) -> True inside the capital region or a town."""
    import math
    from shapely.geometry import shape, Point
    from shapely.ops import unary_union
    from shapely.prepared import prep
    cap = prep(unary_union([shape(f["geometry"]) for f in d["munis"]["features"]
                            if f["properties"]["name"] in CAP_MUNIS]).buffer(0.002))
    rad = {"town": TOWN_RADIUS_KM["town"], "village": TOWN_RADIUS_KM["village"], "hamlet": 0.6}
    towns = [(t["ll"][0], t["ll"][1], rad[t["place"]]) for t in d.get("towns", [])]
    kx = math.cos(math.radians(64.3))

    def ok(lon, lat):
        if any(math.hypot((lon - x) * kx, lat - y) * 111.2 <= r for x, y, r in towns):
            return True
        return cap.contains(Point(lon, lat))
    return ok
