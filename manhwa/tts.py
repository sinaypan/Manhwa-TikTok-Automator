"""Voix off edge-tts : un fichier audio par frame qui a du texte."""
import asyncio
import os

from manhwa.project import fingerprint


def audio_key(text, cfg):
    t = cfg["tts"]
    return fingerprint(text, t["voice"], t["rate"], t["volume"])


async def _synthesize(text, path, cfg):
    import edge_tts

    t = cfg["tts"]
    tmp = path.with_suffix(".part")
    await edge_tts.Communicate(text, t["voice"], rate=t["rate"], volume=t["volume"]).save(str(tmp))
    os.replace(tmp, path)  # jamais de fichier à moitié écrit pris pour un vrai


async def _run(chapter, data, todo, cfg, progress=None):
    sem = asyncio.Semaphore(max(1, cfg["tts"]["concurrency"]))
    finished = [0]

    async def one(frame):
        # nommé d'après le texte et la voix : une frame renumérotée garde sa voix
        path = chapter.audio_dir / f"{audio_key(frame['text'], cfg)}.mp3"
        async with sem:
            try:
                await _synthesize(frame["text"], path, cfg)
            except Exception as e:
                print(f"  [!] {frame['file']} : échec TTS ({e})")
                return
            finally:
                finished[0] += 1
                if progress:
                    progress(finished[0], len(todo))
        frame["audio"] = f"{chapter.audio_dir.name}/{path.name}"
        frame["audio_key"] = audio_key(frame["text"], cfg)
        print(f"  [OK] {path.name} | {frame['text'][:50]}")

    await asyncio.gather(*(one(f) for f in todo))


def run_tts(chapter, cfg, force=False, progress=None):
    data = chapter.load()
    todo = []
    for frame in data["frames"]:
        if not frame.get("text"):
            frame.pop("audio", None)  # le texte a été retiré : plus de voix
            frame.pop("audio_key", None)
            continue
        audio_ok = frame.get("audio") and (chapter.root / frame["audio"]).is_file()
        if force or not audio_ok or frame.get("audio_key") != audio_key(frame["text"], cfg):
            todo.append(frame)

    if not todo:
        chapter.save(data)
        print("  Voix déjà à jour.")
        return 0

    chapter.audio_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Génération de {len(todo)} voix ({cfg['tts']['voice']})...")
    asyncio.run(_run(chapter, data, todo, cfg, progress))
    chapter.save(data)
    _remove_unused(chapter, data)
    return len(todo)


def _remove_unused(chapter, data):
    used = {chapter.root / f["audio"] for f in data["frames"] if f.get("audio")}
    for path in chapter.audio_dir.glob("*.mp3"):
        if path not in used:
            path.unlink()
