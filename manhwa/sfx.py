"""Bruitages : une bibliothèque de sons libres (CC0) rangés par catégorie, et le son de chaque SFX.

Les sons viennent de trois packs de Kenney (kenney.nl, licence CC0 : libres, sans crédit
obligatoire), téléchargés au premier usage dans .cache/ et vérifiés par SHA-256. Ce qui
manque (whoosh, battement de cœur, feu, vent) est fabriqué ici. On peut ajouter ses propres sons :
un fichier .ogg / .wav / .mp3 dans sfx/<catégorie>/ (à la racine du projet) s'ajoute au choix.

Le son d'un SFX : frame["sounds"] = {texte de la bulle: catégorie | "a+b" | "none"}, choisi dans
le Studio (onglet Sons) ; sans choix, la catégorie proposée par GPT (relecture) si elle est sûre.
« a+b » : deux sons ensemble (un coup et du sang), l'un juste après l'autre.
"""
import hashlib
import io
import os
import re
import shutil
import zipfile

import numpy as np

from manhwa.config import ROOT

PACKS = {
    "kenney_impact-sounds.zip": (
        "https://kenney.nl/media/pages/assets/impact-sounds/87b4ddecda-1677589768/kenney_impact-sounds.zip",
        "029d734af1582474edf3a694d1b0cebc97c1c152f2f39fa34d4c2bafc5de77f8"),
    "kenney_rpg-audio.zip": (
        "https://kenney.nl/media/pages/assets/rpg-audio/8e99002d76-1677590336/kenney_rpg-audio.zip",
        "6dbeaf8544da958d8f2adcb4a4a4b76c1ade34a05f8ab9edccd327da7375f38b"),
    "kenney_sci-fi-sounds.zip": (
        "https://kenney.nl/media/pages/assets/sci-fi-sounds/6b296f9ecf-1677589334/kenney_sci-fi-sounds.zip",
        "119340f351a5098ad814f78719438c0da355a9ce8a4c8a3af6a8d48aa3d49e04"),
}

# catégorie → (libellé, débuts de noms de fichiers dans les packs)
CATEGORIES = {
    "punch": ("Coup de poing", ["impactPunch_heavy", "impactPunch_medium"]),
    "impact": ("Coup sourd", ["impactSoft_heavy", "impactGeneric_light", "impactPlate_heavy"]),
    "slam": ("Projeté contre un mur", []),
    "fall": ("Chute au sol", ["impactSoft_medium", "dropLeather"]),
    "slash": ("Lame qui tranche", ["knifeSlice", "chop"]),
    "blade_draw": ("Lame qu'on dégaine", ["drawKnife"]),
    "metal": ("Métal, armes qui s'entrechoquent", ["impactMetal_heavy", "impactMetal_medium", "metalPot"]),
    "energy": ("Rayon d'énergie", ["laserLarge"]),
    "blood": ("Sang", ["slime"]),
    "heartbeat": ("Cœur", []),
    "footsteps": ("Pas", ["footstep_wood", "footstep_concrete", "footstep_grass"]),
    "cloth": ("Tissu", ["cloth"]),
    "door": ("Porte", ["doorOpen", "doorClose", "creak"]),
    "glass": ("Verre brisé", ["impactGlass_heavy", "impactGlass_medium"]),
    "wood": ("Bois / planche", ["impactWood_heavy", "impactPlank_medium", "impactWood_medium"]),
    "bell": ("Cloche, gong", ["impactBell_heavy"]),
    "coins": ("Pièces", ["handleCoins"]),
    "paper": ("Papier, livre", ["bookFlip", "bookOpen", "bookClose"]),
    "fire": ("Feu", []),
    "wind": ("Vent", []),
    "thunder": ("Tonnerre", ["lowFrequency_explosion"]),
    "explosion": ("Explosion", ["explosionCrunch", "lowFrequency_explosion"]),
    "rumble": ("Grondement, tremblement", ["lowFrequency_explosion"]),
    "magic": ("Magie, aura", ["forceField"]),
    "whoosh": ("Mouvement rapide", []),
}
# l'onglet Sons range la bibliothèque par familles
FAMILIES = [
    ("Coups", ["punch", "impact", "slam", "fall"]),
    ("Armes", ["slash", "blade_draw", "metal", "energy"]),
    ("Corps", ["blood", "heartbeat", "footsteps", "cloth"]),
    ("Objets", ["door", "glass", "wood", "bell", "coins", "paper"]),
    ("Éléments", ["fire", "wind", "thunder", "explosion", "rumble"]),
    ("Magie et vitesse", ["magic", "whoosh"]),
]
LIBRARY_VERSION = "4"  # à changer quand la bibliothèque change : elle est refaite
SKIP = {"slime_001.ogg"}  # trop long pour un bruitage (4,7 s)
NONE = "none"
SURE_FROM_GPT = set(CATEGORIES) - {"impact"}  # « impact » : GPT le dit pour tout, on laisse choisir
VOLUME = 0.55  # sous la voix
# la force du moment (GPT : 1 léger, 2 normal, 3 violent) → volume ; certains sons restent discrets
STRENGTH_GAIN = {1: 0.6, 2: 1.0, 3: 1.4}
CATEGORY_GAIN = {"cloth": 0.6, "footsteps": 0.7, "paper": 0.7, "coins": 0.8, "wind": 0.8, "heartbeat": 0.9}


