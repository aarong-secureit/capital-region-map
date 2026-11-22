"""Shops, sights, swimming pools, parks and bus hubs shown as icons on the map (and found by the search).

From the Iceland OSM extract:
  - every Bónus, Krónan and Nettó supermarket, and every Hagkaup (supermarket and department store)
  - shopping centres (Kringlan, Smáralind, Fjörður...), second-hand shops and Kolaportið flea market
  - big stores: Costco, IKEA, Elko, BYKO, Húsasmiðjan, Bauhaus, JYSK
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
  - long-distance bus stops: in every town or village outside the capital region that a long-distance bus
    calls at (Strætó's countryside routes 50-96, LONG_LINES, and the public buses linking villages to their
    town, REGIONAL: Ísafjörður's R, G and F and Múlaþing's scheduled routes; not tourist coaches, airport
    shuttles, the ski bus or in-town buses): any stop where 4 or more of these lines call, then the fewest
    more stops that cover the rest of the lines calling there, each with where its lines go. Outside towns,
    the stops at an airport, a ferry port (FERRY) or a sight on this map, and any where 4 or more lines meet
    (Baula). Stops come from OSM's route relations.
  - well-known sights and tourist attractions (SIGHTS, placed by hand from OSM: Hallgrímskirkja, Gullfoss,
    Seljalandsfoss, Bláa lónið, Kirkjufell...). An English name that is a name (capitalised, "Blue Lagoon")
    gets its own search row; a lower-case one ("canyon") only describes the place.
  - public services people new to Iceland need (CIVIC: universities, hospitals, Skatturinn, Sýslumaður,
    Útlendingastofnun, Vinnumálastofnun, Þjóðskrá, the National Archives and Library), in the capital region and Akureyri
Only places inside the map's municipalities are kept (region.py). Outside the capital region, parks are kept
only in towns; big nature areas show up as sights instead.

Usage: python pois.py iceland-latest.osm.pbf MAPDATA_JSON OUT_JSON
"""
import json, math, re, sys
from collections import Counter, defaultdict
import osmium
from shapely.geometry import shape, Point, Polygon
from shapely.ops import unary_union
import region as R

from region import W, S, E, N
GROCERY = ("Bónus", "Krónan", "Nettó", "Hagkaup")
# public services people new to Iceland need: (name shown, lat, lng, English name, kind, extra search words).
# Coordinates from OSM (2026-11); addresses checked on the offices' own pages (island.is, skatturinn.is),
# Skatturinn (OSM still has the old offices) placed at its address.
CIVIC = [
    ("Háskóli Íslands", 64.14052, -21.94945, "University of Iceland", "university", ["university"]),
    ("Háskólinn í Reykjavík", 64.12441, -21.92777, "Reykjavík University", "university", ["university"]),
    ("Listaháskóli Íslands", 64.13687, -21.90279, "Iceland University of the Arts", "university",
     ["university", "art school", "arts university", "academy of the arts"]),
    ("Háskólinn á Akureyri", 65.68545, -18.12135, "University of Akureyri", "university", ["university"]),
    ("Landspítali", 64.13773, -21.92980, "National University Hospital", "hospital", ["hospital", "landspitali hringbraut"]),
    ("Landspítali Fossvogi", 64.12141, -21.89049, "Fossvogur Hospital (emergency room)", "hospital",
     ["hospital", "emergency", "emergency room", "accident and emergency", "bráðamóttaka", "slysadeild"]),
    ("Sjúkrahúsið á Akureyri", 65.67322, -18.09345, "Akureyri Hospital", "hospital", ["hospital", "emergency", "emergency room", "bráðamóttaka"]),
    ("Þjóðskrá Íslands", 64.14633, -21.90226, "Registers Iceland", "office", ["kennitala", "id number", "national registry", "registry"]),
    ("Útlendingastofnun", 64.10555, -21.87077, "Directorate of Immigration", "office", ["immigration", "residence permit", "utl"]),
    ("Vinnumálastofnun", 64.13162, -21.87341, "Directorate of Labour", "office",
     ["labour", "labor", "directorate of labor", "unemployment", "unemployment benefits", "jobs", "work permit", "vmst"]),
    ("Vinnumálastofnun Akureyri", 65.68162, -18.08942, "Directorate of Labour", "office",
     ["labour", "labor", "directorate of labor", "unemployment", "unemployment benefits", "jobs", "work permit", "vmst"]),
    ("Skatturinn", 64.14393, -21.90791, "Iceland Revenue and Customs", "office", ["tax office", "tax", "customs", "skattkort", "rsk"]),
    ("Skatturinn Akureyri", 65.68130, -18.09025, "Iceland Revenue and Customs", "office", ["tax office", "tax", "customs", "skattkort", "rsk"]),
    ("Sýslumaðurinn á höfuðborgarsvæðinu", 64.09793, -21.89011, "District Commissioner", "office",
     ["district office", "syslumadur", "passport", "driving licence", "driver's license", "notary"]),
    ("Sýslumaðurinn á Norðurlandi eystra", 65.68221, -18.09168, "District Commissioner", "office",
     ["district office", "syslumadur", "passport", "driving licence", "driver's license", "notary"]),
    ("Þjóðskjalasafn Íslands", 64.14225, -21.90669, "National Archives of Iceland", "archive", ["archives", "national archives"]),
    ("Þjóðarbókhlaðan", 64.14279, -21.95083, "National and University Library", "library", ["national library", "library", "landsbokasafn"]),
]
# big stores: brand -> OSM shop values it may carry
STORES = {"Costco": {"wholesale"}, "IKEA": {"furniture"}, "Elko": {"electronics"}, "BYKO": {"doityourself", "hardware"},
          "Húsasmiðjan": {"doityourself", "hardware"}, "Bauhaus": {"doityourself", "hardware"}, "JYSK": {"furniture"}}
