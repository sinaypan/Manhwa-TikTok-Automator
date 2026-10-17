"""Une voix par personnage : liste des voix edge-tts, proposition, réglages et extraits.

Une voix = {"name": "en-US-GuyNeural", "pitch": "-6Hz", "rate": "-4%", "reason": "…", "by": "gpt"|"auto"|"user"}
    pitch / rate : petits décalages propres au personnage (plus grave, plus posé…).
Le narrateur garde la voix de config.toml ([tts] voice), sauf si on la change.

L'émotion d'une réplique (repérée par GPT) ajuste encore vitesse, hauteur et volume :
edge-tts ne sait pas « jouer » une émotion, mais un cri plus fort et plus rapide, ou une
réplique triste plus lente et plus basse, s'entendent déjà.
"""
import asyncio
import json
import os
import re
import time

from manhwa.config import ROOT
from manhwa.project import fingerprint

CACHE = ROOT / ".cache"
VOICES_TTL = 30 * 24 * 3600  # la liste des voix est relue une fois par mois

# émotion → (vitesse %, hauteur Hz, volume %) ajoutés à la voix du personnage
EMOTIONS = {
    "neutral": (0, 0, 0),
    "calm": (-5, -2, -5),
    "happy": (5, 4, 5),
    "excited": (10, 6, 10),
    "mocking": (0, 3, 0),
    "angry": (8, 3, 15),
    "shouting": (10, 6, 25),
    "cold": (-6, -4, -5),
    "sad": (-10, -4, -10),
    "scared": (8, 6, -5),
    "surprised": (6, 8, 10),
    "pain": (-4, -2, 5),
    "whisper": (-8, -2, -35),
    "thinking": (-6, -1, -15),
}
EMOTION_LABELS = {
    "neutral": "neutre", "calm": "calme", "happy": "joyeux", "excited": "excité", "mocking": "moqueur",
    "angry": "en colère", "shouting": "crie", "cold": "froid", "sad": "triste", "scared": "effrayé",
    "surprised": "surpris", "pain": "douleur", "whisper": "chuchote", "thinking": "pensée",
}


# ---------- Liste des voix ----------

def list_voices():
    """Voix anglaises : edge-tts (en ligne) puis Kokoro (local) — [{"name", "gender", "locale", "traits"}]."""
    from manhwa import kokoro_tts

    return _edge_voices() + (kokoro_tts.catalog() if kokoro_tts.available() else [])


def _edge_voices():
    """Voix anglaises d'edge-tts (mises en cache)."""
    path = CACHE / "voices.json"
    if path.is_file() and time.time() - path.stat().st_mtime < VOICES_TTL:
        return json.loads(path.read_text(encoding="utf-8"))
    import edge_tts

    try:
        raw = asyncio.run(edge_tts.list_voices())
    except Exception:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        raise
    voices = [{"name": v["ShortName"], "gender": v["Gender"], "locale": v["Locale"],
               "traits": ", ".join((v.get("VoiceTag") or {}).get("VoicePersonalities") or [])}
              for v in raw if v["Locale"].startswith("en-") and "Multilingual" not in v["ShortName"]]
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps(voices, indent=1), encoding="utf-8")
    return voices


def short_name(name):
    """« en-US-GuyNeural » → « Guy (US) » ; « kokoro:am_michael » → « Michael (US, Kokoro) »."""
    from manhwa import kokoro_tts

    if kokoro_tts.is_kokoro(name):
        return kokoro_tts.label(name)
    m = re.match(r"en-([A-Z]{2})-(\w+?)Neural$", name or "")
    return f"{m.group(2)} ({m.group(1)})" if m else (name or "")


# ---------- Proposition sans GPT ----------

# voix américaines et britanniques d'abord : les plus naturelles en anglais
PREFERRED = {
    "Male": ["en-US-AndrewNeural", "en-US-GuyNeural", "en-US-BrianNeural", "en-US-EricNeural", "en-US-RogerNeural",
             "en-GB-RyanNeural", "en-US-SteffanNeural", "en-GB-ThomasNeural", "en-AU-WilliamNeural", "en-CA-LiamNeural"],
    "Female": ["en-US-AvaNeural", "en-US-EmmaNeural", "en-US-JennyNeural", "en-US-AriaNeural", "en-GB-SoniaNeural",
               "en-US-MichelleNeural", "en-GB-LibbyNeural", "en-GB-MaisieNeural", "en-AU-NatashaNeural", "en-US-AnaNeural"],
}


def gender_of(page):
    g = (page or {}).get("gender", "").lower()
    return "Female" if g.startswith("f") else "Male" if g.startswith("m") else None


