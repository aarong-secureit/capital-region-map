# Rebuilding capital-region-map.html

Needs Python 3 with: `pip install osmium shapely numpy scipy pillow`

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
python landmarks.py data/mapdata.json landmarks.json
python pois.py osm/iceland-latest.osm.pbf data/mapdata.json pois.json
python addresses.py osm/iceland-latest.osm.pbf data/mapdata.json ../_assets/addresses.js
python streets_geo.py osm/iceland-latest.osm.pbf data/mapdata.json ../_assets/streets.js
python make_audio.py packs voices/is_IS-ugla-medium.onnx data/mapdata.json ../_assets/audio pois.json aliases.json
python inject.py data/mapdata.json template.html ../capital-region-map.html ../_assets/audio/index.json landmarks.json pois.json aliases.json
```

- `landmarks.py`: the well-known spot each big area shares to Google Maps (town hall, main church,
  shopping centre). Edit the `LANDMARKS` list; it checks each point lies inside its area.
- `pois.py`: every Bónus, Krónan, Nettó and Hagkaup; shopping centres (Spöngin placed by hand in `MANUAL_MALLS`); second-hand shops and Kolaportið; big stores
  (Costco, IKEA, Elko, BYKO, Húsasmiðjan, Bauhaus, JYSK); Perlan; public swimming pools (`POOLS`, by name);
  named parks, gardens, nature areas and big woods (green labels, sized by area); and bus places: Strætó's transfer hubs
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
- `make_audio.py packs` voices everything from scratch (about a minute on a recent Mac). To add a few new names
  without touching the existing packs, use `make_audio.py add VOICE pois.json ../_assets/audio aliases.json` instead.

The page embeds only `_assets/audio/index.json` (where each name sits inside the packs). The sound itself
stays in `_assets/audio/pack-NN.mp3`, which must sit next to the HTML file, locally and on the web.

UI-only changes (labels, layout): edit `template.html`, then run only the `inject.py` line.

Links: `#q=Holtin` runs a search; `#show=kind|name|town` opens one place (what the share buttons copy),
for example `#show=postal|105`, `#show=nbh|Holt|Reykjavík`, `#show=poi|Bónus Skeifan|Reykjavík`.

## Pronunciation audio

`make_audio.py` needs a separate Python 3.10–3.13 environment with `pip install piper-tts`, plus ffmpeg.
Voice files (`.onnx` + `.onnx.json`) come from https://huggingface.co/rhasspy/piper-voices/tree/main/is/is_IS
(Ugla = the higher female voice; also Salka, Búi, Steinn). `python make_audio.py samples voices/ out/` writes
one comparison clip per voice. The script works around a macOS espeak-ng path bug and adjusts a few phonemes
the voice handles badly (hl, hj, ll); see the docstring in `load_voice()`.

# Packaging for the web (Cloudflare Pages)

From the project root:

```bash
python build/make_site.py
```

Writes `site/` (index.html, manifest, icons, `_headers`, `_assets/audio/` packs, `_assets/addresses.js`, `_assets/streets.js`) and `site.zip` (35 files, ~11 MB).
Security: `_headers` carries a Content-Security-Policy that lets only the page's own inline scripts run
(pinned by SHA-256, recomputed by `make_site.py` on every build), plus Leaflet from cdnjs, which the page pins
with an SRI `integrity` hash. Upgrading Leaflet means updating both URLs and both hashes in `template.html`.
Anything Cloudflare injects into the page (Web Analytics beacon, Rocket Loader, email obfuscation) would be
blocked by the policy: keep those off, or add their sources to `csp_for()`.

Upload `site.zip` in Cloudflare: Workers & Pages > your project > Create a new deployment > Production.

Or let Cloudflare build from this GitHub repository on every push to `main`: create a Pages project with
Connect to Git, framework preset None, build command `python build/make_site.py`, build output directory
`site`. Cloudflare's build machines have no Pillow, so the icons come from `build/icons/`.
