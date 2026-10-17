"""La bibliothèque pro : des bruitages de studio, rangés et choisis par CLAP (un modèle qui écoute).

Les sons viennent des « GDC Game Audio Bundles » de Sonniss (libres de droits, usage commercial
et vidéos monétisées permis, sans crédit). La licence interdit deux choses : les redistribuer
(ils restent dans .cache/, jamais commités) et s'en servir pour entraîner une IA (on ne fait que
les écouter avec CLAP, sans rien entraîner).

    python -m manhwa.soundbank              prépare la bibliothèque et les ambiances (une fois, ≈ 5 min)
    python -m manhwa.soundbank --ambience   seulement les ambiances (places.py)
    python -m manhwa.soundbank --download   télécharge d'abord les sons Sonniss utiles (sonniss.py, ≈ 2 Go)

1. Chaque fichier de .cache/sonniss/raw/ (et de sfx/<catégorie>/) est coupé en prises : un fichier
   pro contient souvent plusieurs coups séparés par des silences. Chaque prise (0,1 à 4 s) est mise
   au même volume (on règle ensuite le volume selon la force du moment, pas selon le fichier).
2. CLAP écoute chaque prise et la range dans une catégorie de sfx.CATEGORIES (« a heavy punch
   hitting a body »…), aidé par le nom du fichier ; ce qui ne ressemble à rien d'utile est écarté.
3. Pour une case, la phrase de GPT (« heavy body slammed into a wooden wall ») est comparée à
   toutes les prises de la catégorie : la plus proche est prise.

Résultat dans .cache/soundbank/ : les prises (.wav), index.json et vectors.npy.
"""
import hashlib
import json
import os
import re
import subprocess
import threading
import wave

import numpy as np

from manhwa.config import ROOT

RATE = 44100
TARGET_RMS = 0.1  # ≈ -20 dBFS : toutes les prises au même volume
MIN_TAKE, MAX_TAKE = 0.1, 4.0
MAX_TAKES = 6  # par fichier : assez de variété sans noyer la catégorie sous un seul pack
MIN_SCORE = 0.25  # en dessous, CLAP n'est pas sûr (une Jeep rangée dans « contre un mur ») : la prise ne sert pas
MIN_TAKES = 3  # une catégorie avec moins de bonnes prises garde les sons d'avant (Kenney, fabriqués)
BANK_VERSION = 1
# ce que CLAP doit reconnaître (en anglais : il a appris comme ça)
PROMPTS = {
    "punch": "a punch hitting a body, fist fight sound effect",
    "impact": "a heavy dull impact thud",
    "slam": "a body slammed hard against a wall, violent crash",
    "fall": "a body falling to the ground",
    "slash": "a sword slash cutting through flesh",
    "blade_draw": "a sword being unsheathed, metallic scrape and ring",
    "metal": "swords clashing, metal clang",
    "energy": "an energy beam blast",
    "blood": "blood splatter, wet gore squelch",
    "heartbeat": "a heartbeat",
    "footsteps": "footsteps walking",
    "cloth": "cloth rustling, clothes movement",
    "door": "a door opening or closing",
    "glass": "glass shattering",
    "wood": "wood cracking or knocking",
    "bell": "a bell or gong ringing",
    "coins": "coins jingling",
    "paper": "paper rustling, book pages",
    "fire": "fire burning, crackling flames",
    "wind": "a gust of wind",
    "thunder": "thunder rumble",
    "explosion": "an explosion",
    "rumble": "a deep earth rumble, tremor",
    "magic": "a magical spell shimmer",
    "whoosh": "a fast whoosh swoosh",
}
# d'autres façons de dire la même chose : CLAP compare à la moyenne (plus juste qu'une seule phrase)
MORE_PROMPTS = {
    "slam": ["a heavy body falling hard on the ground", "a violent body impact, bodyfall"],
    "fall": ["a body falling on the floor, bodyfall", "someone collapsing to the ground"],
    "metal": ["a sword blade hitting another blade", "a metal clang", "chains rattling"],
    "cloth": ["clothes rustling", "a cape flapping", "fabric movement"],
    "wood": ["a wooden plank breaking", "knocking on wood", "wood creaking"],
    "bell": ["a temple gong", "a bell ringing"],
    "heartbeat": ["a heart beating, thump thump"],
    "wind": ["a strong wind gust", "wind howling"],
}
# ce qu'on écarte (une prise plus proche de ça que d'un bruitage utile)
REJECT = ["music", "people talking, speech", "a car or motorcycle engine", "a gunshot", "a robot voice",
          "room tone, quiet ambience", "electronic beeps, 8-bit game sounds"]
