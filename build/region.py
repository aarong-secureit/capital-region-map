"""The map's area, shared by every build script.

The map covers all of Iceland. The country is divided into eight regions (landshlutar), each a group of
whole municipalities, a bit like counties: they are used for statistics and by the municipalities' regional
associations. Every piece of land, the highlands included, belongs to one municipality.

Detail differs: the capital region has neighbourhoods, districts and every street, and Akureyri its
neighbourhoods and every street (DETAIL_MUNIS); elsewhere the map has towns and villages, the streets
inside them, and the big roads (this is a learning map, not a navigation tool).
"""
import math
import numpy as np
import shapely
from shapely.geometry import box

# whole map (lon/lat): Iceland with Vestmannaeyjar and Grímsey
W, S, E, N = -24.60, 63.20, -13.30, 66.65

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
    "Skaftárhreppur": "Skaftárhreppur", "Sveitarfélagið Hornafjörður": "Hornafjörður",
    "Vesturbyggð": "Vesturbyggð", "Ísafjarðarbær": "Ísafjarðarbær", "Bolungarvíkurkaupstaður": "Bolungarvík",
    "Súðavíkurhreppur": "Súðavíkurhreppur", "Strandabyggð": "Strandabyggð", "Kaldrananeshreppur": "Kaldrananeshreppur",
    "Árneshreppur": "Árneshreppur",
    "Húnaþing vestra": "Húnaþing vestra", "Húnabyggð": "Húnabyggð", "Sveitarfélagið Skagaströnd": "Skagaströnd",
    "Skagafjörður": "Skagafjörður",
    "Akureyrarbær": "Akureyri", "Fjallabyggð": "Fjallabyggð", "Dalvíkurbyggð": "Dalvíkurbyggð", "Hörgársveit": "Hörgársveit",
    "Eyjafjarðarsveit": "Eyjafjarðarsveit", "Svalbarðsstrandarhreppur": "Svalbarðsstrandarhreppur",
    "Grýtubakkahreppur": "Grýtubakkahreppur", "Þingeyjarsveit": "Þingeyjarsveit", "Tjörneshreppur": "Tjörneshreppur",
    "Norðurþing": "Norðurþing", "Langanesbyggð": "Langanesbyggð",
    "Vopnafjarðarhreppur": "Vopnafjarðarhreppur", "Múlaþing": "Múlaþing", "Fljótsdalshreppur": "Fljótsdalshreppur",
    "Fjarðabyggð": "Fjarðabyggð",
}

# region (landshluti) -> municipalities (short names)
ZONES = {
    "Höfuðborgarsvæðið": ["Reykjavík", "Kópavogur", "Seltjarnarnes", "Garðabær", "Hafnarfjörður", "Mosfellsbær",
                          "Kjósarhreppur"],
    "Suðurnes": ["Reykjanesbær", "Suðurnesjabær", "Vogar", "Grindavík"],
    "Vesturland": ["Akranes", "Hvalfjarðarsveit", "Borgarbyggð", "Eyja- og Miklaholtshreppur", "Snæfellsbær",
                   "Grundarfjörður", "Stykkishólmur", "Dalabyggð"],
    "Vestfirðir": ["Reykhólahreppur", "Vesturbyggð", "Ísafjarðarbær", "Bolungarvík", "Súðavíkurhreppur",
                   "Strandabyggð", "Kaldrananeshreppur", "Árneshreppur"],
    "Norðurland vestra": ["Húnaþing vestra", "Húnabyggð", "Skagaströnd", "Skagafjörður"],
    "Norðurland eystra": ["Akureyri", "Fjallabyggð", "Dalvíkurbyggð", "Hörgársveit", "Eyjafjarðarsveit",
                          "Svalbarðsstrandarhreppur", "Grýtubakkahreppur", "Þingeyjarsveit", "Tjörneshreppur",
                          "Norðurþing", "Langanesbyggð"],
    "Austurland": ["Vopnafjarðarhreppur", "Múlaþing", "Fljótsdalshreppur", "Fjarðabyggð"],
    "Suðurland": ["Ölfus", "Hveragerði", "Árborg", "Flóahreppur", "Grímsnes- og Grafningshreppur", "Bláskógabyggð",
                  "Hrunamannahreppur", "Skeiða- og Gnúpverjahreppur", "Ásahreppur", "Rangárþing ytra",
                  "Rangárþing eystra", "Mýrdalshreppur", "Vestmannaeyjar", "Skaftárhreppur", "Hornafjörður"],
}
ZONE_EN = {"Höfuðborgarsvæðið": "Capital Region", "Suðurnes": "Reykjanes Peninsula", "Vesturland": "West Iceland",
           "Vestfirðir": "Westfjords", "Norðurland vestra": "Northwest Iceland",
           "Norðurland eystra": "Northeast Iceland", "Austurland": "East Iceland", "Suðurland": "South Iceland"}
ZONE_OF = {m: z for z, ms in ZONES.items() for m in ms}
CAP_MUNIS = set(ZONES["Höfuðborgarsvæðið"])

# Neighbourhoods, small areas, named places and every street (not only those in towns): the capital region
# and Akureyri
DETAIL_MUNIS = CAP_MUNIS | {"Akureyri"}
BOX = box(W, S, E, N)