def library_dir():
    return ROOT / ".cache" / "sfx"


def user_dir():
    return ROOT / "sfx"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def ensure_library():
    """Télécharge et range les sons s'il le faut. Renvoie le dossier de la bibliothèque."""
    import requests

    folder = library_dir()
    ready = folder / ".ready"
    if ready.is_file() and ready.read_text(encoding="utf-8").strip() == LIBRARY_VERSION:
        return folder
    shutil.rmtree(folder, ignore_errors=True)  # refaite en entier : pas de vieux sons rangés ailleurs
    folder.mkdir(parents=True, exist_ok=True)
    wanted = {}
    for cat, (_, prefixes) in CATEGORIES.items():
        for prefix in prefixes:
            wanted.setdefault(prefix, []).append(cat)
    for name, (url, sha) in PACKS.items():
        cached = ROOT / ".cache" / "kenney" / name
        data = cached.read_bytes() if cached.is_file() else None
        if data is None or _sha256(data) != sha:
            r = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0 (manhwa-studio)"})
            r.raise_for_status()
            data = r.content
            if _sha256(data) != sha:
                raise RuntimeError(f"Pack de sons {name} : empreinte inattendue, fichier refusé")
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                base = os.path.basename(info.filename)
                if not base.lower().endswith(".ogg") or base == "Preview.ogg" or base in SKIP:
                    continue
                stem = os.path.splitext(base)[0].rstrip("0123456789").rstrip("_")
                for cat in wanted.get(stem, []):
                    out = folder / cat / base
                    out.parent.mkdir(exist_ok=True)
                    out.write_bytes(z.read(info))
    _synthesize(folder)
    ready.write_text(LIBRARY_VERSION, encoding="utf-8")
    return folder


def _write_wav(path, samples, rate=44100):
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def _lowpass(x, cutoff):
    """Filtre passe-bas d'ordre 1 ; cutoff : un nombre ou une courbe (0 → 1) le long du son."""
    out, low = np.empty_like(x), 0.0
    cut = np.broadcast_to(cutoff, x.shape)
    for i in range(len(x)):
        low += cut[i] * (x[i] - low)
        out[i] = low
    return out


