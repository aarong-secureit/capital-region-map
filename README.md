# Capital Region Map

A map for people learning their way around Iceland's capital region and the west and south: where the
neighbourhoods, districts and towns are, how their names sound, and the everyday places around them, such as
grocery stores, swimming pools, the main bus stops and the well-known sights.

It isn't trying to be a full navigation map. It answers "where is Holtin?" or "which area is 108?", and hands
anything else off to Google Maps with one click.

Covers four of the Icelandic Met Office's weather forecast zones, the region names you hear in every forecast:
the capital region (Höfuðborgarsvæðið) in full detail, and Faxaflói (Reykjanes, Akranes, Borgarfjörður),
Breiðafjörður (Snæfellsnes, Dalir) and South Iceland (Suðurland, out to Vík and Vestmannaeyjar) with their
towns, villages, big roads and sights.

## What it does

- **Where is Holtin, Árbær, Selfoss or 105?** Regions, towns, neighbourhoods, districts and postal codes on one map.
- **Search the way you hear it.** Icelandic letters are optional, near-misses still match, and everyday names
  work too ("Holtin", "Grandi", "Downtown").
- **Hear the name.** Every place, street and point of interest has a 🔊 button with Icelandic pronunciation
  (generated offline with the Piper voice Ugla).
- **Share any place.** Big areas share their well-known landmark (town hall, main church, shopping centre)
  to Google Maps, or a link straight back to this map.
- **Points of interest**, each switchable: groceries (Bónus, Krónan, Nettó, Hagkaup), shopping, swimming
  pools, parks, the main bus stops and transfer hubs, and about 80 sights (Hallgrímskirkja, Gullfoss, Geysir,
  Seljalandsfoss, Bláa lónið, Kirkjufell, Reynisfjara...).
- **What's here:** the area, town, region, postal code and nearest street wherever you tap.
- **Home and Work pins** (up to three each), light/dark theme and your layer choices, all kept in your
  browser's local storage. Addresses are looked up in the page; nothing you type is sent anywhere.
- **Show my location**, on your device only.
- Works on phones, needs no API keys, and runs from a plain file.

## Run it

Open `capital-region-map.html` in a browser. Keep the `_assets/` folder next to it (pronunciation audio,
addresses and street lines).

For the web version (Cloudflare Pages, with security headers): `python build/make_site.py`, then upload
`site.zip`. See [build/README.md](build/README.md) for the full rebuild from OpenStreetMap and the
pronunciation pipeline.

## Data and credits

- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, available under the
  Open Database License (ODbL). Boundaries, places, streets, addresses and points of interest come from OSM.
- Reykjavík neighbourhood and district boundaries: Reykjavík City open data (lukrgatt.reykjavik.is).
- Bus transfer hubs: Strætó.
- Pronunciation: [Piper](https://github.com/rhasspy/piper) with the Icelandic voice Ugla
  ([rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/is/is_IS); see its model
  card for licence), phonemes from espeak-ng.
- Base maps: tiles from OpenStreetMap, OpenStreetMap Germany, OpenStreetMap France / HOT and Esri, credited
  on the map itself.
- [Leaflet](https://leafletjs.com) 1.9.4.

## Licence

The code (the page, its scripts and the build tools) is under the [MIT License](LICENSE). The map data
embedded in the page and in `_assets/` stays under its own terms above: OpenStreetMap data is ODbL, so
reuse of that data needs the OpenStreetMap credit and share-alike.
