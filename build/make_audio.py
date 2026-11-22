"""Generate Icelandic pronunciation clips for every place name on the map, using Piper TTS.

Needs: pip install piper-tts  (Python 3.10-3.13), ffmpeg on PATH, and an Icelandic Piper voice:
  https://huggingface.co/rhasspy/piper-voices/tree/main/is/is_IS   (salka, ugla, bui, steinn; medium)
Voices are trained on the Talrómur corpus (CC BY 4.0).

Usage:
  python make_audio.py samples VOICE_DIR OUT_DIR              # one comparison clip per voice
  python make_audio.py clips VOICE_ONNX MAPDATA_JSON OUT_DIR [POIS_JSON] [ALIASES_JSON] [ROADS_JSON]

"clips" keeps one small mp3 per name in OUT_DIR/c/<id>.mp3 and OUT_DIR/index.json =
{"next": n, "clips": {name: id}} (ids are short base-36 numbers that never change, so a clip stays cached).
It voices only the names that have no clip yet and deletes clips of names no longer on the map; add
--redo to voice everything again (new ids). The map embeds the index and plays c/<id>.mp3.
"""
import array, io, json, os, re, subprocess, sys, wave
from pathlib import Path
import piper
from piper import PiperVoice, SynthesisConfig

SLOW = SynthesisConfig(length_scale=1.15)  # a little slower than normal, for learners
PIPER_PKG = Path(piper.__file__).resolve().parent


def load_voice(onnx):
    """Load a Piper voice, working around problems seen on macOS and in espeak's Icelandic output.

    Rule of thumb: the voice was trained on espeak's phonemes exactly as espeak writes them, so feed it
    the same symbols. Changing them to "more correct" IPA it never saw makes it drop sounds.
    - espeak-ng silently truncates data paths longer than ~160 characters (then falls back to a
      build-machine path and exits), so run from the package folder with a short relative path.
    - espeak writes clusters like br/gr/kr with a schwa ("Klambra" -> ɡlˈambəra). Keep it: the voice
      learned "bər" as a plain "br". (Removing it, as an earlier version did, made the voice swallow
      the r: "Klam-batún".)
    - espeak marks voiceless sounds with "#" (hl, hr, hn, lt), which the voice has no symbol for and was
      trained without. hr/hn keep their h, but "hl" comes out as l#, i.e. a plain l ("Líðar" for Hlíðar).
      Before a vowel, say it as h + l: a breath the voice knows from hr/hn and preaspiration, close to
      the real voiceless l. (Mapping it to ɬ, as an earlier version did, used a symbol the voice never
      learned, and the sound disappeared.)
    - espeak sometimes splits ç (hj) into c + a combining cedilla the voice does not know; join it back.
    - hj and ll: see post() below."""
    onnx = str(Path(onnx).resolve())
    os.chdir(PIPER_PKG)
    v = PiperVoice.load(onnx, espeak_data_dir="espeak-ng-data")
    orig = v.phonemize
    vowels = set("aeiouyæøœɔɛɪʏʊɐəɑ")

    def fix(sentence):
        out = []
        for i, p in enumerate(sentence):
            if p == "̧" and out and out[-1] == "c":   # "ç" (hj, as in Engihjalli) split into c + cedilla
                out[-1] = "ç"
                continue
            if p == "#":
                nxt = next((q for q in sentence[i + 1:] if q not in "ˈˌ"), "")
                if out and out[-1] == "l" and nxt[:1] in vowels and (len(out) < 2 or out[-2] != "h"):
                    out.insert(len(out) - 1, "h")         # hl before a vowel: h + l
                continue                                  # otherwise drop it, as in training
            out.append(p)
        return post(out)

    def post(o):
        """Two sounds tuned with a listening check (Whisper, ~30 names per sound, several spellings each):
        - hj: espeak's ç came out faint ("Falli" for Hjalli); h + j is heard right (score 0.97 vs 0.86).
        - ll (espeak d + l): t + l gives the puff of air of Icelandic ll ([tl̥], "Fjall"), except before
          s, t, d, n, where ll is a plain l (Mosfellsbær, Fellsmúli, Gullsmári)."""
        r, i = [], 0
        while i < len(o):
            p = o[i]
            if p == "ç":
                r += ["h", "j"]; i += 1; continue
            if p == "d" and i + 1 < len(o) and o[i + 1] == "l":
                nxt = next((q for q in o[i + 2:] if q not in "ˈˌ"), "")
                r += ["l"] if nxt in ("s", "t", "d", "n") else ["t", "l"]
                i += 2; continue
            r.append(p); i += 1
        return r

    v.phonemize = lambda text: [fix(s) for s in orig(text)]
    return v

