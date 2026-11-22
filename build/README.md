# Rebuilding capital-region-map.html

The map's area is set in `region.py`: four of Iceland's eight regions (landshlutar: the capital region,
Suðurnes, Vesturland, Suðurland) plus Reykhólahreppur from Vestfirðir, each a group of municipalities, with
the highlands cut off (`LOWLAND`). The capital region gets full detail; elsewhere the map keeps towns and
villages, the streets in them (`TOWN_RADIUS_KM`), big roads and sights.

Run from `build/`. Needs Python 3 with `pip install osmium shapely numpy scipy pillow` (here in `.venv`;
`build_data.py` takes about 8 minutes):

```bash
mkdir -p data osm
curl -L -o osm/iceland-latest.osm.pbf https://download.geofabrik.de/europe/iceland/iceland-latest.osm.pbf
B="https://lukrgatt.reykjavik.is/server/rest/services/OpinGognMorkSkiptingar"
for SV in Hverfaheiti Stjornsysluskipting Ibudahverfi_hverfaskipulags; do
  curl -s "$B/$SV/MapServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=geojson&resultRecordCount=2000" -o data/rvk_$SV.geojson
done
python extract_osm.py osm/iceland-latest.osm.pbf data/osm_extract.json
python extract_coast.py osm/iceland-latest.osm.pbf data/coast.json
python build_data.py data data/mapdata.json
python islands.py osm/iceland-latest.osm.pbf data/coast.json data/mapdata.json
python landmarks.py data/mapdata.json landmarks.json
python pois.py osm/iceland-latest.osm.pbf data/mapdata.json pois.json
python addresses.py osm/iceland-latest.osm.pbf data/mapdata.json ../_assets/addresses.js
python streets_geo.py osm/iceland-latest.osm.pbf data/mapdata.json ../_assets/streets.js roads.json
.venv-tts/bin/python make_audio.py clips voices/is_IS-ugla-medium.onnx data/mapdata.json ../_assets/audio pois.json aliases.json roads.json
python inject.py data/mapdata.json template.html ../capital-region-map.html ../_assets/audio/index.json landmarks.json pois.json aliases.json roads.json
```

- `landmarks.py`: the well-known spot each big area shares to Google Maps (town hall, main church,
  shopping centre). Edit the `LANDMARKS` list; it checks each point lies inside its area. Rural
  municipalities and postal codes without one share their biggest town.
- `pois.py`: every Bónus, Krónan, Nettó and Hagkaup; shopping centres (Spöngin placed by hand in `MANUAL_MALLS`); second-hand shops and Kolaportið; big stores
  (Costco, IKEA, Elko, BYKO, Húsasmiðjan, Bauhaus, JYSK); sights (`SIGHTS`, about 80 hand-picked: Hallgrímskirkja,
  Gullfoss, Geysir, Seljalandsfoss, Bláa lónið, Kirkjufell, the airports...); public swimming pools (`POOLS`, by name);
  named parks, gardens, nature areas and big woods (green labels, sized by area; outside the capital region
  only parks in towns); and bus places: Strætó's transfer hubs
  (`HUBS`, from straeto.is), Hlemmur and Lækjartorg, the BSÍ terminal, and other big stops with lettered
  platforms. Hlemmur is placed by hand (`MANUAL_STOPS`) while its stops are out of OSM.
- `addresses.py`: every street address (street + house number) for the Home / Work settings, as
  `_assets/addresses.js` (~380 KB, ~155 KB compressed). The page loads it only when Home / Work is used and
  looks addresses up in the browser, so typed addresses are not sent anywhere. Keep it next to the HTML.
- `streets_geo.py`: road lines of every named street (~450 KB, ~180 KB compressed) as `_assets/streets.js`,
  loaded in the background so "Nearest street" measures to the road itself rather than to a street's middle
  point (which picked short cross streets on long roads like Brautarholt).
- `aliases.json`: other names people use for a place (Holtin → Holt, Grandi → Örfirisey, Downtown → Miðbær).
  Search finds the place by them and its details list them as "Also called". Mark English names `"en"`
  (not voiced) and grammatical forms `"case"` (úti á Granda: search only, not listed or voiced).
- Pronunciation rules live in `make_audio.py` (`load_voice()`, `post()`, `spoken()`). They were tuned with an
  automatic listening check (Whisper large-v3-turbo transcribing every clip, scored by sound). The main lesson:
  feed the voice espeak's phonemes as espeak writes them; "correcting" them to IPA it never trained on drops sounds.