PITCH_STEPS = (0, -6, 6, -10, 4, -3, 9)  # Hz : deux personnages ne parlent jamais à la même hauteur
OLD_WORDS = re.compile(r"\b(old|elder|elderly|aged|grand(father|mother|pa|ma)|ancestor|master|patriarch)\b", re.I)
GREY_HAIR = ("white", "grey", "gray", "silver")


def is_old(page):
    """Un personnage âgé d'après le wiki : cheveux blancs ou gris, ou « old », « master »…"""
    p = page or {}
    hair = f"{p.get('hair') or ''} {p.get('hair_key') or ''}".lower()
    return any(g in hair for g in GREY_HAIR) or bool(OLD_WORDS.search(p.get("personality") or ""))


def _by_accent(pool, voices):
    """Les voix rangées en alternant les accents (US, UK, Australie…) : deux voisins ne se ressemblent pas."""
    locale = {v["name"]: v.get("locale") or v["name"][:5] for v in voices}
    groups = {}
    for name in pool:
        groups.setdefault(locale.get(name, name[:5]), []).append(name)
    out = []
    while any(groups.values()):
        for names in groups.values():
            if names:
                out.append(names.pop(0))
    return out


def auto_voice(gender, used, narrator, voices, page=None, rank=0):
    """Une voix du bon genre, pas encore prise, différente de celle du narrateur.

    rank : combien de personnages ont déjà reçu une voix (la hauteur change à chaque fois) ;
    page : la fiche du wiki (un personnage âgé parle plus grave et plus lentement).
    """
    names = {v["name"] for v in voices}
    pool = [n for n in PREFERRED.get(gender or "Male", PREFERRED["Male"]) if n in names]
    pool += [v["name"] for v in voices if v["gender"] == (gender or "Male") and v["name"] not in pool]
    pool = _by_accent(pool, voices)
    old = is_old(page)
    pitch = -10 if old else PITCH_STEPS[rank % len(PITCH_STEPS)]
    rate = "-8%" if old else "+0%"
    why = "âgé (wiki) : plus grave et plus lent" if old else "même genre, voix libre, accent et hauteur différents"
    for name in pool:
        if name not in used and name != narrator:
            return {"name": name, "pitch": f"{pitch:+d}Hz", "rate": rate, "reason": why, "by": "auto"}
    return {"name": pool[rank % len(pool)] if pool else narrator, "pitch": f"{pitch - 4:+d}Hz", "rate": rate,
            "reason": "voix déjà prise : hauteur décalée", "by": "auto"}


def spread(characters, step=8):
    """Deux personnages sur la même voix de base : au moins `step` Hz d'écart (sauf ce que tu as choisi)."""
    taken = {}
    changed = False
    for c in characters:
        v = c.get("voice")
        if not v or c.get("silent"):
            continue
        pitches = taken.setdefault(v["name"], [])
        p = _number(v.get("pitch"), 50)
        if v.get("by") != "user" and not c.get("voice_ok") and any(abs(p - q) < step for q in pitches):
            # la hauteur libre la plus proche de celle prévue
            p = next(x for d in range(1, 60) for x in (p + d, p - d) if all(abs(x - q) >= step for q in pitches))
            if f"{p:+d}Hz" != v.get("pitch"):
                v["pitch"] = f"{p:+d}Hz"
                changed = True
        pitches.append(p)
    return changed


# ---------- Proposition par GPT ----------

def gpt_voices(people, voices, narrator):
    """people : [{"id", "name", "gender", "personality", "lines": [quelques répliques]}].

    Renvoie {id: voix}. GPT choisit dans la liste, une voix différente par personnage
    quand c'est possible, et peut décaler un peu la hauteur et la vitesse.
    """
    from manhwa.llm import chat

    catalog = [{"name": v["name"], "gender": v["gender"], "traits": v["traits"]} for v in voices]
    prompt = {
        "task": ("Cast a text-to-speech voice for each character of a Korean manhwa (webtoon) being dubbed in English. "
                 "Pick from the catalog. Match gender and age; match personality (a villain or a cold killer: deep, "
                 "slow, steady; a manipulator: calm and smooth; a young hero: lively; an old master: deep and slow). "
                 "Use a different voice for each character when possible and never the narrator's voice. "
                 "pitch is an offset from -15Hz (deeper) to +15Hz, rate from -15% to +15%. "
                 "Answer in JSON: {\"voices\": [{\"id\", \"voice\", \"pitch\", \"rate\", \"reason\"}]}, "
                 "reason in French, under 12 words."),
        "narrator_voice": narrator,
        "catalog": catalog,
        "characters": people,
    }
    answer = chat([{"role": "system", "content": "You are a casting director. Answer only with JSON."},
                   {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}], max_tokens=3000)
    names = {v["name"] for v in voices}
    out = {}
    for item in answer.get("voices", []):
        if item.get("id") in {p["id"] for p in people} and item.get("voice") in names:
            out[item["id"]] = {"name": item["voice"], "pitch": hz(item.get("pitch")), "rate": pct(item.get("rate")),
                               "reason": str(item.get("reason", ""))[:120], "by": "gpt"}
    return out