def _fire(folder, rng, rate):
    """Un feu qui crépite : grondement sourd + petits craquements au hasard."""
    for k, length in enumerate((2.0, 3.0)):
        n = int(rate * length)
        t = np.linspace(0, 1, n)
        rumble = _lowpass(rng.standard_normal(n), 0.01)
        rumble /= np.abs(rumble).max() + 1e-9
        crackle = np.zeros(n)
        for start in rng.integers(0, n - 2000, int(28 * length)):
            m = int(rng.integers(150, 900))
            crackle[start:start + m] += rng.uniform(0.3, 1.0) * rng.standard_normal(m) * np.exp(-np.arange(m) / (m / 5))
        crackle = crackle - _lowpass(crackle, 0.15)  # les craquements restent secs et aigus
        out = (0.55 * rumble + 0.5 * crackle) * np.minimum(1, np.minimum(t, 1 - t) * 6)
        _write_wav(folder / "fire" / f"fire_{k}.wav", 0.9 * out / (np.abs(out).max() + 1e-9), rate)


def _wind(folder, rng, rate):
    """Une rafale de vent : souffle filtré dont le filtre et le volume ondulent lentement."""
    for k, length in enumerate((2.0, 3.0)):
        n = int(rate * length)
        t = np.linspace(0, 1, n)
        swell = 0.5 + 0.5 * np.sin(np.pi * t) ** 2 * (0.8 + 0.2 * np.sin(2 * np.pi * (2 + k) * t))
        out = _lowpass(rng.standard_normal(n), 0.004 + 0.03 * swell)
        out *= swell * np.minimum(1, np.minimum(t, 1 - t) * 5)
        _write_wav(folder / "wind" / f"wind_{k}.wav", 0.8 * out / (np.abs(out).max() + 1e-9), rate)


def _decode(path, rate=44100):
    """Un son en échantillons (mono, entre -1 et 1), avec le ffmpeg du rendu."""
    import subprocess

    import imageio_ffmpeg

    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "quiet", "-i", str(path), "-f", "s16le", "-ac", "1",
                          "-ar", str(rate), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def _blood(folder, rng, rate):
    """Une éclaboussure : un « splash » mouillé (souffle grave qui retombe vite) et quelques gouttes."""
    for k, length in enumerate((0.7, 1.0)):
        n = int(rate * length)
        t = np.arange(n) / rate
        splash = _lowpass(rng.standard_normal(n), 0.06) * np.exp(-t * (9 + 3 * k))
        drops = np.zeros(n)
        for start in rng.integers(int(0.15 * rate), n - 3000, 4 + 2 * k):
            m = 1800
            tt = np.arange(m) / rate
            drops[start:start + m] += 0.35 * np.sin(2 * np.pi * rng.uniform(500, 900) * tt * (1 - 2 * tt)) * np.exp(-tt * 60)
        out = splash / (np.abs(splash).max() + 1e-9) + drops
        _write_wav(folder / "blood" / f"blood_{k}.wav", 0.9 * out / (np.abs(out).max() + 1e-9), rate)


def _slam(folder, rate):
    """Projeté contre un mur : un coup sourd, le bois qui craque et un grave qui résonne, ensemble."""
    soft = sorted((folder / "impact").glob("impactSoft_heavy*.ogg"))
    wood = sorted((folder / "wood").glob("impactWood_heavy*.ogg"))
    for k, (a, b) in enumerate(zip(soft, wood)):
        x, y = _decode(a, rate), _decode(b, rate)
        n = max(len(x), len(y), int(0.6 * rate))
        tt = np.arange(n) / rate
        out = 0.9 * np.sin(2 * np.pi * 52 * tt) * np.exp(-tt * 9)
        out[:len(x)] += x
        out[:len(y)] += 0.7 * y
        _write_wav(folder / "slam" / f"slam_{k}.wav", 0.95 * out / (np.abs(out).max() + 1e-9), rate)