- `make_audio.py clips` keeps one small mp3 per name in `_assets/audio/c/` (about 5,000 files, ~20 MB). It voices
  only names without a clip and deletes clips of names that left the map; `--redo` voices everything again
  under new ids (an id is never reused, so browsers may cache clips for good).
  Postal codes are read as numbers (`postal_words()`: 262 = "tvö hundruð sextíu og tveir").
- `roads.json` (from `streets_geo.py`): the big roads, so the search finds Suðurlandsvegur or "Route 35".
- `land.py`: a rough land outline (grown ~200 m, simplified) embedded in the page, so a tap on the open sea
  says "Ocean". `build_data.py` adds it; `python land.py data/coast.json data/mapdata.json` updates an
  existing map data file (run `islands.py` again after it).
- `islands.py`: named islands from OSM (`place=island / islet / archipelago`): every named one in the capital
  region and Vestmannaeyjar (Viðey, Engey, Heimaey, Surtsey, Þrídrangar...), elsewhere those of 0.1 km² or more
  (Brokey, Hjörsey, Flatey, Árnes in Þjórsá), about 120 in all. Each gets its municipality (the boundary that holds
  it, else the nearest within 10 km; the Flatey group goes to Reykhólahreppur) and is added to the land outline,
  so a tap on it never says "Ocean". The page labels them, finds them in search, and shows an Island row.

The page embeds only `_assets/audio/index.json` (name → clip id). The clips stay in `_assets/audio/c/`, which
must sit next to the HTML file, locally and on the web.

UI-only changes (labels, layout): edit `template.html`, then run only the `inject.py` line.

The version in Settings (`stamp.py`) is the build time to the minute (UTC = Iceland time) and the git commit.
`inject.py` stamps the page; `make_site.py` stamps it again, so the live site shows when Cloudflare built it.

Links: `#q=Holtin` runs a search; `#show=kind|name|town` opens one place (what the share buttons copy),
for example `#show=postal|105`, `#show=nbh|Holt|Reykjavík`, `#show=poi|Bónus Skeifan|Reykjavík`,
`#show=town|Selfoss|Árborg`, `#show=zones|Suðurland`.

## Pronunciation audio

`make_audio.py` needs a separate Python 3.10–3.13 environment with `pip install piper-tts`, plus ffmpeg
(here: `uv venv --python 3.13 .venv-tts && VIRTUAL_ENV=.venv-tts uv pip install piper-tts`).
Voice files (`.onnx` + `.onnx.json`) come from https://huggingface.co/rhasspy/piper-voices/tree/main/is/is_IS
(Ugla = the higher female voice; also Salka, Búi, Steinn). `python make_audio.py samples voices/ out/` writes
one comparison clip per voice. The script works around a macOS espeak-ng path bug and adjusts a few phonemes
the voice handles badly (hl, hj, ll); see the docstring in `load_voice()`.

# Packaging for the web (Cloudflare Pages)

From the project root:

```bash
python build/make_site.py
```

Writes `site/` (index.html, manifest, icons, `_headers`, `_assets/audio/c/` clips, `_assets/addresses.<hash>.js`,
`_assets/streets.<hash>.js`) and `site.zip`. The two scripts get their content's hash in the name (the page in
`site/` is pointed at them), so `_headers` can let browsers cache everything under `_assets/` for a year;
index.html itself is revalidated on every visit. Cloudflare Workers allows 20,000 files per deploy on the free plan.
Security: `_headers` carries a Content-Security-Policy that lets only the page's own inline scripts run
(pinned by SHA-256, recomputed by `make_site.py` on every build), plus Leaflet's own folder on cdnjs, which the
page pins with an SRI `integrity` hash. The page makes no network calls from code (`connect-src 'none'`). Upgrading Leaflet means updating both URLs and both hashes in `template.html`.
Permissions-Policy allows location and the microphone (🎤 search) for this site only.
Anything Cloudflare injects into the page (Web Analytics beacon, Rocket Loader, email obfuscation) would be
blocked by the policy: keep those off, or add their sources to `csp_for()`.

Upload `site.zip` in Cloudflare: Workers & Pages > your project > Create a new deployment > Production.

Or let Cloudflare build from this GitHub repository on every push to `main` (Workers with static assets):
create a Worker by importing the repository, name it `reykjavik-map` (must match `name` in
`wrangler.jsonc`), build command `python3 build/make_site.py`, deploy command `npx wrangler deploy`.
`wrangler.jsonc` serves `site/` as static files and Cloudflare applies `site/_headers`. Cloudflare's build
machines have no Pillow, so the icons come from `build/icons/`. Test locally with `npx wrangler dev`.