STORE_SKIP = re.compile(r"Timbursala|Leigumarkað")          # BYKO's lumber yard and tool hire next to the shop
# sights: (name shown, lat, lng, English name or "", kind, extra search words). Coordinates from OSM
# (2026-11), a few by hand where OSM has no point (Brú milli heimsálfa, Fontana, Gamla laugin, Gerðuberg,
# the Sólheimasandur plane wreck).
SIGHTS = [
    # capital region
    ("Hallgrímskirkja", 64.14177, -21.92667, "Hallgrím's Church", "church", ["church"]),
    ("Harpa", 64.15035, -21.93253, "Harpa Concert Hall", "landmark", ["concert hall"]),
    ("Sólfarið", 64.14761, -21.92226, "Sun Voyager", "artwork", ["sun voyager", "solfar"]),
    ("Perlan", 64.12925, -21.91901, "The Pearl", "landmark", ["pearl"]),
    ("Alþingishúsið", 64.14667, -21.94026, "Parliament House", "landmark", ["parliament", "althingi"]),
    ("Tjörnin", 64.14464, -21.94262, "The Pond", "lake", ["pond"]),
    ("Viðey", 64.16440, -21.85404, "Viðey Island", "island", ["island", "imagine peace tower"]),
    ("Árbæjarsafn", 64.11863, -21.81390, "Open Air Museum", "museum", ["open air museum"]),
    ("Gróttuviti", 64.16500, -22.02196, "Grótta Lighthouse", "lighthouse", ["grotta", "lighthouse"]),
    ("Esja", 64.24501, -21.65686, "Mount Esja", "mountain", ["esjan", "mountain"]),
    ("Þríhnúkagígur", 63.99844, -21.69893, "", "volcano", ["inside the volcano", "thrihnukagigur"]),
    ("Reykjavíkurflugvöllur", 64.13000, -21.94000, "Reykjavík Airport", "airport", ["domestic airport", "airport"]),
    ("Ráðhús Reykjavíkur", 64.14613, -21.94238, "Reykjavík City Hall", "public", ["city hall", "town hall", "mayor", "mayor's office", "radhusid"]),
    ("Stjórnarráðshúsið", 64.14730, -21.93524, "Prime Minister's Office", "public", ["government house", "prime minister", "stjornarradid"]),
    ("Bessastaðir", 64.10593, -21.99585, "President's Residence", "public", ["president", "president's house", "presidential residence", "forseti"]),
    ("Höfði", 64.14653, -21.90638, "Höfði House", "landmark", ["reagan gorbachev", "summit house", "hofdi"]),
    ("Dómkirkjan", 64.14665, -21.93934, "Reykjavík Cathedral", "church", ["cathedral", "domkirkjan"]),
    ("Landakotskirkja", 64.14744, -21.94855, "Landakot Cathedral", "church", ["catholic church", "catholic cathedral", "christ the king", "kristskirkja"]),
    ("Þjóðminjasafn Íslands", 64.14200, -21.94813, "National Museum of Iceland", "museum", ["national museum", "thjodminjasafnid"]),
    ("Listasafn Íslands", 64.14411, -21.93922, "National Gallery of Iceland", "museum", ["national gallery", "art museum"]),
    ("Þjóðleikhúsið", 64.14727, -21.93108, "National Theatre", "landmark", ["theatre", "theater", "national theater"]),
    ("Gamla höfnin", 64.15167, -21.94210, "Old Harbour", "landmark", ["old harbor", "harbour", "harbor", "whale watching"]),
    ("Laugardalsvöllur", 64.14354, -21.87892, "National Stadium", "landmark", ["stadium", "football stadium"]),
    # Reykjanes and Faxaflói
    ("Keflavíkurflugvöllur", 63.98500, -22.62350, "Keflavík Airport", "airport", ["kef", "international airport", "airport"]),
    ("Bláa lónið", 63.87963, -22.44813, "Blue Lagoon", "lagoon", ["blue lagoon", "lagoon"]),
    ("Brú milli heimsálfa", 63.86840, -22.67540, "Bridge between Continents", "landmark", ["bridge between continents", "leif the lucky bridge"]),
    ("Gunnuhver", 63.81944, -22.68418, "", "geothermal", ["hot spring"]),
    ("Reykjanesviti", 63.81561, -22.70436, "Reykjanes Lighthouse", "lighthouse", ["lighthouse"]),
    ("Seltún", 63.89525, -22.05552, "Krýsuvík geothermal area", "geothermal", ["krysuvik"]),
    ("Kleifarvatn", 63.92713, -21.97539, "", "lake", ["lake"]),
    ("Fagradalsfjall", 63.89505, -22.28070, "", "volcano", ["geldingadalir", "eruption", "volcano"]),
    ("Akranesviti", 64.30882, -22.09495, "Akranes Lighthouse", "lighthouse", ["lighthouse"]),
    ("Glymur", 64.39081, -21.25146, "", "waterfall", ["waterfall"]),
    ("Deildartunguhver", 64.66361, -21.41057, "", "geothermal", ["hot spring"]),
    ("Krauma", 64.66455, -21.41130, "", "lagoon", ["spa"]),
    ("Snorrastofa", 64.66471, -21.29339, "Snorri's Reykholt", "museum", ["snorri sturluson", "reykholt"]),
    ("Hraunfossar", 64.70256, -20.98060, "", "waterfall", ["waterfall", "lava falls"]),
    ("Barnafoss", 64.70182, -20.97367, "", "waterfall", ["waterfall"]),
    ("Víðgelmir", 64.75022, -20.80190, "", "cave", ["lava cave"]),
    ("Grábrók", 64.77146, -21.53121, "", "volcano", ["crater"]),
    ("Gerðuberg", 64.86060, -22.35940, "basalt columns", "nature", ["basalt columns"]),
    ("Ytri Tunga", 64.80397, -23.08055, "seal beach", "beach", ["seals", "seal beach"]),
    # Snæfellsnes and Breiðafjörður
    ("Kirkjufell", 64.93995, -23.30748, "", "mountain", ["church mountain", "mountain"]),
    ("Kirkjufellsfoss", 64.92616, -23.31236, "", "waterfall", ["waterfall"]),
    ("Búðakirkja", 64.82167, -23.38405, "Black Church at Búðir", "church", ["black church", "budir"]),
    ("Rauðfeldsgjá", 64.79912, -23.64785, "", "nature", ["gorge"]),
    ("Snæfellsjökull", 64.80699, -23.79190, "", "glacier", ["glacier", "volcano"]),
    ("Lóndrangar", 64.73241, -23.78390, "", "nature", ["rock pillars"]),
    ("Djúpalónssandur", 64.75240, -23.90157, "", "beach", ["black beach"]),
    ("Saxhóll", 64.85173, -23.92653, "", "volcano", ["crater"]),
    ("Bjarnarhöfn", 64.99743, -22.96325, "shark museum", "museum", ["shark museum"]),
    ("Eiríksstaðir", 65.05863, -21.53843, "Erik the Red's farm", "museum", ["erik the red", "viking"]),
    # South Iceland
    ("Þingvellir", 64.25910, -21.12125, "Þingvellir National Park", "nature", ["thingvellir", "national park", "golden circle"]),
    ("Silfra", 64.25519, -21.11694, "", "nature", ["snorkeling", "diving"]),
    ("Geysir", 64.31384, -20.29951, "", "geothermal", ["geyser", "golden circle"]),
    ("Strokkur", 64.31270, -20.30077, "", "geothermal", ["geyser"]),
    ("Gullfoss", 64.32661, -20.12168, "", "waterfall", ["waterfall", "golden circle"]),
    ("Kerið", 64.04096, -20.88452, "", "volcano", ["crater", "kerid"]),
    ("Faxi", 64.22511, -20.33650, "", "waterfall", ["vatnsleysufoss", "waterfall"]),
    ("Brúarfoss", 64.26424, -20.51587, "", "waterfall", ["waterfall"]),
    ("Fontana", 64.21470, -20.72960, "", "lagoon", ["laugarvatn", "spa"]),
    ("Gamla laugin", 64.13760, -20.30910, "Secret Lagoon", "lagoon", ["secret lagoon"]),
    ("Friðheimar", 64.17743, -20.44485, "tomato farm", "landmark", ["tomato"]),
    ("Skálholtskirkja", 64.12532, -20.52416, "Skálholt Cathedral", "church", ["skalholt", "church"]),
    ("Hjálparfoss", 64.11587, -19.84978, "", "waterfall", ["waterfall"]),
    ("Gjáin", 64.15018, -19.73626, "", "nature", ["gorge"]),
    ("Þjóðveldisbærinn", 64.11999, -19.82064, "Commonwealth Farm", "museum", ["viking farm"]),
    ("Hekla", 63.99270, -19.66582, "", "volcano", ["volcano"]),
    ("Urriðafoss", 63.92490, -20.67194, "", "waterfall", ["waterfall"]),
    ("Raufarhólshellir", 63.94024, -21.39718, "", "cave", ["lava tunnel", "cave"]),
    ("Reykjadalur", 64.04797, -21.22219, "hot river", "geothermal", ["hot river"]),
    ("Hellisheiðarvirkjun", 64.03679, -21.40006, "geothermal power plant", "landmark", ["power plant", "geothermal exhibition"]),
    ("Seljalandsfoss", 63.61546, -19.98817, "", "waterfall", ["waterfall"]),
    ("Gljúfrabúi", 63.62076, -19.98634, "", "waterfall", ["waterfall", "hidden waterfall"]),
    ("Skógafoss", 63.53210, -19.51129, "", "waterfall", ["waterfall"]),
    ("Kvernufoss", 63.52869, -19.48051, "", "waterfall", ["waterfall"]),
    ("Skógasafn", 63.52614, -19.49300, "Skógar Museum", "museum", ["skogar museum"]),
    ("Seljavallalaug", 63.56614, -19.60767, "", "lagoon", ["pool"]),
    ("Eyjafjallajökull", 63.62999, -19.62139, "", "glacier", ["volcano", "glacier"]),
    ("Sólheimajökull", 63.53077, -19.37088, "", "glacier", ["glacier"]),
    ("Flugvélarflakið á Sólheimasandi", 63.45910, -19.36470, "Sólheimasandur plane wreck", "landmark", ["plane wreck", "dc-3"]),
    ("Dyrhólaey", 63.39883, -19.12663, "", "nature", ["arch", "puffins"]),
    ("Reynisfjara", 63.40504, -19.06695, "black sand beach", "beach", ["black beach", "black sand beach"]),
    ("Reynisdrangar", 63.39894, -19.03379, "", "nature", ["sea stacks"]),
    ("Víkurkirkja", 63.42052, -19.00290, "Vík Church", "church", ["vik church"]),
    ("Mýrdalsjökull", 63.63006, -19.13350, "", "glacier", ["katla", "glacier"]),
    ("Þórsmörk", 63.68668, -19.52100, "", "nature", ["thorsmork"]),
    ("Lava Centre", 63.75329, -20.23627, "", "museum", ["lava center", "hvolsvollur"]),
    ("Landeyjahöfn", 63.53090, -20.11699, "Vestmannaeyjar ferry port", "landmark", ["ferry", "herjolfur"]),
    ("Eldfell", 63.43232, -20.24728, "", "volcano", ["volcano"]),
    ("Eldheimar", 63.43496, -20.26018, "volcano museum", "museum", ["pompeii of the north"]),
    # south-east: Skaftárhreppur and Hornafjörður
    ("Fjaðrárgljúfur", 63.77260, -18.17372, "canyon", "nature", ["canyon"]),
    ("Kirkjugólf", 63.79524, -18.04620, "church floor", "nature", ["basalt"]),
    ("Lakagígar", 64.07019, -18.23631, "Laki craters", "volcano", ["laki", "craters"]),
    ("Eldgjá", 63.96441, -18.61217, "fire canyon", "volcano", ["ofaerufoss", "canyon"]),
    ("Skaftafell", 64.01645, -16.96646, "", "nature", ["national park", "hiking"]),
    ("Svartifoss", 64.02772, -16.97529, "", "waterfall", ["waterfall", "black falls"]),
    ("Hvannadalshnúkur", 64.01415, -16.67696, "highest peak in Iceland", "mountain", ["highest mountain"]),
    ("Vatnajökull", 64.38297, -16.92576, "", "glacier", ["glacier", "national park"]),
    ("Hofskirkja", 63.90704, -16.70673, "turf church", "church", ["turf church", "church"]),
    ("Fjallsárlón", 64.02290, -16.39779, "glacier lagoon", "lake", ["glacier lagoon", "icebergs"]),
    ("Jökulsárlón", 64.04800, -16.18000, "Jökulsárlón Glacier Lagoon", "lake", ["glacier lagoon", "icebergs"]),
    ("Breiðamerkursandur", 64.04314, -16.17825, "Diamond Beach", "beach", ["diamond beach", "ice beach"]),
    ("Vestrahorn", 64.27605, -14.94975, "", "mountain", ["stokksnes", "mountain"]),
    # highlands
    ("Landmannalaugar", 63.99051, -19.06049, "", "geothermal", ["hot springs", "hiking", "laugavegur"]),
    ("Háifoss", 64.20792, -19.68699, "", "waterfall", ["waterfall"]),
    ("Langjökull", 64.69983, -20.14365, "", "glacier", ["glacier", "ice cave"]),
    ("Hofsjökull", 64.80852, -18.80605, "", "glacier", ["glacier"]),
    ("Kerlingarfjöll", 64.62416, -19.25835, "", "geothermal", ["mountains", "hot springs"]),
    ("Hveravellir", 64.86533, -19.55652, "", "geothermal", ["hot springs", "kjolur"]),
    ("Askja", 65.03044, -16.74689, "", "volcano", ["viti", "caldera"]),
    ("Herðubreið", 65.17492, -16.34620, "queen of mountains", "mountain", ["mountain"]),
    ("Snæfell", 64.79751, -15.56155, "", "mountain", ["mountain"]),
    # Vestfirðir
    ("Dynjandi", 65.73278, -23.19925, "", "waterfall", ["waterfall", "fjallfoss"]),
    ("Látrabjarg", 65.50213, -24.53079, "bird cliff", "nature", ["bird cliff", "puffins", "westernmost point"]),
    ("Rauðasandur", 65.44563, -23.96905, "red sand beach", "beach", ["red beach", "beach"]),
    ("Garðar BA 64", 65.51675, -23.83679, "shipwreck", "landmark", ["ship wreck", "gardar"]),
    ("Bolafjall", 66.17837, -23.33159, "", "mountain", ["viewpoint", "platform"]),
    ("Hornstrandir", 66.36180, -22.43903, "nature reserve", "nature", ["nature reserve", "arctic fox"]),
    ("Ísafjarðarflugvöllur", 66.05683, -23.13858, "Ísafjörður Airport", "airport", ["airport"]),
    # Norðurland vestra
    ("Hvítserkur", 65.60588, -20.63730, "sea stack", "nature", ["troll rock", "sea stack"]),
    ("Kolugljúfur", 65.33278, -20.57010, "canyon", "nature", ["canyon"]),
    ("Borgarvirki", 65.47478, -20.59718, "fortress", "landmark", ["fortress"]),
    ("Glaumbær", 65.61103, -19.50470, "turf farm museum", "museum", ["turf houses", "turf farm"]),
    ("Víðimýrarkirkja", 65.53881, -19.47037, "turf church", "church", ["turf church", "church"]),
    ("Hólar í Hjaltadal", 65.73319, -19.11160, "Hólar Cathedral", "church", ["holar", "cathedral"]),
    ("Grettislaug", 65.88223, -19.73654, "hot pool", "lagoon", ["hot pool", "reykir"]),
    # Norðurland eystra
    ("Akureyrarkirkja", 65.67986, -18.09094, "Akureyri Church", "church", ["church"]),
    ("Akureyrarflugvöllur", 65.65699, -18.07332, "Akureyri Airport", "airport", ["airport"]),
    ("Ráðhús Akureyrar", 65.68490, -18.09186, "Akureyri Town Hall", "public", ["town hall", "city hall", "mayor"]),
    ("Hof", 65.68336, -18.08744, "Hof Cultural Centre", "landmark", ["culture house", "cultural center", "concert hall", "menningarhusid hof"]),
    ("Listasafnið á Akureyri", 65.68040, -18.09197, "Akureyri Art Museum", "museum", ["art museum"]),
    ("Minjasafnið á Akureyri", 65.66647, -18.08625, "Akureyri Museum", "museum", ["museum"]),
    ("Jólagarðurinn", 65.58011, -18.09150, "Christmas Garden", "landmark", ["christmas house", "christmas shop", "jolahusid"]),
    ("Skógarböðin", 65.66992, -18.04180, "Forest Lagoon", "lagoon", ["forest lagoon", "spa"]),
    ("Síldarminjasafnið", 66.14757, -18.91339, "Herring Era Museum", "museum", ["herring museum", "siglufjordur"]),
    ("Goðafoss", 65.68282, -17.55062, "", "waterfall", ["waterfall"]),
    ("Aldeyjarfoss", 65.36640, -17.33700, "", "waterfall", ["waterfall"]),
    ("Mývatn", 65.60325, -17.01333, "", "lake", ["lake myvatn", "midge lake"]),
    ("Skútustaðagígar", 65.57138, -17.03373, "pseudocraters", "volcano", ["pseudo craters"]),
    ("Dimmuborgir", 65.58661, -16.89534, "dark castles", "nature", ["lava formations"]),
    ("Hverfjall", 65.60506, -16.87395, "", "volcano", ["crater", "hverfell"]),
    ("Grjótagjá", 65.62641, -16.88297, "", "cave", ["hot spring cave", "game of thrones"]),
    ("Jarðböðin við Mývatn", 65.63046, -16.84760, "Mývatn Nature Baths", "lagoon", ["nature baths", "spa"]),
    ("Hverir", 65.64114, -16.80918, "Námafjall geothermal area", "geothermal", ["namafjall", "mud pots"]),
    ("Krafla", 65.73775, -16.82762, "", "volcano", ["viti", "volcano"]),
    ("Húsavíkurkirkja", 66.04583, -17.34216, "Húsavík Church", "church", ["church"]),
    ("Hvalasafnið á Húsavík", 66.04679, -17.34471, "Húsavík Whale Museum", "museum", ["whale museum"]),
    ("Ásbyrgi", 66.00159, -16.51223, "horseshoe canyon", "nature", ["canyon"]),
    ("Hljóðaklettar", 65.94441, -16.53302, "echo rocks", "nature", ["basalt"]),
    ("Dettifoss", 65.81435, -16.38449, "", "waterfall", ["waterfall", "most powerful waterfall"]),
    ("Heimskautsgerðið", 66.46220, -15.96233, "Arctic Henge", "landmark", ["arctic henge"]),
    # Austurland
    ("Stuðlagil", 65.16233, -15.30812, "basalt canyon", "nature", ["canyon", "basalt columns"]),
    ("Hengifoss", 65.09518, -14.88955, "", "waterfall", ["waterfall"]),
    ("Hallormsstaðaskógur", 65.09537, -14.72071, "largest forest in Iceland", "nature", ["forest", "woods"]),
    ("Skriðuklaustur", 65.04094, -14.95309, "", "museum", ["gunnar gunnarsson"]),
    ("Vök Baths", 65.30307, -14.44748, "", "lagoon", ["vok", "spa"]),
    ("Egilsstaðaflugvöllur", 65.28288, -14.40199, "Egilsstaðir Airport", "airport", ["airport"]),
    ("Seyðisfjarðarkirkja", 65.26132, -14.01060, "Blue Church", "church", ["blue church", "rainbow street"]),
    ("Gufufoss", 65.23995, -14.05750, "", "waterfall", ["waterfall"]),
    ("Hafnarhólmi", 65.54247, -13.75678, "puffin islet", "nature", ["puffins", "borgarfjordur eystri"]),
    ("Steinasafn Petru", 64.83572, -13.88052, "Petra's Stone Collection", "museum", ["stone collection"]),
    ("Eggin í Gleðivík", 64.66191, -14.29513, "Eggs of Merry Bay", "artwork", ["eggs", "djupivogur"]),
]
# The main grocery store of each town or village outside the capital region that has no Bónus, Krónan, Nettó
# or Hagkaup nearby (picked from OSM: a supermarket or a known grocery name such as Kjörbúðin, Krambúðin or a
# kaupfélag over a corner shop; fuel stations and grills left out). (name, lat, lng, street address, town)
LOCAL_GROCERIES = [
    ("Kjörbúðin", 65.65983, -20.28474, "Húnabraut 4", "Blönduós"),
    ("Kjörbúðin", 65.97305, -18.53155, "Hafnartorg", "Dalvík"),
    ("Kjörbúðin", 65.07086, -14.01377, "Strandgata 50", "Eskifjörður"),
    ("Kjörbúðin", 64.92993, -14.01129, "Skólavegur 59", "Fáskrúðsfjörður"),
    ("Kjörbúðin", 64.07047, -22.65022, "Sunnubraut 4", "Garður"),
    ("Kjörbúðin", 64.92531, -23.26022, "Grundargata 38", "Grundarfjörður"),
    ("Kjörbúðin", 63.83484, -20.40123, "Suðurlandsvegur 1", "Hella"),
    ("Spar", 65.14733, -13.69239, "Hafnarbraut 13", "Neskaupstaður"),
    ("Kjörbúðin", 66.07370, -18.64500, "Aðalgata 2", "Ólafsfjörður"),
    ("Kassinn", 64.89742, -23.70913, "", "Ólafsvík"),
    ("Fjölval", 65.59833, -24.00113, "", "Patreksfjörður"),
    ("Kjörbúðin", 64.03937, -22.70635, "Miðnestorg 1", "Sandgerði"),
    ("Skagfirðingabúð", 65.74140, -19.63738, "Ártorg 1", "Sauðárkrókur"),
    ("Kjörbúðin", 65.25995, -14.00876, "Vesturvegur 1", "Seyðisfjörður"),
    ("Kjörbúðin", 66.15076, -18.91058, "Suðurgata 2-4", "Siglufjörður"),
    ("Vogus", 63.98066, -22.37917, "Iðndalur 2", "Vogar"),
    ("Kauptún", 65.75377, -14.82691, "", "Vopnafjörður"),
    ("Vegamót", 65.68553, -23.60088, "", "Bíldudalur"),
    ("Kaupfjelagið", 64.79207, -14.00939, "", "Breiðdalsvík"),
    ("Krambúðin", 65.10807, -21.76282, "Vesturbraut 10", "Búðardalur"),
    ("Kjörbúðin", 64.65597, -14.28603, "Búland 1", "Djúpivogur"),
    ("Krambúðin", 64.13102, -20.32098, "Grund", "Flúðir"),
    ("Jónsabúð", 65.94675, -18.18145, "", "Grenivík"),
    ("KS Hofsós", 65.89724, -19.41295, "Suðurbraut 9", "Hofsós"),
    ("Krambúðin", 65.70082, -21.68588, "Höfðatún 4", "Hólmavík"),
    ("Hríseyjarbúðin", 65.97950, -18.37689, "Norðurvegur 7", "Hrísey"),
    ("Kaupfélag Vestur-Húnvetninga", 65.39587, -20.94675, "", "Hvammstangi"),
    ("Gvendarkjör", 63.79023, -18.04784, "Klausturvegur 13", "Kirkjubæjarklaustur"),
    ("Verslunin Skerjakolla", 66.30035, -16.44784, "Bakkagata 10", "Kópasker"),
    ("Krambúðin", 64.21686, -20.73401, "Dalbraut 8", "Laugarvatn"),
    ("Reykhólabúðin", 65.45161, -22.20156, "", "Reykhólar"),
    ("Bjarnabúð", 64.17708, -20.45357, "", "Reykholt"),
    ("Krambúðin", 65.64172, -16.91054, "Hraunvegur 10", "Reykjahlíð"),
    ("Kjörbúðin", 65.82460, -20.30592, "Bogabraut 1", "Skagaströnd"),
    ("Hjá Jóhönnu", 65.62686, -23.82580, "", "Tálknafjörður"),
    ("Kjörbúðin", 66.19847, -15.33731, "Langanesvegur 2", "Þórshöfn"),
    ("Verslunin Árborg", 64.04132, -20.25097, "", "Árnes"),
    ("Búðin", 65.52720, -13.81670, "", "Bakkagerði"),
    ("Kaupfélag Steingrímsfjarðar", 65.68932, -21.44230, "", "Drangsnes"),
    ("Verslunin Vala", 64.06583, -20.64439, "", "Sólheimar"),
    ("Víkurbúðin", 66.02605, -22.99142, "", "Súðavík"),
]
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
         "Sky Lagoon": ("Sky Lagoon", "spa", ["lagoon", "spa"]),
         # outside the capital region (OSM name -> name shown)
         "Vatnaveröld": ("Vatnaveröld", "pool", ["sundmidstod reykjanesbaejar", "keflavik pool"]),
         "Sundlaug Njarðvíkur": ("Sundlaug Njarðvíkur", "pool", []), "Sundlaug Grindavíkur": ("Sundlaug Grindavíkur", "pool", []),
         "Íþróttamiðstöð Sandgerðisbæjar": ("Sundlaug Sandgerðis", "pool", []),
         "Íþróttamiðstöðin Garði": ("Sundlaugin í Garði", "pool", []), "Íþróttamiðstöðin Vogum": ("Sundlaugin í Vogum", "pool", []),
         "Jaðarsbakkalaug": ("Jaðarsbakkalaug", "pool", []), "Bjarnalaug": ("Bjarnalaug", "pool", []),
         "Íþróttamiðstöðin Borgarnesi": ("Sundlaugin í Borgarnesi", "pool", []),
         "Íþróttamiðstöðin Kleppjárnsreykjum": ("Sundlaugin á Kleppjárnsreykjum", "pool", []),
         "Íþróttamiðstöðin Varmalandi": ("Sundlaugin á Varmalandi", "pool", []),
         "Sundlaugin Húsafelli": ("Sundlaugin á Húsafelli", "pool", []), "Hreppslaug": ("Hreppslaug", "pool", []),
         "Sundlaugin að Hlöðum": ("Sundlaugin að Hlöðum", "pool", []), "Lýsuhólslaug": ("Lýsuhólslaug", "pool", []),
         "Sundlaug Snæfellsbæjar": ("Sundlaug Snæfellsbæjar", "pool", ["olafsvik pool"]),
         "Sundlaug og íþróttamiðstöð Stykkishólms": ("Sundlaug Stykkishólms", "pool", []),
         "Sælingsdalslaug": ("Sælingsdalslaug", "pool", []), "Guðrúnarlaug": ("Guðrúnarlaug", "pool", ["hot pot"]),
         "Sundlaugin Grettislaug": ("Grettislaug", "pool", ["reykholar pool"]),
         "Laugaskarð": ("Laugaskarð", "pool", ["hveragerdi pool"]), "Sundhöll Selfoss": ("Sundhöll Selfoss", "pool", []),
         "Sundlaug Stokkseyrar": ("Sundlaug Stokkseyrar", "pool", []), "Sundlaug Þorlákshafnar": ("Sundlaug Þorlákshafnar", "pool", []),
         "Íþróttamiðstöðin Borg": ("Sundlaugin á Borg", "pool", []), "Laugarvatnslaug": ("Laugarvatnslaug", "pool", []),
         "Reykholtslaug": ("Reykholtslaug", "pool", []), "Sundlaugin á Flúðum": ("Sundlaugin á Flúðum", "pool", []),
         "Hrunalaug": ("Hrunalaug", "pool", ["hot pot"]), "Neslaug": ("Neslaug", "pool", []),
         "Brautarholtslaug": ("Brautarholtslaug", "pool", []), "Þjórsárdalslaug": ("Þjórsárdalslaug", "pool", []),
         "Sundlaugin Hellu": ("Sundlaugin á Hellu", "pool", []), "Sundlaugin Laugalandi": ("Sundlaugin á Laugalandi", "pool", []),
         "Sundlaugin Hvolsvelli": ("Sundlaugin á Hvolsvelli", "pool", []), "Sundlaugin Vík": ("Sundlaugin í Vík", "pool", []),
         "Sundlaug og íþróttamiðstöð Vestmannaeyja": ("Sundlaug Vestmannaeyja", "pool", []),
         "Sundlaugin Kirkjubæjarklaustri": ("Sundlaugin á Kirkjubæjarklaustri", "pool", []),
         "Sundlaug Hafnar": ("Sundlaug Hafnar", "pool", ["hofn pool"]),
         # Vestfirðir
         "Sundhöll Ísafjarðar": ("Sundhöll Ísafjarðar", "pool", ["isafjordur pool"]),
         "Íþrottamiðstöð Árbær": ("Sundlaug Bolungarvíkur", "pool", []),
         "Flateyrarlaug": ("Flateyrarlaug", "pool", []), "Sundlaug Suðureyrar": ("Sundlaug Suðureyrar", "pool", []),
         "Sundlaugin á Þingeyri": ("Sundlaugin á Þingeyri", "pool", []),
         "Brattahlíð (Steep hill)": ("Sundlaug Patreksfjarðar", "pool", []),
         "Íþróttamiðstöðin á Tálknafirði": ("Sundlaug Tálknafjarðar", "pool", []),
         "Íþróttamiðstöðin Byltu": ("Sundlaugin á Bíldudal", "pool", []),
         "Sundlaugin Birkimel": ("Sundlaugin Birkimel", "pool", []),
         "Pollurinn": ("Pollurinn", "pool", ["hot pot"]), "Krossneslaug": ("Krossneslaug", "pool", ["hot pool"]),
         "Sundlaug Hólmavíkur": ("Sundlaug Hólmavíkur", "pool", []),
         "Sundlaugin á Drangsnesi": ("Sundlaugin á Drangsnesi", "pool", []),
         # Norðurland vestra
         "Íþróttamiðstöðin Blönduósi": ("Sundlaug Blönduóss", "pool", []),
         "Sundlaugin á Skagaströnd": ("Sundlaugin á Skagaströnd", "pool", []),
         "Sundlaug Sauðárkróks": ("Sundlaug Sauðárkróks", "pool", []),
         "Sundlaugin í Varmahlíð": ("Sundlaugin í Varmahlíð", "pool", []),
         "Sundlaugin á Hofsósi": ("Sundlaugin á Hofsósi", "pool", ["hofsos pool"]),
         # Norðurland eystra
         "Sundhöll Siglufjarðar": ("Sundhöll Siglufjarðar", "pool", []),
         "Íþróttamiðstöð Ólafsfjarðar": ("Sundlaug Ólafsfjarðar", "pool", []),
         "Íþróttamiðstöð Dalvíkur": ("Sundlaug Dalvíkur", "pool", []),
         "Sundlaug Akureyrar": ("Sundlaug Akureyrar", "pool", ["akureyri pool"]), "Glerárlaug": ("Glerárlaug", "pool", []),
         "Þelamerkurlaug": ("Þelamerkurlaug", "pool", []), "Sundlaug Hríseyjar": ("Sundlaug Hríseyjar", "pool", []),
         "Sundlaugin í Grímsey": ("Sundlaugin í Grímsey", "pool", []),
         "Sundlaugin Grenivík": ("Sundlaugin á Grenivík", "pool", []),
         "Sundlaug Svalbarðsstrandar": ("Sundlaug Svalbarðsstrandar", "pool", []),
         "Sundlaug Eyjafjarðarsveitar": ("Sundlaug Eyjafjarðarsveitar", "pool", ["hrafnagil"]),
         "Sundlaugin Illugastöðum": ("Sundlaugin á Illugastöðum", "pool", []),
         "Sundlaug Húsavíkur": ("Sundlaug Húsavíkur", "pool", []),
         "Laugar swimming pool": ("Sundlaugin á Laugum", "pool", []),
         "Sundlaugin Lundi": ("Sundlaugin í Lundi", "pool", []),
         "Sundlaug Raufarhafnar": ("Sundlaug Raufarhafnar", "pool", []),
         "Sundlaug Þórshafnar": ("Sundlaug Þórshafnar", "pool", []),
         # Austurland
         "Selárdalslaug": ("Selárdalslaug", "pool", ["vopnafjordur pool"]),
         "Íþróttamiðstöðin á Egilsstöðum": ("Sundlaugin á Egilsstöðum", "pool", []),
         "Sundhöll Seyðisfjarðar": ("Sundhöll Seyðisfjarðar", "pool", []),
         "Stefánslaug": ("Stefánslaug", "pool", ["neskaupstadur pool"]),
         "Sundlaug Eskifjarðar": ("Sundlaug Eskifjarðar", "pool", []),
         "Sundlaug Fáskrúðsfjarðar": ("Sundlaug Fáskrúðsfjarðar", "pool", []),
         "Sundlaug Stöðvarfjarðar": ("Sundlaug Stöðvarfjarðar", "pool", []),
         "Sundlaugin Breiðdalsvík": ("Sundlaugin á Breiðdalsvík", "pool", []),
         "Íþróttamiðstöð Djúpavogs": ("Sundlaugin á Djúpavogi", "pool", [])}