# le nom du fichier aide CLAP (« Punch_Heavy_03.wav » est sans doute un coup de poing)
NAME_HINTS = {
    "fall": r"body ?fall|bodyfall", "punch": r"punch|fist|kick", "slam": r"body ?slam|slam|crash into",
    "slash": r"slash|stab|slice|cut", "heartbeat": r"heart ?beat|heartbeat|stethoscope.*heart",
    "wind": r"wind[ ,_].*(gust|howl|rushing|breeze)|wind gust|gusts", "bell": r"\bbell\b|gong",
    "blade_draw": r"unsheath|sheath", "metal": r"sword|clang|clash|metal.*(hit|crash|impact)|chain|parry|shield",
    "cloth": r"cloth|fabric|clothing|umbrella", "wood": r"wood|plank|branch|tree limb|crate",
    "blood": r"blood|gore|splat|squelch|flesh|guts|bone", "whoosh": r"whoosh|swoosh|swish|woosh",
    "footsteps": r"footstep|step", "door": r"door", "fire": r"fire|flame", "thunder": r"thunder", "explosion": r"explo",
    "glass": r"glass|shatter", "paper": r"paper|book", "coins": r"coin", "impact": r"impact|hit|thud|thump",
}
_WORKER = {}
_LOCK = threading.Lock()


def raw_dir():
    return ROOT / ".cache" / "sonniss" / "raw"


def bank_dir():
    return ROOT / ".cache" / "soundbank"


# ---------- CLAP, dans .venv-tts ----------

def _worker():
    w = _WORKER.get("p")
    if w and w.poll() is None:
        return w
    from manhwa import chatterbox_tts, vision

    chatterbox_tts.close()
    vision.close()
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clap_worker.py")
    p = subprocess.Popen([str(chatterbox_tts.python()), "-u", worker], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8", cwd=str(ROOT))
    if not chatterbox_tts._answer(p).get("ready"):
        p.kill()
        raise RuntimeError("CLAP n'a pas démarré (environnement .venv-tts ?)")
    _WORKER["p"] = p
    return p


def close():
    p = _WORKER.pop("p", None)
    if p and p.poll() is None:
        try:
            p.stdin.close()
            p.wait(timeout=20)
        except Exception:
            p.kill()


def _ask(job):
    import tempfile

    from manhwa.chatterbox_tts import _answer

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "v.npy")
        with _LOCK:
            p = _worker()
            p.stdin.write(json.dumps({**job, "out": out}) + "\n")
            p.stdin.flush()
            answer = _answer(p)
        if "error" in answer:
            raise RuntimeError(answer["error"])
        return np.load(out)


def embed_texts(texts):
    return _ask({"text": list(texts)}) if texts else np.zeros((0, 512), np.float32)


def embed_audio(paths):
    return _ask({"audio": [str(p) for p in paths]})


# ---------- Les prises ----------

def _decode(path):
    import imageio_ffmpeg

    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "quiet", "-i", str(path), "-f", "s16le", "-ac", "1",
                          "-ar", str(RATE), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def takes(y, rate=RATE):
    """Les prises d'un fichier : morceaux séparés par au moins 0,25 s de quasi-silence."""
    if not len(y):
        return []
    hop = int(0.01 * rate)
    env = np.sqrt(np.convolve(y ** 2, np.ones(hop) / hop, mode="same"))[::hop]
    loud = env > max(1e-4, 0.03 * env.max())  # ≈ -30 dB sous le plus fort
    out, start, quiet = [], None, 0
    for i, on in enumerate(np.append(loud, False)):
        if on:
            start = i if start is None else start
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet >= 25 or i == len(loud):
                a, b = max(0, start - 2) * hop, min(len(y), (i - quiet + 6) * hop)
                if MIN_TAKE * rate <= b - a:
                    out.append(y[a:min(b, a + int(MAX_TAKE * rate))])
                start, quiet = None, 0
    return out


def _level(y):
    """Même volume pour toutes les prises (RMS de la partie forte), sans écrêter, avec un fondu de fin."""
    rms = np.sqrt(np.mean(y[np.abs(y) > 0.1 * np.abs(y).max()] ** 2)) if np.abs(y).max() > 0 else 1
    y = y * min(TARGET_RMS / max(rms, 1e-6), 0.98 / max(np.abs(y).max(), 1e-6))
    fade = min(len(y) // 4, int(0.05 * RATE))
    if fade:
        y[-fade:] *= np.linspace(1, 0, fade)
    return y


def _write(path, y):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())


