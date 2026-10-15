"""Bruitages : une bibliothèque de sons libres (CC0) rangés par catégorie, et le son de chaque SFX.

Les sons viennent de trois packs de Kenney (kenney.nl, licence CC0 : libres, sans crédit
obligatoire), téléchargés au premier usage dans .cache/ et vérifiés par SHA-256. Ce qui
manque (whoosh, battement de cœur) est fabriqué ici. On peut ajouter ses propres sons :
un fichier .ogg / .wav / .mp3 dans sfx/<catégorie>/ (à la racine du projet) s'ajoute au choix.

Le son d'un SFX : frame["sounds"] = {texte de la bulle: catégorie | "none"}, choisi dans
le Studio (onglet Sons) ; sans choix, la catégorie proposée par GPT (relecture) si elle est sûre.
"""
import hashlib
import io
import os
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
    "impact": ("Coup sourd", ["impactSoft_heavy", "impactGeneric_light", "impactPlate_heavy"]),
    "punch": ("Coup de poing", ["impactPunch_heavy", "impactPunch_medium"]),
    "slash": ("Lame", ["knifeSlice", "drawKnife", "chop"]),
    "glass": ("Verre brisé", ["impactGlass_heavy", "impactGlass_medium"]),
    "wood": ("Bois / planche", ["impactWood_heavy", "impactPlank_medium", "impactWood_medium"]),
    "metal": ("Métal", ["impactMetal_heavy", "impactMetal_medium", "metalPot"]),
    "explosion": ("Explosion", ["explosionCrunch", "lowFrequency_explosion"]),
    "whoosh": ("Whoosh", []),
    "footsteps": ("Pas", ["footstep_wood", "footstep_concrete", "footstep_grass"]),
    "door": ("Porte", ["doorOpen", "doorClose", "creak"]),
    "magic": ("Magie / aura", ["forceField"]),
    "cloth": ("Tissu", ["cloth"]),
    "heartbeat": ("Cœur", []),
    "thunder": ("Tonnerre", ["lowFrequency_explosion"]),
}
NONE = "none"
SURE_FROM_GPT = set(CATEGORIES) - {"impact"}  # « impact » : GPT le dit pour tout, on laisse choisir
VOLUME = 0.55  # sous la voix


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
    if (folder / ".ready").is_file():
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    wanted = {prefix: cat for cat, (_, prefixes) in CATEGORIES.items() for prefix in prefixes}
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
                if not base.lower().endswith(".ogg") or base == "Preview.ogg":
                    continue
                stem = os.path.splitext(base)[0].rstrip("0123456789").rstrip("_")
                for prefix, cat in wanted.items():
                    if stem == prefix:
                        out = folder / cat / base
                        out.parent.mkdir(exist_ok=True)
                        out.write_bytes(z.read(info))
    _synthesize(folder)
    (folder / ".ready").write_text("ok", encoding="utf-8")
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


def _synthesize(folder, rate=44100):
    """Les sons absents des packs : whoosh (souffle filtré qui monte et descend) et cœur."""
    rng = np.random.default_rng(7)
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
    """Les sons d'une catégorie (bibliothèque + sons ajoutés dans sfx/<catégorie>/)."""
    out = []
    for folder in (library_dir() / category, user_dir() / category):
        if folder.is_dir():
            out += sorted(p for p in folder.iterdir() if p.suffix.lower() in (".ogg", ".wav", ".mp3"))
    return out


def pick(category, seed_text):
    """Un son de la catégorie, toujours le même pour une même bulle (et varié d'une bulle à l'autre)."""
    options = files(category)
    if not options:
        return None
    k = int(hashlib.sha1(seed_text.encode("utf-8")).hexdigest(), 16) % len(options)
    return options[k]


def labels():
    return {cat: label for cat, (label, _) in CATEGORIES.items()}


# ---------- Le son de chaque SFX du chapitre ----------

def spots(data):
    """Les SFX du chapitre : [{"key", "frame", "text", "box", "crop", "sound", "suggested", "chosen"}]."""
    from manhwa.review import effective

    out = []
    for frame in data["frames"]:
        chosen = frame.get("sounds") or {}
        for b in effective(frame):
            if b["kind"] != "sfx":
                continue
            gpt = b.get("sfx")
            suggested = gpt if gpt in SURE_FROM_GPT else None
            out.append({
                "key": f"{frame['file']}#{b['index']}", "frame": frame["file"], "text": b["orig"], "box": b["box"],
                "crop": frame["crop"], "chosen": b["orig"] in chosen,
                "sound": chosen.get(b["orig"], suggested or NONE), "suggested": suggested, "gpt": gpt,
            })
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
        sound = c.get("sound")
        if sound not in (None, NONE) and sound not in CATEGORIES:
            raise ValueError("Catégorie de son inconnue")
        sounds = frame.setdefault("sounds", {})
        text = bubbles[int(index)]["text"]
        if sound is None:
            sounds.pop(text, None)
        else:
            sounds[text] = sound
        n += 1
    return n