def _synthesize(folder, rate=44100):
    """Les sons absents des packs : whoosh (souffle filtré qui monte et descend), cœur, feu, vent, sang, « contre un mur »."""
    rng = np.random.default_rng(7)
    _fire(folder, rng, rate)
    _wind(folder, rng, rate)
    _blood(folder, rng, rate)
    _slam(folder, rate)
    for k, length in enumerate((0.45, 0.6, 0.8)):
        n = int(rate * length)
        t = np.linspace(0, 1, n)
        noise = rng.standard_normal(n)
        out, low = np.zeros(n), 0.0
        cutoff = 0.02 + 0.25 * np.sin(np.pi * t) ** 2  # le filtre s'ouvre puis se referme
        for i in range(n):
            low += cutoff[i] * (noise[i] - low)
            out[i] = low
        out *= np.sin(np.pi * t) ** 1.5
        _write_wav(folder / "whoosh" / f"whoosh_{k}.wav", 0.9 * out / (np.abs(out).max() + 1e-9), rate)
    for k, bpm in enumerate((70, 95)):
        beat = 60 / bpm
        n = int(rate * beat * 2)
        out = np.zeros(n)
        for start, amp in ((0.0, 1.0), (0.28 * beat, 0.7), (beat, 1.0), (1.28 * beat, 0.7)):
            i0 = int(start * rate)
            m = int(0.12 * rate)
            tt = np.arange(m) / rate
            thump = amp * np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 35)
            out[i0:i0 + m] += thump[: max(0, min(m, n - i0))]
        _write_wav(folder / "heartbeat" / f"heartbeat_{k}.wav", 0.95 * out / (np.abs(out).max() + 1e-9), rate)


def files(category):
    """Les sons d'une catégorie : la bibliothèque pro (soundbank) si elle en a, sinon Kenney + sfx/<catégorie>/."""
    from manhwa import soundbank

    pro = soundbank.files(category)
    if pro:
        return pro
    out = []
    for folder in (library_dir() / category, user_dir() / category):
        if folder.is_dir():
            out += sorted(p for p in folder.iterdir() if p.suffix.lower() in (".ogg", ".wav", ".mp3"))
    return out


def pick(category, seed_text, query=None):
    """Un son de la catégorie, toujours le même pour une même bulle (et varié d'une bulle à l'autre).

    query : ce qu'on doit entendre (vecteur CLAP de la phrase de GPT) : la prise pro la plus proche.
    """
    from manhwa import soundbank

    if soundbank.files(category):
        return soundbank.best(category, query, seed_text)
    options = files(category)
    if not options:
        return None
    k = int(hashlib.sha1(seed_text.encode("utf-8")).hexdigest(), 16) % len(options)
    return options[k]


def labels():
    return {cat: label for cat, (label, _) in CATEGORIES.items()}


def layers(value):
    """« impact+blood » → ["impact", "blood"] ; « none » ou rien → []."""
    if isinstance(value, (list, tuple)):
        value = "+".join(value)
    return [c for c in str(value or "").split("+") if c in CATEGORIES][:2]


def clean(sound):
    """La valeur à ranger : une catégorie, « a+b », « none », ou None (revenir à la proposition)."""
    if sound is None or sound == NONE:
        return sound
    parts = sound if isinstance(sound, (list, tuple)) else str(sound).split("+")
    if not parts or len(parts) > 2 or any(p not in CATEGORIES for p in parts):
        raise ValueError("Catégorie de son inconnue")
    return "+".join(dict.fromkeys(parts))


def sample_files(value, seed, query=None):
    """Les fichiers d'un son (un par couche), toujours les mêmes pour une même bulle."""
    return [p for k, cat in enumerate(layers(value)) if (p := pick(cat, f"{seed}:{k}" if k else seed, query))]


def gains(value, strength=None):
    """Le volume de chaque couche : la force du moment, et les sons discrets plus bas."""
    base = STRENGTH_GAIN.get(strength or 2, 1.0)
    return [base * CATEGORY_GAIN.get(cat, 1.0) * (0.8 if k else 1.0) for k, cat in enumerate(layers(value))]


def category_of(path):
    """La catégorie d'un fichier de son (une prise pro est rangée dans l'index de soundbank)."""
    from pathlib import Path

    from manhwa import soundbank

    path = Path(path)
    if path.parent.name == "takes":
        return next((r["cat"] for r in soundbank.bank()["takes"] if r["file"] == path.name), "?")
    return path.parent.name