def sources():
    from manhwa.sfx import user_dir

    out = []
    for folder in (raw_dir(), user_dir()):
        if folder.is_dir():
            out += sorted(p for p in folder.rglob("*") if p.suffix.lower() in (".wav", ".ogg", ".mp3", ".flac", ".aif", ".aiff"))
    return out


def _hint(name):
    low = name.lower()
    return next((cat for cat, rx in NAME_HINTS.items() if re.search(rx, low)), None)


def prepare(progress=None):
    """Coupe, met au même volume, écoute et range toute la bibliothèque. Renvoie le nombre de prises."""
    folder = bank_dir()
    (folder / "takes").mkdir(parents=True, exist_ok=True)
    rows = []
    files = sources()
    for i, src in enumerate(files):
        try:
            y = _decode(src)
        except Exception:
            continue
        for k, t in enumerate(takes(y)[:MAX_TAKES]):
            name = hashlib.sha1(f"{src.name}:{k}".encode()).hexdigest()[:16] + ".wav"
            _write(folder / "takes" / name, _level(t))
            user = src.is_relative_to(ROOT / "sfx")
            rows.append({"file": name, "src": src.name, "pack": src.parent.name, "dur": round(len(t) / RATE, 2),
                         "user_cat": src.parent.name if user else None})
        if progress:
            progress(i + 1, 2 * len(files))
    from manhwa.sfx import CATEGORIES

    vecs = embed_audio([folder / "takes" / r["file"] for r in rows])
    keep = _classify(rows, vecs)
    keep, vecs = _layer_slams(folder, keep, vecs)
    np.save(folder / "vectors.npy", vecs.astype(np.float16))
    (folder / "index.json").write_text(json.dumps({"version": BANK_VERSION, "takes": keep}, ensure_ascii=False),
                                       encoding="utf-8")
    close()
    if progress:
        progress(1, 1)
    _BANK.clear()
    return sum(1 for r in keep if r["cat"])


def _classify(rows, vecs):
    """Range chaque prise : la catégorie que CLAP entend le mieux, aidé par le nom du fichier."""
    from manhwa.sfx import CATEGORIES

    cats = [c for c in PROMPTS if c in CATEGORIES]
    texts = [PROMPTS[c] for c in cats]
    owner = list(range(len(cats)))
    for c, extra in MORE_PROMPTS.items():
        if c in cats:
            texts += extra
            owner += [cats.index(c)] * len(extra)
    text = embed_texts(texts + REJECT)
    sims_all = vecs @ text.T
    owner = np.array(owner)
    for r, s in zip(rows, sims_all):
        good = np.array([s[:len(owner)][owner == k].mean() for k in range(len(cats))])
        hint = _hint(r["src"])
        best = int(good.argmax())
        # le nom du fichier le dit (« bodyfall », « Cloth 61 ») et CLAP ne le contredit pas franchement : on le croit
        named = hint in cats and good[cats.index(hint)] >= max(0.08, good[best] - 0.12)
        if named:
            best = cats.index(hint)
            good[best] = max(good[best], MIN_SCORE)
        if r.get("user_cat") in CATEGORIES:  # rangé à la main dans sfx/<catégorie>/ : on respecte
            r["cat"] = r["user_cat"]
        elif named:
            r["cat"] = cats[best]
        elif good[best] < s[len(owner):].max() or good[best] < 0.15:
            r["cat"] = None  # musique, voix, moteur… : écarté
        else:
            r["cat"] = cats[best]
        r["score"] = round(float(good[best]), 3)
    return rows


def _layer_slams(folder, rows, vecs, n=6):
    """« Projeté contre un mur » manque dans les packs : un gros coup et une chute de corps, mêlés."""
    def best(cat, k):
        found = sorted((r for r in rows if r["cat"] == cat), key=lambda r: -r["score"])[:k]
        return [_decode(folder / "takes" / r["file"]) for r in found]

    hits, falls = best("punch", 4) + best("impact", 2), best("fall", 4)
    if not hits or not falls or sum(1 for r in rows if r["cat"] == "slam" and r["score"] >= MIN_SCORE) >= MIN_TAKES:
        return rows, vecs
    made = []
    for k in range(n):
        a, b = hits[k % len(hits)], falls[k % len(falls)]
        y = np.zeros(max(len(a), len(b) + int(0.04 * RATE)), np.float32)
        y[:len(a)] += a
        y[int(0.04 * RATE):int(0.04 * RATE) + len(b)] += 0.9 * b
        tt = np.arange(len(y)) / RATE
        y += 0.5 * np.sin(2 * np.pi * 50 * tt) * np.exp(-tt * 10) * TARGET_RMS * 4  # le grave du choc
        name = f"slam_layer_{k}.wav"
        _write(folder / "takes" / name, _level(y))
        made.append({"file": name, "src": name, "pack": "fabriqué", "dur": round(len(y) / RATE, 2), "user_cat": None,
                     "cat": "slam", "score": MIN_SCORE})
    new = embed_audio([folder / "takes" / r["file"] for r in made])
    return rows + made, np.concatenate([vecs, new])