def frame_sounds(data):
    """{fichier de frame: [chemin du son, ...]} pour le rendu (bulles SFX, puis cases sans texte)."""
    out = {}
    for s in silent_frames(data):
        if s["sound"] != NONE:
            path = pick(s["sound"], s["frame"])
            if path:
                out.setdefault(s["frame"], []).append(str(path))
    for s in spots(data):
        if s["sound"] != NONE:
            path = pick(s["sound"], s["text"])
            if path:
                out.setdefault(s["frame"], []).append(str(path))
    return out


# ---------- Cases sans texte (action, décor) ----------

ACTION_PREFIX = "frame:"  # clé d'une case entière (et pas d'une bulle) dans set_sounds


def silent_frames(data):
    """Les cases où personne ne parle : on peut y mettre un son (coup, pas, porte…)."""
    from manhwa.review import effective, is_spoken

    out = []
    for i, frame in enumerate(data["frames"]):
        if any(is_spoken(b) for b in effective(frame)):
            continue
        action = frame.get("action_sound") or {}
        out.append({"key": ACTION_PREFIX + frame["file"], "frame": frame["file"], "index": i, "crop": frame["crop"],
                    "sound": action.get("chosen") or NONE, "chosen": bool(action.get("chosen")),
                    "suggested": action.get("suggested"), "reason": action.get("reason")})
    return out


def set_action(data, file, sound):
    frame = next((f for f in data["frames"] if f["file"] == file), None)
    if not frame:
        return 0
    if sound not in (None, NONE) and sound not in CATEGORIES:
        raise ValueError("Catégorie de son inconnue")
    action = frame.setdefault("action_sound", {})
    if sound is None:
        action.pop("chosen", None)
    else:
        action["chosen"] = sound
    return 1


def suggest_actions(chapter, cfg=None, progress=None):
    """GPT propose un son pour les cases sans texte, d'après les répliques autour (il ne voit pas l'image)."""
    import json

    from manhwa.llm import chat
    from manhwa.review import effective, is_spoken

    data = chapter.load()
    frames = data["frames"]
    said = [[b["text"] for b in effective(f) if is_spoken(b)] for f in frames]
    drawn = [[b["orig"] for b in effective(f) if b["kind"] == "sfx"] for f in frames]
    items = []
    for s in silent_frames(data):
        i = s["index"]
        before = [t for k in range(max(0, i - 3), i) for t in said[k]][-3:]
        after = [t for k in range(i + 1, min(len(frames), i + 3)) for t in said[k]][:2]
        items.append({"id": s["frame"], "panel": i + 1, "lines_before": before, "lines_after": after,
                      "drawn_sfx_ocr": drawn[i] or None})
    if not items:
        return 0
    prompt = {
        "task": ("These manhwa panels have no dialogue. From the surrounding lines (you cannot see the art), say if a "
                 "sound effect clearly fits the panel. Most silent panels are just scenery or reactions: answer 'none' "
                 "unless the lines make the action obvious (a strike, a fall, a door, footsteps, a blade, an explosion…). "
                 f"category: one of {list(CATEGORIES) + [NONE]}. reason in French, under 10 words. "
                 "Answer JSON: {\"panels\": [{\"id\", \"category\", \"reason\"}]}"),
        "panels": items,
    }
    if progress:
        progress(0, 1)
    answer = chat([{"role": "system", "content": "You are a sound designer for webtoon videos. Answer only with JSON."},
                   {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}], max_tokens=6000)
    got = {str(x.get("id")): x for x in answer.get("panels", []) if isinstance(x, dict)}
    data = chapter.load()  # relu : on a pu choisir des sons pendant l'appel
    n = 0
    for frame in data["frames"]:
        x = got.get(frame["file"])
        if not x:
            continue
        action = frame.setdefault("action_sound", {})
        cat = x.get("category")
        action["suggested"] = cat if cat in CATEGORIES else None
        action["reason"] = str(x.get("reason") or "")[:80] if cat in CATEGORIES else None
        n += cat in CATEGORIES
    chapter.save(data)
    if progress:
        progress(1, 1)
    return n
