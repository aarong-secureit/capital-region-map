"""Generate Icelandic pronunciation clips for every place name on the map, using Piper TTS.

Needs: pip install piper-tts  (Python 3.10-3.13), ffmpeg on PATH, and an Icelandic Piper voice:
  https://huggingface.co/rhasspy/piper-voices/tree/main/is/is_IS   (salka, ugla, bui, steinn; medium)
Voices are trained on the Talrómur corpus (CC BY 4.0).

Usage:
  python make_audio.py samples VOICE_DIR OUT_DIR              # one comparison clip per voice
  python make_audio.py packs VOICE_ONNX MAPDATA_JSON OUT_DIR [POIS_JSON] [ALIASES_JSON]  # everything
  python make_audio.py add VOICE_ONNX POIS_JSON OUT_DIR [ALIASES_JSON]   # only names not voiced yet, into extra packs
  python make_audio.py all VOICE_ONNX MAPDATA_JSON OUT_JSON    # (older) places only, as base64 json

"packs" writes OUT_DIR/pack-NN.mp3 (about 100 names each, separated by short silences) and
OUT_DIR/index.json = {"files": [...], "clips": {name: [file, start_s, dur_s]}}. The map embeds the
index and plays just that slice of the pack. Packing keeps the file count far below Cloudflare's
1,000-file drag-and-drop limit, and plain <audio> playback also works when the page is opened from disk.
"""
import array, base64, io, json, os, re, subprocess, sys, wave
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
POSTAL_WORDS = {
    "101": "hundrað og einn", "102": "hundrað og tveir", "103": "hundrað og þrír", "104": "hundrað og fjórir",
    "105": "hundrað og fimm", "107": "hundrað og sjö", "108": "hundrað og átta", "109": "hundrað og níu",
    "110": "hundrað og tíu", "111": "hundrað og ellefu", "112": "hundrað og tólf", "113": "hundrað og þrettán",
    "116": "hundrað og sextán", "161": "hundrað sextíu og einn", "162": "hundrað sextíu og tveir",
    "170": "hundrað og sjötíu", "200": "tvö hundruð", "201": "tvö hundruð og einn", "203": "tvö hundruð og þrír",
    "206": "tvö hundruð og sex", "210": "tvö hundruð og tíu", "220": "tvö hundruð og tuttugu",
    "221": "tvö hundruð tuttugu og einn", "225": "tvö hundruð tuttugu og fimm", "270": "tvö hundruð og sjötíu",
    "271": "tvö hundruð sjötíu og einn", "276": "tvö hundruð sjötíu og sex",
}


# names an Icelandic voice would otherwise spell out or misread: say them the way Icelanders do
SAY_AS = {"IKEA": "Íkea", "Costco": "Kostkó", "BYKO": "Býkó", "JYSK": "Jysk", "Bauhaus": "Báhás", "BSÍ": "bé ess í",
          "abc": "a bé sé", "KR": "ká err", "MR": "emm err", "FB": "eff bé", "FMOS": "eff emm o ess",
          "RÚV": "Ríkisútvarpið, Rúv"}
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
    t = t.replace("Kjalarn.-dreifb.", "Kjalarnes dreifbýli")
    t = re.sub(r"\b(\d{1,2})\.\s*(?=\w)", lambda m: ORDINAL.get(int(m.group(1)), m.group(1)) + " ", t)   # 3.Gata
    t = re.sub(r"\b(II|III|IV|VI|VII)\b-?", lambda m: ROMAN[m.group(1)] + " ", t)                      # Eyjar II
    t = t.replace("v/", "við ").replace("/", " ")                                                    # v/Rauðavatn
    t = t.replace("Elliðakotsl", "Elliðakotsland")
    t = re.sub(r"\s+kollf\. v\.hl\.$|\s+Bl \d+$", "", t)                                            # unreadable abbreviations
    t = re.sub(r"\(([^)]*)\)", r" \1 ", t)          # "Kjalarnes (dreifbýli)" -> "Kjalarnes dreifbýli"
    t = re.sub(r"\s+-\s+|-(?=[A-ZÁÐÉÍÓÚÝÞÆÖ])", " ", t)  # "Mjódd - norður", "Efra-Breiðholt"
    t = re.sub(r"\bN$", "norður", t)
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