# shopping centres OSM does not tag as malls: name -> (lat, lng, street)
MANUAL_MALLS = {"Spöngin": (64.15060, -21.78830, "Spöngin")}
HUBS = ["Fjörður", "Ásgarður", "Hamraborg", "Mjódd", "Ártún", "Spöngin", "Háholt"]   # Strætó's own list
CENTRE = ["Hlemmur", "Lækjartorg"]
TERMINAL = "BSÍ"
# stops OSM does not show right now: name -> (lat, lng)
MANUAL_STOPS = {"Hlemmur": (64.14318, -21.91470)}
# long-distance buses: Strætó's countryside routes (landsbyggðarvagnar) by number, where they go
LONG_LINES = {"50": "Reykjavík – Akranes – Borgarnes", "51": "Reykjavík – Selfoss", "52": "Reykjavík – Vík – Höfn",
              "53": "Selfoss – Landeyjahöfn", "55": "Reykjavík – Keflavík Airport", "56": "Akureyri – Egilsstaðir",
              "57": "Reykjavík – Akureyri", "58": "Borgarnes – Stykkishólmur", "59": "Borgarnes – Hólmavík",
              "62": "Ísafjörður – Patreksfjörður", "63": "Borgarnes – Varmaland", "64": "Borgarnes – Kleppjárnsreykir",
              "65": "Borgarnes – Búðardalur", "66": "Patreksfjörður – Bíldudalur", "71": "Hveragerði – Þorlákshöfn",
              "72": "Selfoss – Borg – Flúðir", "73": "Selfoss – Flúðir – Borg", "78": "Akureyri – Siglufjörður",
              "79": "Akureyri – Húsavík", "82": "Stykkishólmur – Hellissandur", "84": "Blönduós – Skagaströnd",
              "87": "Reykjanesbær – Vogar", "89": "Reykjanesbær – Sandgerði – Garður", "91": "Egilsstaðir – Neskaupstaður",
              "92": "Fáskrúðsfjörður – Breiðdalsvík", "93": "Egilsstaðir – Seyðisfjörður", "94": "Höfn – Djúpivogur",
              "94S": "Djúpivogur – Breiðdalsvík", "96": "Fáskrúðsfjörður – Neskaupstaður"}
