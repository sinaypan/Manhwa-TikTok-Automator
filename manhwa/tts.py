"""Voix off edge-tts : chaque réplique lue avec la voix de son personnage.

Une frame a une liste de « segments » (frame["segments"]) : ses répliques dans l'ordre,
chacune avec son personnage, son émotion, ses réglages edge-tts et son fichier audio.
Le fichier est nommé d'après le texte et les réglages : une frame renumérotée, ou une
réplique inchangée, garde sa voix sans être refaite.

Qui parle : le personnage validé dans le Studio, sinon celui proposé ; le narrateur pour
la narration et quand personne n'est trouvé. Un personnage sans voix en reçoit une (voices.auto_voice).
"""
import asyncio

from manhwa.project import fingerprint


def narrator_voice(cfg, crew):
    return (crew.get("narrator") or {}).get("voice") or {"name": cfg["tts"]["voice"], "pitch": "+0Hz", "rate": "+0%"}


def voice_rate(cfg):
    """Vitesse edge-tts : le réglage `tts.rate` multiplié par `render.speed` (« +25% »…)."""
    from manhwa.voices import prosody

    return prosody(cfg, {"name": cfg["tts"]["voice"]})["rate"]


def audio_key(text, cfg, params=None):
    params = params or {"voice": cfg["tts"]["voice"], "rate": voice_rate(cfg), "volume": cfg["tts"]["volume"]}
    return fingerprint(text, params)


def ensure_voices(chapter, crew, cfg):
    """Donne une voix (automatique) aux personnages qui n'en ont pas. Renvoie True si changé."""
    from manhwa.cast import series_dir
    from manhwa.ingest.wiki import load_wiki
    from manhwa.voices import auto_voice, gender_of, list_voices

    missing = [c for c in crew["characters"] if not c.get("voice") and not c.get("silent")]
    if not missing:
        return False
    voices = list_voices()
    pages = {w["id"]: w for w in (load_wiki(series_dir(chapter)) or {}).get("characters", [])}
    used = {c["voice"]["name"] for c in crew["characters"] if c.get("voice")}
    narrator = narrator_voice(cfg, crew)["name"]
    for c in missing:
        c["voice"] = auto_voice(gender_of(pages.get(c.get("wiki"))), used, narrator, voices)
        used.add(c["voice"]["name"])
    return True


def plan(chapter, data, cfg, crew=None):
    """{fichier de frame: [segment]} : ce que chaque frame doit dire, et avec quelle voix."""
    from manhwa.cast import EXTRAS, NARRATOR, extra_voice, lines, load_cast
    from manhwa.voices import prosody

    crew = crew or load_cast(chapter)
    by_key = {l["key"]: l for l in lines(data, crew)}
    voices = {c["id"]: c.get("voice") for c in crew["characters"]}
    narrator = narrator_voice(cfg, crew)
    out = {}
    for frame in data["frames"]:
        segments = []
        for line in (by_key.get(f"{frame['file']}#{j}") for j in range(len(frame.get("bubbles") or []))):
            if not line:
                continue
            speaker = line["speaker"] or (NARRATOR if line["kind"] == "narration" else line["suggestion"]) or NARRATOR
            voice = voices.get(speaker) or (extra_voice(crew, speaker, cfg) if speaker in EXTRAS else narrator)
            emotion = line["emotion"]
            if line["kind"] == "thought" and emotion == "neutral":
                emotion = "thinking"
            params = prosody(cfg, voice, emotion)
            key = fingerprint(line["text"], params)
            segments.append({"text": line["text"], "speaker": speaker, "emotion": emotion, **params,
                             "audio_key": key, "audio": f"{chapter.audio_dir.name}/{key}.mp3"})
        out[frame["file"]] = segments
    return out


async def _run(chapter, todo, cfg, progress=None):
    from manhwa.voices import synthesize

    sem = asyncio.Semaphore(max(1, cfg["tts"]["concurrency"]))
    finished = [0]

    async def one(seg):
        path = chapter.root / seg["audio"]
        async with sem:
            try:
                await synthesize(seg["text"], path, seg)
                print(f"  [OK] {seg['voice']} {seg['emotion']} | {seg['text'][:50]}")
            except Exception as e:
                print(f"  [!] échec TTS ({e}) : {seg['text'][:40]}")
            finally:
                finished[0] += 1
                if progress:
                    progress(finished[0], len(todo))

    await asyncio.gather(*(one(s) for s in todo))


def run_tts(chapter, cfg, force=False, progress=None):
    from manhwa.cast import load_cast, save_cast

    crew = load_cast(chapter)
    if ensure_voices(chapter, crew, cfg):
        save_cast(chapter, crew)
    data = chapter.load()
    planned = plan(chapter, data, cfg, crew)
    todo = {}
    for frame in data["frames"]:
        frame.pop("audio", None)  # ancienne voix unique par frame
        frame.pop("audio_key", None)
        segments = planned.get(frame["file"], [])
        frame["segments"] = segments
        frame["text"] = " ".join(s["text"] for s in segments) or None
        for seg in segments:
            path = chapter.root / seg["audio"]
            if force or not path.is_file() or path.stat().st_size <= 100:
                todo[seg["audio_key"]] = seg
    chapter.save(data)
    if not todo:
        print("  Voix déjà à jour.")
        _remove_unused(chapter, data)
        return 0
    chapter.audio_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Génération de {len(todo)} répliques...")
    asyncio.run(_run(chapter, list(todo.values()), cfg, progress))
    _remove_unused(chapter, data)
    return len(todo)


def tts_up_to_date(chapter, data, cfg):
    """Toutes les répliques prévues ont leur fichier, avec les bons réglages."""
    planned = plan(chapter, data, cfg)
    for frame in data["frames"]:
        want = [s["audio_key"] for s in planned.get(frame["file"], [])]
        have = [s.get("audio_key") for s in frame.get("segments") or []]
        if want != have or not all((chapter.root / s["audio"]).is_file() for s in frame.get("segments") or []):
            return False
    return True


def _remove_unused(chapter, data):
    used = {chapter.root / s["audio"] for f in data["frames"] for s in f.get("segments") or []}
    if not chapter.audio_dir.is_dir():
        return
    for path in chapter.audio_dir.glob("*.mp3"):
        if path not in used:
            path.unlink()