def all_names(voice_onnx, mapdata, out_json):
    out_json = Path(out_json).resolve()
    d = json.load(open(Path(mapdata).resolve(), encoding="utf-8"))
    names = set()
    for k in ("munis", "districts", "hverfi", "nbh", "small"):
        names.update(f["properties"]["name"] for f in d[k]["features"])
    names.update(p["name"] for p in d["points"])
    voice = load_voice(voice_onnx)
    clips, total = {}, 0
    for n in sorted(names):
        b = to_mp3(wav_bytes(voice, spoken(n)))
        clips[n] = base64.b64encode(b).decode()
        total += len(b)
    for f in d["postal"]["features"]:
        c, town = f["properties"]["code"], f["properties"]["town"]
        if c in POSTAL_WORDS:
            b = to_mp3(wav_bytes(voice, f"{POSTAL_WORDS[c]}, {town}"))
            clips["postal:" + c] = base64.b64encode(b).decode()
            total += len(b)
    json.dump(clips, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{len(clips)} clips, {total/1024:.0f} KB mp3, {Path(out_json).stat().st_size/1024:.0f} KB as base64 json")


RATE = 22050
GAP = 0.3          # seconds of silence before every clip (and at the end of a pack)
PER_PACK = 100


def trim(pcm, thr=400, win=0.01, pad_start=0.03, pad_end=0.08):
    """Cut silence off both ends. The voice sometimes waits up to ~0.6 s before speaking (it varies run to
    run), which feels like the play button did nothing; the packs add their own fixed gap between clips."""
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


def packs(voice_onnx, mapdata, out_dir, pois_json=None, aliases_json=None):
    out = Path(out_dir).resolve()
    d = json.load(open(Path(mapdata).resolve(), encoding="utf-8"))
    texts = {}                                   # key -> what to say
    for k in ("munis", "districts", "hverfi", "nbh", "small"):
        for f in d[k]["features"]:
            texts[f["properties"]["name"]] = spoken(f["properties"]["name"])
    for p in d["points"]:
        texts[p["name"]] = spoken(p["name"])
    for s in d["streets"]:
        texts.setdefault(s[0], spoken(s[0]))     # a street sharing a place's name reuses its clip
    for name in extra_names(pois_json) + extra_names(aliases_json):
        texts.setdefault(name, spoken(name))
    for f in d["postal"]["features"]:
        c, town = f["properties"]["code"], f["properties"]["town"]
        if c in POSTAL_WORDS:
            texts["postal:" + c] = f"{POSTAL_WORDS[c]}, {town}"
    voice = load_voice(voice_onnx)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("pack-*.mp3"):
        old.unlink()
    keys = sorted(texts, key=lambda k: (k.startswith("postal:"), k.lower()))
    gap = b"\x00\x00" * int(GAP * RATE)
    index = {"files": [], "clips": {}}
    total = 0
    for n, i in enumerate(range(0, len(keys), PER_PACK)):
        buf, t = bytearray(), 0.0
        for k in keys[i:i + PER_PACK]:
            pcm = pcm16(voice, texts[k])
            buf += gap; t += GAP
            dur = len(pcm) / 2 / RATE
            index["clips"][k] = [n, round(t, 3), round(dur, 3)]
            buf += pcm; t += dur
        buf += gap
        name = f"pack-{n:02d}.mp3"
        # constant bitrate keeps seeking accurate; -write_xing keeps the gapless header so offsets line up
        p = subprocess.run(["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "pipe:0",
                            "-codec:a", "libmp3lame", "-b:a", "32k", str(out / name)], input=bytes(buf), check=True)
        index["files"].append(name)
        total += (out / name).stat().st_size
        print(f"  {name}: {len(keys[i:i+PER_PACK])} clips, {(out / name).stat().st_size/1024:.0f} KB", flush=True)
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(index['clips'])} clips in {len(index['files'])} packs, {total/1024/1024:.1f} MB; "
          f"index {(out / 'index.json').stat().st_size/1024:.0f} KB")


def add(voice_onnx, pois_json, out_dir, aliases_json=None):
    """Voice the names in POIS_JSON that index.json lacks, into new packs after the existing ones.
    Existing packs and offsets are left alone, so only the new files need uploading."""
    out = Path(out_dir).resolve()
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    texts = {}
    for name in extra_names(pois_json) + extra_names(aliases_json):
        if name not in index["clips"]:
            texts[name] = spoken(name)
    if not texts:
        print("nothing new to voice"); return
    voice = load_voice(voice_onnx)
    keys = sorted(texts, key=str.lower)
    gap = b"\x00\x00" * int(GAP * RATE)
    for i in range(0, len(keys), PER_PACK):
        n = len(index["files"])
        buf, t = bytearray(), 0.0
        for k in keys[i:i + PER_PACK]:
            pcm = pcm16(voice, texts[k])
            buf += gap; t += GAP
            dur = len(pcm) / 2 / RATE
            index["clips"][k] = [n, round(t, 3), round(dur, 3)]
            buf += pcm; t += dur
        buf += gap
        name = f"pack-{n:02d}.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "pipe:0",
                        "-codec:a", "libmp3lame", "-b:a", "32k", str(out / name)], input=bytes(buf), check=True)
        index["files"].append(name)
        print(f"  {name}: {len(keys[i:i+PER_PACK])} new clips, {(out / name).stat().st_size/1024:.0f} KB", flush=True)
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(index['clips'])} clips in {len(index['files'])} packs")


if __name__ == "__main__":
    if sys.argv[1] == "samples":
        samples(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "packs":
        packs(sys.argv[2], sys.argv[3], sys.argv[4], *sys.argv[5:7])
    elif sys.argv[1] == "add":
        add(sys.argv[2], sys.argv[3], sys.argv[4], *sys.argv[5:6])
    else:
        all_names(sys.argv[2], sys.argv[3], sys.argv[4])