# How Icelanders say the postal codes ("hundrað og fimm" = 105)
ONES = ["", "einn", "tveir", "þrír", "fjórir", "fimm", "sex", "sjö", "átta", "níu", "tíu", "ellefu", "tólf", "þrettán",
        "fjórtán", "fimmtán", "sextán", "sautján", "átján", "nítján"]
TENS = {2: "tuttugu", 3: "þrjátíu", 4: "fjörutíu", 5: "fimmtíu", 6: "sextíu", 7: "sjötíu", 8: "áttatíu", 9: "níutíu"}
HUNDREDS = ["", "hundrað", "tvö hundruð", "þrjú hundruð", "fjögur hundruð", "fimm hundruð", "sex hundruð",
            "sjö hundruð", "átta hundruð", "níu hundruð"]


def postal_words(code):
    """A postal code as Icelanders say it: 101 "hundrað og einn", 262 "tvö hundruð sextíu og tveir"."""
    n = int(code)
    h, r = divmod(n, 100)
    if r == 0:
        return HUNDREDS[h]
    if r < 20 or r % 10 == 0:
        return f"{HUNDREDS[h]} og {ONES[r] if r < 20 else TENS[r // 10]}"
    return f"{HUNDREDS[h]} {TENS[r // 10]} og {ONES[r % 10]}"




# names an Icelandic voice would otherwise spell out or misread: say them the way Icelanders do
SAY_AS = {"IKEA": "Íkea", "Costco": "Kostkó", "BYKO": "Býkó", "JYSK": "Jysk", "Bauhaus": "Báhás", "BSÍ": "bé ess í",
          "abc": "a bé sé", "KR": "ká err", "MR": "emm err", "FB": "eff bé", "FMOS": "eff emm o ess",
          "RÚV": "Ríkisútvarpið, Rúv", "N1": "enn einn", "FSU": "eff ess ú"}
# names the Icelandic voice should not read: English names, and stray abbreviations in the street data
NO_CLIP = {"Lava Centre", "DRE"}
# "3.Gata" is "þriðja gata", not "three point street"; farm numbers like "Eyjar II" are read as "Eyjar tvö"
ORDINAL = {1: "fyrsta", 2: "önnur", 3: "þriðja", 4: "fjórða", 5: "fimmta", 6: "sjötta", 7: "sjöunda", 8: "áttunda",
           9: "níunda", 10: "tíunda", 11: "ellefta", 12: "tólfta", 13: "þrettánda", 14: "fjórtánda", 15: "fimmtánda",
           16: "sextánda", 17: "sautjánda", 18: "átjánda", 19: "nítjánda", 20: "tuttugasta"}
ROMAN = {"II": "tvö", "III": "þrjú", "IV": "fjögur", "VI": "sex", "VII": "sjö"}