def reclassify():
    """Range de nouveau les prises déjà écoutées (les phrases ou les règles ont changé), sans tout réécouter."""
    index = json.loads((bank_dir() / "index.json").read_text(encoding="utf-8"))
    vecs = np.load(bank_dir() / "vectors.npy").astype(np.float32)
    try:
        rows = _classify(index["takes"], vecs)
    finally:
        close()
    (bank_dir() / "index.json").write_text(json.dumps({"version": BANK_VERSION, "takes": rows}, ensure_ascii=False),
                                           encoding="utf-8")
    _BANK.clear()
    return sum(1 for r in rows if r["cat"])


_BANK = {}


def bank():
    """{"takes": [...], "vectors": np.array} (vide si la bibliothèque n'est pas prête)."""
    if not _BANK:
        try:
            index = json.loads((bank_dir() / "index.json").read_text(encoding="utf-8"))
            _BANK.update(takes=index["takes"], vectors=np.load(bank_dir() / "vectors.npy").astype(np.float32))
        except (OSError, ValueError, KeyError):
            _BANK.update(takes=[], vectors=np.zeros((0, 512), np.float32))
    return _BANK


def ready():
    return bool(bank()["takes"])


def _rows(category):
    rows = [i for i, r in enumerate(bank()["takes"]) if r["cat"] == category and (r["score"] >= MIN_SCORE or r["user_cat"])]
    return rows if len(rows) >= MIN_TAKES else []


def files(category):
    b = bank()
    return [bank_dir() / "takes" / b["takes"][i]["file"] for i in _rows(category)]


def best(category, query=None, seed=""):
    """La prise de la catégorie la plus proche de la phrase (vecteur CLAP) ; sans phrase, au hasard (stable)."""
    b = bank()
    rows = _rows(category)
    if not rows:
        return None
    if query is None:
        k = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % len(rows)
        return bank_dir() / "takes" / b["takes"][rows[k]]["file"]
    sims = b["vectors"][rows] @ np.asarray(query, np.float32)
    top = np.argsort(-sims)[:3]  # parmi les 3 plus proches : deux cases pareilles n'ont pas toujours le même son
    k = top[int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % len(top)] if seed else top[0]
    return bank_dir() / "takes" / b["takes"][rows[k]]["file"]




# ---------- Ambiances : le fond sonore d'un lieu (places.py) ----------

AMB_SECONDS = 25
# ambiances hors sujet pour un fond (machines, véhicules, ville moderne, un son précis plutôt qu'un fond)
AMB_SKIP = (r"chairlift|metro|barcelona|plane|iceberg|geese|apartment|children|house party|burger|beach|football|"
            r"compressor|machine|mothership|gas burner|dry ice|jet ski|toyota|bmw|volvo|alfa|b-25|brdm|tugboat|"
            r"screwdriver|nighthawk|hawk|falcon|drawer|nightstand|sink|encarta|loretta|tongues|orcs|audience|cannon|"
            r"exhibition|designed|splashes|dive in|inside boat|plastic|ice on stream|swoosh|whoosh|fear|horror|"
            r"open window|dry_ice|rally|cheering|eagle")
AMB_FADE = 1.5  # la fin se fond dans le début : la boucle ne s'entend pas


def ambience_raw_dir():
    return ROOT / ".cache" / "sonniss" / "ambience"


def _loop(y):
    """25 s d'ambiance qui bouclent sans couture, au même volume que les autres."""
    y = y[: int(AMB_SECONDS * RATE)].astype(np.float32)
    y = y - y.mean()
    f = int(AMB_FADE * RATE)
    if len(y) > 3 * f:
        ramp = np.linspace(0, 1, f, dtype=np.float32)
        head = y[:f].copy()
        y = y[f:]
        y[-f:] = y[-f:] * (1 - ramp) + head * ramp
    rms = float(np.sqrt(np.mean(y ** 2))) or 1.0
    return y * min(TARGET_RMS / rms, 0.95 / max(float(np.abs(y).max()), 1e-6))