# Outside DETAIL_MUNIS, streets and addresses are kept only in towns: within this many km of a town,
# village or hamlet (OSM place=town / village / hamlet)
TOWN_RADIUS_KM = {"town": 2.5, "village": 1.2, "hamlet": 0.6}

KM = 111.2                                         # km per degree of latitude


def kx(lat):
    """East-west shrink at a latitude: one degree of longitude is kx(lat) degrees of latitude long."""
    return math.cos(math.radians(lat))


def scale(g):
    """Shapes in a near-metric plane (longitude times the cosine of each point's own latitude), for
    buffering, simplifying and measuring; right from Vík (63.4°) to Grímsey (66.5°)."""
    return shapely.transform(g, lambda c: np.column_stack([c[:, 0] * np.cos(np.radians(c[:, 1])), c[:, 1]]))


def unscale(g):
    return shapely.transform(g, lambda c: np.column_stack([c[:, 0] / np.cos(np.radians(c[:, 1])), c[:, 1]]))


def km2(g):
    return scale(g).area * KM * KM


def inb(lon, lat):
    return W <= lon <= E and S <= lat <= N


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
    "880": "Kirkjubæjarklaustur", "881": "Kirkjubæjarklaustur", "780": "Höfn í Hornafirði", "781": "Höfn í Hornafirði",
    "785": "Öræfi",
    # Vestfirðir
    "400": "Ísafjörður", "401": "Ísafjörður", "410": "Hnífsdalur", "415": "Bolungarvík", "416": "Bolungarvík",
    "420": "Súðavík", "421": "Súðavík", "425": "Flateyri", "426": "Flateyri", "430": "Suðureyri", "431": "Suðureyri",
    "450": "Patreksfjörður", "451": "Patreksfjörður", "460": "Tálknafjörður", "461": "Tálknafjörður",
    "465": "Bíldudalur", "466": "Bíldudalur", "470": "Þingeyri", "471": "Þingeyri", "510": "Hólmavík",
    "511": "Hólmavík", "512": "Hólmavík", "520": "Drangsnes", "524": "Árneshreppur",
    # Norðurland vestra
    "500": "Staður", "530": "Hvammstangi", "531": "Hvammstangi", "540": "Blönduós", "541": "Blönduós",
    "545": "Skagaströnd", "546": "Skagaströnd", "550": "Sauðárkrókur", "551": "Sauðárkrókur", "560": "Varmahlíð",
    "561": "Varmahlíð", "565": "Hofsós", "566": "Hofsós", "570": "Fljót",
    # Norðurland eystra
    "580": "Siglufjörður", "581": "Siglufjörður", "600": "Akureyri", "601": "Akureyri", "603": "Akureyri",
    "604": "Akureyri", "605": "Akureyri", "606": "Akureyri", "607": "Akureyri", "610": "Grenivík", "611": "Grímsey",
    "616": "Grenivík", "620": "Dalvík", "621": "Dalvík", "625": "Ólafsfjörður", "626": "Ólafsfjörður", "630": "Hrísey",
    "640": "Húsavík", "641": "Húsavík", "645": "Fosshóll", "650": "Laugar", "660": "Mývatn", "670": "Kópasker",
    "671": "Kópasker", "675": "Raufarhöfn", "676": "Raufarhöfn", "680": "Þórshöfn", "681": "Þórshöfn",
    "685": "Bakkafjörður", "686": "Bakkafjörður",
    # Austurland
    "690": "Vopnafjörður", "691": "Vopnafjörður", "700": "Egilsstaðir", "701": "Egilsstaðir", "710": "Seyðisfjörður",
    "711": "Seyðisfjörður", "715": "Mjóifjörður", "720": "Borgarfjörður eystri", "721": "Borgarfjörður eystri",
    "730": "Reyðarfjörður", "731": "Reyðarfjörður", "735": "Eskifjörður", "736": "Eskifjörður",
    "740": "Neskaupstaður", "741": "Neskaupstaður", "750": "Fáskrúðsfjörður", "751": "Fáskrúðsfjörður",
    "755": "Stöðvarfjörður", "756": "Stöðvarfjörður", "760": "Breiðdalsvík", "761": "Breiðdalsvík",
    "765": "Djúpivogur", "766": "Djúpivogur",
}
# OSM town names shown differently (or dropped: the municipality already carries the name)
TOWN_RENAME = {"Vestmannaeyjabær": "Vestmannaeyjar"}
TOWN_DROP = {"Reykjanesbær"}

BIG_ROADS = {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link", "secondary_link"}


def town_filter(d):
    """For map data d (mapdata.json): a function (lon, lat) -> True in DETAIL_MUNIS (the capital region and
    Akureyri) or within a town's radius elsewhere."""
    from shapely.geometry import shape, Point
    from shapely.ops import unary_union
    from shapely.prepared import prep
    detail = prep(unary_union([shape(f["geometry"]) for f in d["munis"]["features"]
                               if f["properties"]["name"] in DETAIL_MUNIS]).buffer(0.002))
    towns = [(t["ll"][0], t["ll"][1], TOWN_RADIUS_KM[t["place"]]) for t in d.get("towns", [])]

    def ok(lon, lat):
        k = kx(lat)
        if any(math.hypot((lon - x) * k, lat - y) * KM <= r for x, y, r in towns):
            return True
        return detail.contains(Point(lon, lat))
    return ok