def spoken(name):
    """Turn a map label into something a speech engine reads naturally."""
    t = name
    for word, say in SAY_AS.items():                 # also inside longer names ("BYKO Skemmuvegur")
        t = re.sub(rf"\b{word}\b", say, t)
    t = re.sub(r"\b(\d{1,2})\.\s*(?=\w)", lambda m: ORDINAL.get(int(m.group(1)), m.group(1)) + " ", t)   # 3.Gata
    t = re.sub(r"\b(II|III|IV|VI|VII)\b-?", lambda m: ROMAN[m.group(1)] + " ", t)                      # Eyjar II
    t = t.replace("v/", "við ").replace("/", " ")                                                    # v/Rauðavatn
    t = t.replace("Elliðakotsl", "Elliðakotsland")
    t = re.sub(r"\s+kollf\. v\.hl\.$|\s+Bl \d+$", "", t)                                            # unreadable abbreviations
    t = re.sub(r"\(([^)]*)\)", r" \1 ", t)          # "Kjalarnes (dreifbýli)" -> "Kjalarnes dreifbýli"
    t = re.sub(r"\s+-\s+|-(?=[A-ZÁÐÉÍÓÚÝÞÆÖ])", " ", t)  # "Mjódd - norður", "Efra-Breiðholt"
    t = re.sub(r"\bN$", "norður", t)
    # nn after a long vowel is a stopped "tn" (einn, steinn: espeak gets these). At the end of a word after
    # á/é/í/ó/ú/ý/æ espeak drops it ("Grænn" -> "græn"); spelled "dn" it writes the stop, as it does for einn.
    t = re.sub(r"([áéíóúýæÁÉÍÓÚÝÆ])nn\b", r"\1dn", t)
    return re.sub(r"\s+", " ", t).strip()


def wav_bytes(voice, text):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        voice.synthesize_wav(text, w, syn_config=SLOW)
    return buf.getvalue()


def to_mp3(wav, kbps=32):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", "22050",
                        "-codec:a", "libmp3lame", "-b:a", f"{kbps}k", "-f", "mp3", "pipe:1"],
                       input=wav, capture_output=True, check=True)
    return p.stdout


def samples(voice_dir, out_dir):
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    text = "Árbær. Hlíðar. Holtin. Kópavogur. Hafnarfjörður. Grafarvogur. Hundrað og fimm."
    for onnx in sorted(Path(voice_dir).resolve().glob("is_IS-*-medium.onnx")):
        name = onnx.name.split("-")[1]
        mp3 = to_mp3(wav_bytes(load_voice(onnx), text), kbps=64)
        (out / f"voice-sample-{name}.mp3").write_bytes(mp3)
        print("wrote", out / f"voice-sample-{name}.mp3")


RATE = 22050


def trim(pcm, thr=400, win=0.01, pad_start=0.03, pad_end=0.08):
    """Cut silence off both ends. The voice sometimes waits up to ~0.6 s before speaking (it varies run to
    run), which feels like the play button did nothing."""
    a = array.array("h", pcm)
    n = max(1, int(RATE * win))
    loud = [i for i in range(0, len(a), n) if max(abs(x) for x in a[i:i + n]) > thr]
    if not loud:
        return pcm
    start = max(0, loud[0] - int(RATE * pad_start))
    end = min(len(a), loud[-1] + n + int(RATE * pad_end))
    return a[start:end].tobytes()


def pcm16(voice, text):
    """Synthesize text, return raw 16-bit mono PCM at RATE, with the silence at both ends trimmed."""
    with wave.open(io.BytesIO(wav_bytes(voice, text))) as w:
        assert w.getframerate() == RATE and w.getsampwidth() == 2 and w.getnchannels() == 1
        return trim(w.readframes(w.getnframes()))


def extra_names(path):
    """Names to voice from pois.json (a list of places) or aliases.json (skips English names and grammatical forms)."""
    if not path:
        return []
    d = json.load(open(Path(path).resolve(), encoding="utf-8"))
    if isinstance(d, list):
        return [p["name"] for p in d]
    return [k for k, v in d.items() if not k.startswith("_") and not {"en", "case"} & set(v[3:])]


def b36(n):
    d = "0123456789abcdefghijklmnopqrstuvwxyz"
    o = ""
    while True:
        n, r = divmod(n, 36)
        o = d[r] + o
        if not n:
            return o


def encode_clip(pcm, path):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "pipe:0",
                    "-codec:a", "libmp3lame", "-b:a", "32k", str(path)], input=bytes(pcm), check=True)