def query_of(ai):
    """Le vecteur CLAP rangé avec le choix de GPT (base64 de float16), ou None."""
    import base64

    q = (ai or {}).get("q")
    return np.frombuffer(base64.b64decode(q), np.float16).astype(np.float32) if q else None


def mix(value, seed, chapter=None, frame=None, rate=44100, ai=None):
    """Le son tel qu'il sera dans la vidéo (WAV) : ses couches, et la voix de la case si on la donne.

    Les sons partent comme au rendu (0,05 s puis 0,25 s plus tard) et sous la voix (VOLUME).
    ai : le choix de GPT pour cette case (la prise la plus proche, le volume selon la force).
    """
    import wave

    from manhwa.render import GAP_SECONDS

    voice = []
    for seg in (frame or {}).get("segments") or []:
        path = chapter.root / seg["audio"] if chapter and seg.get("audio") else None
        if path and path.is_file():
            voice += [_decode(path, rate), np.zeros(int(GAP_SECONDS * rate), np.float32)]
    voice = np.concatenate(voice) if voice else np.zeros(0, np.float32)
    level = VOLUME if len(voice) else 0.8
    hits = [_decode(p, rate) * level * g for p, g in zip(sample_files(value, seed, query_of(ai)),
                                                         gains(value, (ai or {}).get("strength")))]
    n = max([len(voice)] + [int((0.05 + 0.25 * k) * rate) + len(h) for k, h in enumerate(hits)] + [int(0.3 * rate)])
    out = np.zeros(n, np.float32)
    out[:len(voice)] += voice
    for k, h in enumerate(hits):
        at = int((0.05 + 0.25 * k) * rate)
        out[at:at + len(h)] += h
    out = np.clip(out, -1, 1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((out * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


# ---------- Le son de chaque SFX du chapitre ----------

# onomatopées anglaises → catégorie (lettres répétées ramenées à une : « WHOOOOSH » = « WHOSH »)
ONOMATOPOEIA = {
    "punch": ["BAM", "POW", "WHAM", "SMACK", "WHACK", "THWACK", "PUNCH", "BAMF"],
    "impact": ["THUD", "THUMP", "DOOM", "DUNK", "BONK", "THONK", "KADUNK"],
    "slash": ["SLASH", "SHLICK", "SLICE", "CHOP", "SHUNK"],
    "blade_draw": ["SHING", "SHINK", "SCHING", "SHRING", "SCHWING"],
    "blood": ["SPLAT", "SPLURT", "SQUELCH", "SPURT", "DRIP", "SPLASH"],
    "slam": ["CRUNCH", "WUMP"],
    "whoosh": ["WHOSH", "SWOSH", "FWOSH", "WOSH", "SWISH", "FWIP", "ZIP", "ZOM", "SWIP"],
    "explosion": ["BOM", "KABOM", "BLAM", "KRAKOM", "BLAST"],
    "glass": ["CRASH", "SHATER", "CRISH", "TINKLE"],
    "door": ["KNOCK", "CREAK", "SLAM", "CLICK"],
    "footsteps": ["STEP", "STOMP", "TAP", "TAK", "CLOP", "SHUFLE"],
    "metal": ["CLANG", "CLANK", "TING", "KANG", "CHING", "KLANG", "CLASH"],
    "heartbeat": ["BADUMP", "BADUM", "BUMP", "DOKI"],
    "thunder": ["RUMBLE", "KRAKA", "CRAKA"],
    "fire": ["FWOM", "CRACKLE", "WHOMP"],
    "wind": ["WHO", "FWO", "SWO"],
    "cloth": ["FLAP", "FLUTER", "RUSTLE", "SWISH"],
    "magic": ["WHIR", "HUM", "VWOM", "ZING"],
}


# bruitages coréens laissés sur l'image (덜컹 : ça claque, 쿵 : un choc sourd…)
KOREAN = {"쾅": "slam", "쿵": "impact", "퍽": "punch", "탁": "impact", "덜컹": "wood", "챙": "metal", "쨍": "metal",
          "철컥": "metal", "철컹": "metal", "휙": "whoosh", "슉": "whoosh", "쉭": "whoosh", "스윽": "cloth", "콰직": "slam", "푹": "slash",
          "촤악": "blood", "두근": "heartbeat", "펑": "explosion", "콰광": "explosion", "화르륵": "fire"}


def _squeeze(word):
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[^A-Z]", "", word.upper()))


_ONOMATOPOEIA = {_squeeze(w): cat for cat, ws in ONOMATOPOEIA.items() for w in ws}


def onomatopoeia(text):
    """La catégorie d'un bruitage dessiné lisible (« BAM! » → punch), sinon None."""
    for token in (text or "").split():
        w = _squeeze(token)
        if len(w) >= 3 and w in _ONOMATOPOEIA:
            return _ONOMATOPOEIA[w]
    for word, cat in sorted(KOREAN.items(), key=lambda kv: -len(kv[0])):
        if word in (text or ""):
            return cat
    return None


def _with_scene(item, scene, gpt):
    """Ajoute « je vois » (seen), ce qui se passe (what, why : GPT d'après la description de la case),
    les sons proposés (recs) et celui à mettre d'office (proposed, « a+b » pour deux sons)."""
    from manhwa.scene import recommend

    s = (scene or {}).get(item["frame"])
    ai = ((s or {}).get("ai") or {}).get(item["key"])
    memory = ((s or {}).get("memory") or {}).get(item["key"])
    recs, best = recommend(s, gpt, ai, memory=memory)
    item["recs"] = recs
    item["proposed"] = best or NONE
    item["seen"] = list(((s or {}).get("seen") or {}).keys())[:3]
    item["what"] = (ai or {}).get("what") or None
    item["why"] = (ai or {}).get("why") or None
    item["strength"] = (ai or {}).get("strength") or None
    if memory:
        item["why"] = f"Comme tes choix sur des cases qui ressemblent ({round(100 * memory['share'])} %)"
    return item


def spots(data, scene=None):
    """Les SFX du chapitre : [{"key", "frame", "text", "box", "crop", "sound", "suggested", "chosen", "recs"…}]."""
    from manhwa.review import effective

    out = []
    for i, frame in enumerate(data["frames"]):
        chosen = frame.get("sounds") or {}
        for b in effective(frame):
            if b["kind"] != "sfx":
                continue
            gpt = b.get("sfx")
            suggested = gpt if gpt in SURE_FROM_GPT else None
            out.append(_with_scene({
                "key": f"{frame['file']}#{b['index']}", "frame": frame["file"], "index": i, "text": b["orig"], "box": b["box"],
                "crop": frame["crop"], "chosen": b["orig"] in chosen,
                "sound": chosen.get(b["orig"], suggested or NONE), "suggested": suggested, "gpt": gpt,
            }, scene, gpt if gpt in CATEGORIES else onomatopoeia(b["orig"])))
    return out


def set_sounds(data, choices):
    """choices : [{"key", "sound": catégorie | "none" | None (revenir à la proposition)}]."""
    frames = {f["file"]: f for f in data["frames"]}
    n = 0
    for c in choices:
        if str(c.get("key", "")).startswith(ACTION_PREFIX):  # une case sans texte
            n += set_action(data, str(c["key"])[len(ACTION_PREFIX):], c.get("sound"))
            continue
        file, _, index = str(c.get("key", "")).partition("#")
        frame = frames.get(file)
        bubbles = (frame or {}).get("bubbles") or []
        if not index.isdigit() or int(index) >= len(bubbles):
            continue
        sound = clean(c.get("sound"))
        sounds = frame.setdefault("sounds", {})
        text = bubbles[int(index)]["text"]
        if sound is None:
            sounds.pop(text, None)
        else:
            sounds[text] = sound
        n += 1
    return n


def frame_sounds(data, scene=None, auto=False):
    """{fichier de frame: [(chemin du son, volume), ...]} pour le rendu (bulles SFX, puis cases sans texte).

    auto : une case où tu n'as rien choisi prend le son proposé (scene : ce que montrent les cases).
    Le volume suit la force du moment (GPT) ; la prise est la plus proche de ce qu'on doit entendre.
    """
    out = {}
    for frame, sound, seed, ai in _frame_items(data, scene, auto):
        for path, g in zip(sample_files(sound, seed, query_of(ai)), gains(sound, (ai or {}).get("strength"))):
            out.setdefault(frame, []).append((str(path), round(g, 2)))
    return out


def _frame_items(data, scene, auto):
    """(frame, son, graine, choix de GPT) de chaque bruitage et de chaque case sans texte."""
    for items, seed in ((silent_frames(data, scene), "frame"), (spots(data, scene), "text")):
        for s in items:
            sound = s["proposed"] if auto and not s["chosen"] else s["sound"]
            yield s["frame"], sound, s[seed], (((scene or {}).get(s["frame"]) or {}).get("ai") or {}).get(s["key"])


def frame_hits(data, scene=None, auto=False):
    """{fichier de frame: [(couches, force), ...]} : ce qui fait réagir l'image (motion.py)."""
    out = {}
    for frame, sound, _, ai in _frame_items(data, scene, auto):
        if layers(sound):
            out.setdefault(frame, []).append((layers(sound), (ai or {}).get("strength") or 2))
    return out


def video_hits(chapter, data, cfg):
    from manhwa.scene import load_scene

    return frame_hits(data, load_scene(chapter), bool((cfg.get("auto") or {}).get("sounds", True)))


def video_sounds(chapter, data, cfg):
    """Les sons de la vidéo : tes choix, et la proposition ailleurs si [auto] sounds est activé."""
    from manhwa.scene import load_scene

    auto = bool((cfg.get("auto") or {}).get("sounds", True))
    return frame_sounds(data, load_scene(chapter), auto)  # la scène sert aussi à choisir la prise et le volume


# ---------- Cases sans texte (action, décor) ----------

ACTION_PREFIX = "frame:"  # clé d'une case entière (et pas d'une bulle) dans set_sounds


def silent_frames(data, scene=None):
    """Les cases où personne ne parle : on peut y mettre un son (coup, pas, porte…)."""
    from manhwa.review import effective, is_spoken

    out = []
    for i, frame in enumerate(data["frames"]):
        if any(is_spoken(b) for b in effective(frame)):
            continue
        action = frame.get("action_sound") or {}
        out.append(_with_scene({"key": ACTION_PREFIX + frame["file"], "frame": frame["file"], "index": i,
                                "crop": frame["crop"], "sound": action.get("chosen") or NONE,
                                "chosen": bool(action.get("chosen")), "suggested": action.get("suggested"),
                                "reason": action.get("reason")}, scene, action.get("suggested")))
    return out


def set_action(data, file, sound):
    frame = next((f for f in data["frames"] if f["file"] == file), None)
    if not frame:
        return 0
    sound = clean(sound)
    action = frame.setdefault("action_sound", {})
    if sound is None:
        action.pop("chosen", None)
    else:
        action["chosen"] = sound
    return 1


def suggest_sounds(chapter, cfg=None, progress=None):
    """GPT choisit le son de chaque bruitage et de chaque case sans texte, d'après ce qui s'y passe.

    Il lit, dans l'ordre de l'histoire, la description de chaque case (vision.py : « il est projeté
    contre un mur »), les répliques autour et le bruitage dessiné. Il répond, pour chacune : ce qui se
    passe (en français), un ou deux sons (un coup et du sang) ou aucun, et pourquoi. Rangé dans
    scene.json (« ai ») : c'est une proposition, tes choix restent les tiens.
    """
    import json

    from manhwa.llm import chat
    from manhwa.review import effective, is_spoken
    from manhwa.scene import load_scene, scene_path

    data = chapter.load()
    frames = data["frames"]
    seen = load_scene(chapter)
    said = [[b["text"] for b in effective(f) if is_spoken(b)] for f in frames]
    index = {f["file"]: i for i, f in enumerate(frames)}
    plain = {f: {k: v for k, v in e.items() if k != "ai"} for f, e in seen.items()}  # la proposition d'avant GPT
    items = []
    for s in sorted(spots(data, plain) + silent_frames(data, plain), key=lambda x: (index[x["frame"]], x["key"])):
        i = index[s["frame"]]
        look = seen.get(s["frame"]) or {}
        items.append({"id": s["key"], "panel": i + 1, "drawn_sfx": s.get("text"), "first_guess": s["recs"][:3] or None,
                      "panel_shows": look.get("desc") or None, "sounds_a_viewer_would_hear": look.get("heard") or None,
                      "lines_in_panel": said[i][:3] or None,
                      "lines_before": [t for k in range(max(0, i - 2), i) for t in said[k]][-2:] or None})
    if not items:
        return 0
    rule = ("You are the sound designer of a manhwa video (TikTok). For each item (in story order) choose the sound "
            "effects that make the moment hit. first_guess comes from an image classifier and from the drawn SFX: it "
            "matches the human editor 4 times out of 5, so keep its first category unless panel_shows or the lines "
            "clearly show another action (a body thrown against a wall: slam; a blade being drawn: blade_draw). "
            "panel_shows comes from a small vision model and can be wrong or exaggerated. Add a 2nd sound only when a "
            "second thing clearly happens at that moment; blood only for a fresh wound or a splash right now, not for "
            "old injuries or a bloody face. A drawn SFX always gets a sound. A silent panel gets no sound only if "
            "nothing moves (a still face, scenery). "
            f"categories: {list(CATEGORIES)}. "
            "Answer JSON: {\"items\": [{\"id\", \"what\": what happens, in French, under 12 words, "
            "\"sounds\": [0 to 2 categories, most important first], \"why\": in French, under 10 words, "
            "\"hear\": what the main sound should sound like, in English, under 10 words (e.g. 'heavy body slammed "
            "into a wooden wall'), \"strength\": 1 soft, 2 normal or 3 violent}]}")
    got = {}
    batch = 40
    for start in range(0, len(items), batch):
        part = items[start:start + batch]
        answer = chat([{"role": "system", "content": rule},
                       {"role": "user", "content": json.dumps({"items": part}, ensure_ascii=False)}], max_tokens=8000)
        for x in answer.get("items", []):
            if isinstance(x, dict) and x.get("id"):
                strength = x.get("strength")
                got[str(x["id"])] = {"what": str(x.get("what") or "")[:120],
                                     "sounds": [c for c in (x.get("sounds") or []) if c in CATEGORIES][:2],
                                     "why": str(x.get("why") or "")[:100], "hear": str(x.get("hear") or "")[:100],
                                     "strength": strength if strength in (1, 2, 3) else 2}
        if progress:
            progress(min(len(items), start + batch), len(items))
    _hear_vectors(got)
    scene = load_scene(chapter)  # relu : la description a pu changer pendant l'appel
    for key, x in got.items():
        file = key[len(ACTION_PREFIX):] if key.startswith(ACTION_PREFIX) else key.partition("#")[0]
        if file in scene:
            scene[file].setdefault("ai", {})[key] = x
    scene_path(chapter).write_text(json.dumps(scene, ensure_ascii=False), encoding="utf-8")
    return len(got)


def _hear_vectors(got):
    """Ce qu'on doit entendre → vecteur CLAP (rangé en base64), pour prendre la prise pro la plus proche."""
    import base64

    from manhwa import soundbank

    keys = [k for k, x in got.items() if x["sounds"] and x["hear"]]
    if not keys or not soundbank.ready():
        return
    try:
        vecs = soundbank.embed_texts([f"{got[k]['hear']}, sound effect" for k in keys])
    except Exception as e:  # sans CLAP : un son de la bonne catégorie, au hasard
        print(f"  [!] CLAP indisponible ({e}) : prises au hasard")
        return
    finally:
        soundbank.close()
    for k, v in zip(keys, vecs):
        got[k]["q"] = base64.b64encode(v.astype(np.float16).tobytes()).decode()


suggest_actions = suggest_sounds  # l'ancien nom