# and the public buses that link villages to the nearest town: (network, ref) -> (line shown, where it goes)
REGIONAL = {("Strætisvagnar Ísafjarðar", "R"): ("R", "Ísafjörður bus R: Ísafjörður – Flateyri – Þingeyri"),
            ("Strætisvagnar Ísafjarðar", "G"): ("G", "Ísafjörður bus G: Ísafjörður – Suðureyri"),
            ("Strætisvagnar Ísafjarðar", "F"): ("F", "Ísafjörður bus F: Ísafjörður – Bolungarvík"),
            **{("Almenningssamgöngur í Múlaþingi", r): ("", "Múlaþing bus: Egilsstaðir – Djúpivogur") for r in ("DV - EG", "EG - DV")},
            **{("Almenningssamgöngur í Múlaþingi", r): ("", "Múlaþing bus: Egilsstaðir – Borgarfjörður eystri") for r in ("BE - EG", "EG - BE")},
            **{("Almenningssamgöngur í Múlaþingi", r): ("", "Múlaþing bus: Egilsstaðir – Hallormsstaður") for r in ("EG - HS", "HS - EG")}}
STOP_NAME = {"Laugarás. Bláskógabyggð": "Laugarás"}     # stop names to tidy
# ferry ports a long-distance bus calls at, and where the ferry goes
FERRY = {"Landeyjahöfn": "for the Herjólfur ferry to Vestmannaeyjar",
         "Brjánslækur": "for the Baldur ferry to Flatey and Stykkishólmur"}