def name_texts(mapdata, pois_json=None, aliases_json=None, roads_json=None, streets_js=None):
    """Every name the map can play: key -> what the voice says. streets_js (_assets/streets.js) adds the
    roads "Nearest street" can name that have no addresses (Þormóðsdalsvegur)."""
    d = json.load(open(Path(mapdata).resolve(), encoding="utf-8"))
    texts = {}
    for k in ("zones", "munis", "districts", "hverfi", "nbh", "small", "islands"):
        for f in d.get(k, {"features": []})["features"]:
            texts[f["properties"]["name"]] = spoken(f["properties"]["name"])
    for p in d["points"] + d.get("towns", []):
        texts.setdefault(p["name"], spoken(p["name"]))
    for s in d["streets"]:
        texts.setdefault(s[0], spoken(s[0]))     # a street sharing a place's name reuses its clip
    for name in extra_names(pois_json) + extra_names(aliases_json):
        texts.setdefault(name, spoken(name))
    if roads_json:
        for r in json.load(open(Path(roads_json).resolve(), encoding="utf-8")):
            if not r["name"].startswith("Route "):
                texts.setdefault(r["name"], spoken(r["name"]))
    if streets_js and Path(streets_js).exists():
        js = Path(streets_js).read_text(encoding="utf-8")
        for name in json.loads(js[js.index("=") + 1:].rstrip().rstrip(";").replace("<\\/", "</")):
            if not name.startswith("Route ") and re.search(r"[^\W\d_]{2}", name):
                texts.setdefault(name, spoken(name))
    for f in d["postal"]["features"]:
        c, town = f["properties"]["code"], f["properties"]["town"]
        if c.isdigit():
            texts["postal:" + c] = f"{postal_words(c)}, {town}"
    for k in NO_CLIP:
        texts.pop(k, None)
    return texts


def clips(voice_onnx, mapdata, out_dir, pois_json=None, aliases_json=None, roads_json=None, redo=False):
    out = Path(out_dir).resolve()
    cdir = out / "c"
    cdir.mkdir(parents=True, exist_ok=True)
    ip = out / "index.json"
    old = json.loads(ip.read_text(encoding="utf-8")) if ip.exists() else None
    # --redo voices every name again under new ids: an id is never reused for different audio, so the site
    # can let browsers cache clips for good
    index = old if old and not redo else {"next": old["next"] if old else 0, "clips": {}}
    texts = name_texts(mapdata, pois_json, aliases_json, roads_json, streets_js=out.parent / "streets.js")
    gone = [k for k in index["clips"] if k not in texts]
    for k in gone:                                           # names no longer on the map
        (cdir / f"{index['clips'].pop(k)}.mp3").unlink(missing_ok=True)
    todo = sorted((k for k in texts if k not in index["clips"]), key=lambda k: (k.startswith("postal:"), k.lower()))
    print(f"{len(texts)} names: {len(texts) - len(todo)} already voiced, {len(todo)} to voice, {len(gone)} removed", flush=True)
    voice = load_voice(voice_onnx) if todo else None
    for n, k in enumerate(todo, 1):
        cid = b36(index["next"]); index["next"] += 1
        encode_clip(pcm16(voice, texts[k]), cdir / f"{cid}.mp3")
        index["clips"][k] = cid
        if n % 200 == 0:
            print(f"  {n}/{len(todo)}", flush=True)
            ip.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    used = set(index["clips"].values())
    for f in cdir.glob("*.mp3"):                             # leftovers of an interrupted run
        if f.stem not in used:
            f.unlink()
    ip.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = sum(f.stat().st_size for f in cdir.glob("*.mp3"))
    print(f"{len(index['clips'])} clips, {size / 1024 / 1024:.1f} MB; index {ip.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--redo"]
    if args[0] == "samples":
        samples(args[1], args[2])
    elif args[0] == "clips":
        clips(args[1], args[2], args[3], *args[4:7], redo="--redo" in sys.argv)
    else:
        sys.exit(__doc__)