def _number(value, limit):
    m = re.search(r"[-+]?\d+", str(value or "0"))
    return max(-limit, min(limit, int(m.group()) if m else 0))


def hz(value, limit=20):
    return f"{_number(value, limit):+d}Hz"


def pct(value, limit=50):
    return f"{_number(value, limit):+d}%"


# ---------- Réglages d'une réplique ----------

def prosody(cfg, voice, emotion=None):
    """{"voice", "rate", "pitch", "volume"} pour edge-tts : vitesse de la vidéo × voix × émotion."""
    base_rate = 1 + _number(cfg["tts"]["rate"], 100) / 100
    speed = float(cfg["render"].get("speed", 1.0))
    e_rate, e_pitch, e_volume = EMOTIONS.get(emotion or "neutral", (0, 0, 0))
    rate = base_rate * speed * (1 + _number(voice.get("rate"), 50) / 100) * (1 + e_rate / 100)
    pitch = _number(voice.get("pitch"), 50) + e_pitch
    volume = _number(cfg["tts"]["volume"], 100) + e_volume
    out = {"voice": voice["name"], "rate": f"{round((rate - 1) * 100):+d}%", "pitch": f"{pitch:+d}Hz",
           "volume": f"{max(-90, min(100, volume)):+d}%"}
    if voice.get("expressive") or (cfg["tts"].get("expressive") == "all" and _chatterbox()):  # rejouée avec l'émotion
        out["expressive"] = True
        out["emotion"] = emotion or "neutral"
    return out


def _chatterbox():
    """Chatterbox installé (.venv-tts) : sans lui, « toutes expressives » garde les voix de base."""
    from manhwa import chatterbox_tts

    return chatterbox_tts.available()


async def synthesize(text, path, params):
    from manhwa import kokoro_tts

    if params.get("expressive"):
        from manhwa import chatterbox_tts

        if chatterbox_tts.available():
            return await asyncio.to_thread(chatterbox_tts.synthesize, text, path, params)
    if kokoro_tts.is_kokoro(params["voice"]):  # voix locale : à côté, pour ne pas bloquer les autres
        return await asyncio.to_thread(kokoro_tts.synthesize, text, path, params)
    import edge_tts

    tmp = path.with_suffix(".part")
    await edge_tts.Communicate(text, params["voice"], rate=params["rate"], pitch=params["pitch"],
                               volume=params["volume"]).save(str(tmp))
    os.replace(tmp, path)  # jamais de fichier à moitié écrit pris pour un vrai


def sample(params, text):
    """Extrait à écouter dans le Studio (mis en cache)."""
    folder = CACHE / "samples"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{fingerprint(text, params)}.mp3"
    if not path.is_file():
        asyncio.run(synthesize(text, path, params))
    return path


def propose(chapter, cfg, progress=None):
    """GPT choisit une voix pour chaque personnage dont la voix n'est pas encore validée."""
    from manhwa.cast import load_cast, lines, save_cast, series_dir
    from manhwa.ingest.wiki import load_wiki
    from manhwa.tts import narrator_voice

    crew = load_cast(chapter)
    data = chapter.load()
    pages = {w["id"]: w for w in (load_wiki(series_dir(chapter)) or {}).get("characters", [])}
    said = {}
    for line in lines(data, crew):
        who = line["speaker"] or line["suggestion"]
        said.setdefault(who, []).append(line["text"])
    todo = [c for c in crew["characters"] if not c.get("voice_ok") and not c.get("silent")]
    if not todo:
        return 0
    people = []
    for i, c in enumerate(crew["characters"]):
        if c in todo:
            page = pages.get(c.get("wiki")) or {}
            people.append({"id": c["id"], "name": c["name"] or f"Perso {i + 1}", "gender": page.get("gender") or None,
                           "personality": (page.get("personality") or "")[:500] or None,
                           "lines": said.get(c["id"], [])[:6]})
    if progress:
        progress(0, 1)
    chosen = gpt_voices(people, list_voices(), narrator_voice(cfg, crew)["name"])
    crew = load_cast(chapter)  # relu : un nom a pu changer pendant l'appel
    for c in crew["characters"]:
        if c["id"] in chosen and not c.get("voice_ok"):
            c["voice"] = chosen[c["id"]]
    save_cast(chapter, crew)
    if progress:
        progress(1, 1)
    return len(chosen)