# second-hand shops and the flea market: extra words people search with
SECOND_WORDS = {"Góði hirðirinn": ["good shepherd", "sorpa"], "Kolaportið": ["kolaport", "flea market"]}
STORE_WORDS = {"Elko": ["electronics"], "BYKO": ["hardware", "diy"], "Húsasmiðjan": ["hardware", "diy"],
               "Bauhaus": ["hardware", "diy"], "JYSK": ["furniture"], "IKEA": ["furniture"], "Costco": ["wholesale"]}


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(math.radians((a[1] + b[1]) / 2)), (a[1] - b[1]) * 110540)


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.shops, self.malls, self.second, self.sights = [], {}, [], []
        self.platforms = defaultdict(list)      # base name -> [(letter, lon, lat)]
        self.stations = {}
        self.stop_nodes = {}                    # node id -> (stop name without platform letter, lon, lat)
        self.routes = []                        # (line number, [member node ids]) for Strætó bus routes
        self.long = []                          # (line shown, "Strætó 57: Reykjavík – Akureyri", [member node ids])
        self.parks = {}                         # name -> (kind, km2, (lon, lat), bbox)
        self.pools = {}                         # OSM name -> (lon, lat, is_area)
        self.ports = []                         # (name, "airport" | "ferry", (lon, lat)): airports with flights, ferry terminals

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
        if name in POOLS and (name not in self.pools or (kind == "a" and not self.pools[name][2])):
            self.pools[name] = (lon, lat, kind == "a")      # prefer the building/area over entrance nodes
        if t.get("highway") == "bus_stop" or t.get("public_transport") == "platform":
            m = re.fullmatch(r"(.+?) ([A-Z])(?: \(.*\))?", name)
            base, letter = (m.group(1), m.group(2)) if m else (name, t.get("local_ref", ""))
            if base:
                self.platforms[base].append((letter if re.fullmatch(r"[A-Z]", letter or "") else "", lon, lat))
        if t.get("amenity") == "bus_station" and name:
            self.stations[name] = (lon, lat)
        if name and ((t.get("aeroway") == "aerodrome" and t.get("iata")) or t.get("amenity") == "ferry_terminal"):
            self.ports.append((name, "airport" if t.get("aeroway") else "ferry", (lon, lat)))

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
        if t.get("type") != "route" or t.get("route") != "bus":
            return
        ref, net = t.get("ref", ""), t.get("network", "")
        members = [m.ref for m in r.members if m.type == "n"]
        straeto = "Strætó" in t.get("operator", "") or net.startswith("Strætó")
        if ref and ("Strætó" in t.get("operator", "") or net.startswith("Strætó Höfuðborgarsvæðið")):
            self.routes.append((ref, members))
        if straeto and ref in LONG_LINES:
            self.long.append((ref, f"Strætó {ref}: {LONG_LINES[ref]}", members))
        elif straeto and re.fullmatch(r"[5-9]\d\w?", ref):
            print(f"  long-distance line {ref} not in LONG_LINES: {t.get('name')}")
        elif (net, ref) in REGIONAL:
            self.long.append((*REGIONAL[(net, ref)], members))

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
        km2 = g.area * 111.32 * 111.32 * math.cos(math.radians((y0 + y1) / 2))
        if wood and km2 < 0.3:                  # only big named woods (Heiðmörk...)
            return
        kind = ("botanical" if t.get("garden:type") == "botanical" else "garden") if le == "garden" else \
               "reserve" if le == "nature_reserve" else "wood" if wood else "park"
        c = (max(g.geoms, key=lambda x: x.area) if g.geom_type == "MultiPolygon" else g).representative_point()
        if name not in self.parks or km2 > self.parks[name][1]:
            self.parks[name] = (kind, km2, (c.x, c.y), (x0, y0, x1, y1))

    def area(self, a):
        self.park(a)
        if not (a.tags.get("shop") or a.tags.get("tourism") or a.tags.get("amenity") or a.tags.get("aeroway") == "aerodrome"
                or a.tags.get("name") in POOLS):
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

    NEAR = 0.004                                      # ~200-400 m: harbour fronts just outside the mapped coastline

    def muni_at(lon, lat):
        pt = Point(lon, lat)
        hit = next((n for n, g in munis if g.contains(pt)), None)
        if hit:
            return hit
        d, n = min((g.distance(pt), n) for n, g in munis)
        return n if d <= NEAR else None

    def postal_at(lon, lat):
        pt = Point(lon, lat)
        hit = next(((c, t) for c, t, g in postal if g.contains(pt)), None)
        if hit:
            return hit
        d, c, t = min((g.distance(pt), c, t) for c, t, g in postal)
        return (c, t) if d <= NEAR else (None, None)

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
    # towns without a chain supermarket: their own grocery store (Kjörbúðin, Krambúðin, the kaupfélag...)
    many_local = {n for n, k in Counter(r[0] for r in LOCAL_GROCERIES).items() if k > 1}
    for name, lat, lon, addr, town in LOCAL_GROCERIES:                # one per town: "Kjörbúðin Blönduós"
        add({"name": f"{name} {town}" if name in many_local else name, "cat": "grocery", "kind": "local",
             "brand": name, "addr": addr, "town": town, "g": f"{name}, {town}", "words": ["grocery", "shop", "milk", town]},
            lon, lat)
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
    towns = d.get("towns", [])

    def near_town(lon, lat):
        return any(metres(t["ll"], (lon, lat)) <= 1000 * R.TOWN_RADIUS_KM[t["place"]] for t in towns)
    for name, (kind, km2, (lon, lat), bb) in sorted(h.parks.items()):
        mu = muni_at(lon, lat)
        if mu and mu not in R.DETAIL_MUNIS and not (kind in ("park", "garden", "botanical") and near_town(lon, lat)):
            continue                                        # rural nature areas: the big ones are sights
        add({"name": name, "cat": "park", "kind": kind, "km2": round(km2, 3), "bb": [round(v, 5) for v in bb],
             "g": f"{name}, {{PC}}"}, lon, lat)
    for osm_name, (lon, lat, _) in sorted(h.pools.items()):
        name, kind, words = POOLS[osm_name]
        add({"name": name, "cat": "pool", "kind": kind, "words": words, "g": f"{name}, {{PC}}"}, lon, lat)
    missing = sorted(set(POOLS) - set(h.pools))
    if missing:
        print("  pools not found in OSM:", ", ".join(missing))
    for name, lat, lon, en, kind, words in SIGHTS:
        add({"name": name, "cat": "sight", "kind": kind, "en": en, "words": words, "g": f"{en if name.startswith('Flugvél') else name}, Iceland"}, lon, lat)
    for name, lat, lon, en, kind, words in CIVIC:
        add({"name": name, "cat": "civic", "kind": kind, "en": en, "words": words, "g": f"{name}, Iceland"}, lon, lat)

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
    # any other capital-region stop served by 4 or more lines (busiest first, so a same-named smaller stop is skipped);
    # outside the capital region such stops are shown as long-distance stops, below
    taken = {(p["name"], p["muni"]) for p in pois if p["cat"] == "bus"}
    mid = lambda c: (sum(x for x, _ in c["pts"]) / len(c["pts"]), sum(y for _, y in c["pts"]) / len(c["pts"]))
    for base, c in sorted(((b, c) for b, cs in clusters.items() for c in cs if len(c["lines"]) >= 4),
                          key=lambda bc: -len(bc[1]["lines"])):
        if base in used:
            continue
        lon, lat = mid(c)
        muni = muni_at(lon, lat)
        if muni not in R.CAP_MUNIS or (base, muni) in taken:
            continue
        taken.add((base, muni))
        add({"name": base, "cat": "bus", "kind": "stop", "stops": "", "lines": sorted(c["lines"], key=line_key)}, lon, lat)

    # long-distance buses outside the capital region. In every town they call at: any stop where 4 or more lines
    # call, then the fewest more stops that cover the rest of its lines (most lines first, then nearest the centre).
    # Outside towns: stops at an airport, ferry port or sight on this map, and any stop where 4 or more lines meet.
    for c in node_cluster.values():
        c.setdefault("long", {})
    for line, label, members in h.long:
        for m in members:
            if m in node_cluster:
                node_cluster[m]["long"][label] = line

    def town_of(base, lon, lat):
        """Town or village a stop is in: within its radius, or named after it and within 3 km ("Skógar")."""
        near = [(metres(t["ll"], (lon, lat)), t) for t in d["towns"]]
        inside = [(m, t) for m, t in near if m <= R.TOWN_RADIUS_KM.get(t["place"], 2.5) * 1000]
        named = [(m, t) for m, t in near if m <= 3000 and re.split(r" - |, ", base)[0] == t["name"]]
        return min(inside or named, key=lambda mt: mt[0], default=(0, None))[1]

    # what a stop outside town is at: a sight on this map within 1 km (an airport within 1.5 km), else an
    # airport with flights (IATA code) within 1.5 km or a ferry terminal within 1 km.
    # Gives (name, English name, "airport" | "ferry" | "sight").
    marks = [(p["name"], p.get("en", ""), "airport" if p["kind"] == "airport" else "sight", tuple(p["ll"]),
              1500 if p["kind"] == "airport" else 1000) for p in pois if p["cat"] == "sight"]
    n_sights = len(marks)
    marks += [(name, "", kind, ll, 1500 if kind == "airport" else 1000) for name, kind, ll in h.ports]

    def at_what(lon, lat):
        near = [(i >= n_sights, metres(ll, (lon, lat)), (name, en, "ferry" if name in FERRY else kind))
                for i, (name, en, kind, ll, r) in enumerate(marks) if metres(ll, (lon, lat)) <= r]
        return min(near, key=lambda m: m[:2], default=(0, 0, None))[2]      # sights first, then the nearest

    long_order = lambda label: (0, line_key(label.split()[1].rstrip(":"))) if label.startswith("Strætó") else (1, label)

    def coach(base, c, lon, lat, town=None, at=None):
        name = STOP_NAME.get(base, base)
        if (name, muni_at(lon, lat)) in taken:
            return
        taken.add((name, muni_at(lon, lat)))
        labels = sorted(c["long"], key=long_order)
        rec = {"name": name, "cat": "bus", "kind": "coach",
               "lines": sorted({c["long"][l] for l in labels if c["long"][l]}, key=line_key), "routes": labels}
        places, extra = [], []
        if town:
            rec["town"], places = town, [town]
        elif at:
            rec["at"], places = at[0], [w for w in at[:2] if w]
            if at[0] in FERRY:
                rec["ferry"] = FERRY[at[0]]
            extra = {"airport": ["airport"], "ferry": ["ferry", "ferry port"]}.get(at[2], [])
        rec["words"] = ["long distance bus", "coach", "intercity bus", "landsbyggdarvagn", *places,     # "bus Selfoss"
                        *(f"{w} {p}" for p in places + extra for w in ("bus", "bus stop", "long distance bus", "coach")),
                        *(f"{p} bus" for p in extra)]
        add(rec, lon, lat)

    by_town, outside = defaultdict(list), []
    for base, cs in clusters.items():
        for c in cs:
            if not c["long"]:
                continue
            lon, lat = mid(c)
            if muni_at(lon, lat) in R.CAP_MUNIS:
                continue
            t = town_of(base, lon, lat)
            if t and t["muni"] in R.CAP_MUNIS:
                continue
            if t:
                by_town[(t["name"], t["muni"])].append((base, c, lon, lat, t))
            else:
                outside.append((base, c, lon, lat))
    for (town, muni), cand in sorted(by_town.items()):
        need = set().union(*(c["long"] for _, c, _, _, _ in cand))
        pick = [x for x in cand if len(x[1]["long"]) >= 4]          # 4+ lines: an important stop anyway
        for x in pick:
            need -= set(x[1]["long"])
        while need:
            x = max(cand, key=lambda x: (len(need & set(x[1]["long"])), -metres(x[4]["ll"], (x[2], x[3]))))
            need -= set(x[1]["long"])
            pick.append(x)
        for base, c, lon, lat, t in pick:
            coach(base, c, lon, lat, town=town)
    for base, c, lon, lat in sorted(outside, key=lambda x: x[0]):
        at = at_what(lon, lat)
        if at or len(c["long"]) >= 4:
            coach(base, c, lon, lat, at=at)

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
        print(f"  {cat}:", ", ".join(p["name"] for p in pois if p["cat"] == cat))
    if skipped:
        print("outside the map's municipalities, skipped:", len(skipped))


if __name__ == "__main__":
    main(*sys.argv[1:4])