def _synth_ambiences(folder, seconds=AMB_SECONDS + AMB_FADE, rate=RATE):
    """Deux fonds fabriqués : une pièce calme (souffle très doux) et un feu de cheminée."""
    from manhwa.sfx import _lowpass

    rng = np.random.default_rng(11)
    n = int(seconds * rate)
    room = _lowpass(rng.standard_normal(n), 0.008)
    room += 0.15 * _lowpass(rng.standard_normal(n), 0.05)
    _write(folder / "Quiet indoor room tone.wav", 0.5 * room / (np.abs(room).max() + 1e-9))
    rumble = _lowpass(rng.standard_normal(n), 0.004)
    crackle = np.zeros(n)
    for start in rng.integers(0, n - 2000, int(22 * seconds)):
        m = int(rng.integers(120, 700))
        crackle[start:start + m] += rng.uniform(0.2, 1.0) * rng.standard_normal(m) * np.exp(-np.arange(m) / (m / 5))
    crackle = crackle - _lowpass(crackle, 0.15)
    fire = 0.6 * rumble / (np.abs(rumble).max() + 1e-9) + 0.45 * crackle
    _write(folder / "Fireplace crackling indoor.wav", 0.8 * fire / (np.abs(fire).max() + 1e-9))


def prepare_ambience(progress=None):
    """Les ambiances de .cache/sonniss/ambience/ : en boucles, écoutées par CLAP. Renvoie leur nombre."""
    folder = bank_dir() / "ambience"
    folder.mkdir(parents=True, exist_ok=True)
    synth = ambience_raw_dir() / "_fabriquées"
    synth.mkdir(parents=True, exist_ok=True)
    _synth_ambiences(synth)
    files = sorted(p for p in ambience_raw_dir().rglob("*") if p.suffix.lower() in (".wav", ".flac")) \
        if ambience_raw_dir().is_dir() else []
    rows = []
    for i, src in enumerate(files):
        if re.search(AMB_SKIP, src.name.lower()):
            continue
        try:
            y = _decode(src)
        except Exception:
            continue
        if len(y) < 8 * RATE:
            continue
        name = hashlib.sha1(src.name.encode()).hexdigest()[:16] + ".wav"
        _write(folder / name, _loop(y))
        rows.append({"file": name, "src": src.name, "pack": src.parent.name})
        if progress:
            progress(i + 1, 2 * len(files))
    if not rows:
        return 0
    vecs = embed_audio([folder / r["file"] for r in rows])
    np.save(bank_dir() / "ambience_vectors.npy", vecs.astype(np.float16))
    (bank_dir() / "ambience.json").write_text(json.dumps({"version": BANK_VERSION, "loops": rows}, ensure_ascii=False),
                                             encoding="utf-8")
    close()
    _AMB.clear()
    return len(rows)


_AMB = {}


def ambience_bank():
    if not _AMB:
        try:
            index = json.loads((bank_dir() / "ambience.json").read_text(encoding="utf-8"))
            _AMB.update(loops=index["loops"], vectors=np.load(bank_dir() / "ambience_vectors.npy").astype(np.float32))
        except (OSError, ValueError, KeyError):
            _AMB.update(loops=[], vectors=np.zeros((0, 512), np.float32))
    return _AMB


def ambience_ready():
    return bool(ambience_bank()["loops"])


def best_ambience(query):
    """Le nom de la boucle d'ambiance la plus proche de la phrase (vecteur CLAP), ou None."""
    b = ambience_bank()
    if not b["loops"]:
        return None
    return b["loops"][int(np.argmax(b["vectors"] @ np.asarray(query, np.float32)))]["file"]


def ambience_file(name):
    path = bank_dir() / "ambience" / name
    return path if name and path.is_file() else None


if __name__ == "__main__":
    import sys

    show = lambda d, t: print(f"{d}/{t}", end="\r", flush=True)  # noqa: E731
    if "--download" in sys.argv:  # les sons Sonniss utiles (sonniss.py), puis tout est préparé
        from manhwa import sonniss

        print("  {} bruitages, {} ambiances".format(*sonniss.download(show)))
    if "--ambience" not in sys.argv:
        print(f"\n{prepare(show)} prises rangées dans {bank_dir()}")
    print(f"\n{prepare_ambience(show)} ambiances prêtes")
