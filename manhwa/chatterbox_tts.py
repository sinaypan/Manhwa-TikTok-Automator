"""Voix expressives : Chatterbox (Resemble AI, MIT), en local, dans un environnement à part.

On coche « Expressive » sur la voix d'un personnage (onglet Personnages) : il garde le
timbre de sa voix (edge-tts ou Kokoro), et Chatterbox la rejoue avec l'émotion de chaque
réplique (plus d'intensité pour la colère ou un cri, moins pour la tristesse).
Mesuré : ≈ 2,6 s par réplique sur la RTX 3050 (3,4 Go de mémoire), comprise par Whisper
sans erreur sur les essais. Chatterbox ajoute un filigrane audio inaudible (Perth).

Installation (≈ 4 Go, une fois) :
    uv venv --python 3.12 .venv-tts
    uv pip install --python .venv-tts/Scripts/python.exe torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
    uv pip install --python .venv-tts/Scripts/python.exe chatterbox-tts==0.1.7
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import threading

from manhwa.config import ROOT

REF_TEXT = ("I have walked this road for a long time, and I am not done yet. "
            "Every step I take brings me closer to the truth, whatever it costs me.")
# l'intensité (exaggeration) selon le ton ; 0,5 = normal
INTENSITY = {"neutral": 0.5, "calm": 0.4, "happy": 0.6, "excited": 0.75, "mocking": 0.6, "angry": 0.85,
             "shouting": 0.95, "cold": 0.4, "sad": 0.35, "scared": 0.7, "surprised": 0.7, "pain": 0.75,
             "whisper": 0.3, "thinking": 0.35}
_WORKER = {}
_LOCK = threading.Lock()


def python():
    folder = ROOT / ".venv-tts"
    exe = folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return exe if exe.is_file() else None


def available():
    return python() is not None


def _number(value):
    m = re.search(r"[-+]?\d+", str(value or "0"))
    return int(m.group()) if m else 0


def reference(params):
    """La voix de base qui dit une phrase neutre (≈ 10 s) : son timbre sert de modèle."""
    from manhwa.project import fingerprint
    from manhwa.voices import synthesize

    base = {"voice": params["voice"], "rate": "+0%", "pitch": params.get("pitch") or "+0Hz", "volume": "+0%"}
    folder = ROOT / ".cache" / "voices_ref"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{fingerprint(REF_TEXT, base)}.mp3"
    if not path.is_file():
        asyncio.run(synthesize(REF_TEXT, path, base))
    return path


def _worker():
    w = _WORKER.get("p")
    if w and w.poll() is None:
        return w
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chatterbox_worker.py")
    p = subprocess.Popen([str(python()), "-u", worker], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8", cwd=str(ROOT))
    if not _answer(p).get("ready"):
        p.kill()
        raise RuntimeError("Chatterbox n'a pas démarré (environnement .venv-tts ?)")
    _WORKER["p"] = p
    return p


def _answer(p):
    """La prochaine réponse JSON du programme (Chatterbox écrit aussi ses propres messages)."""
    for line in p.stdout:
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"error": "Chatterbox s'est arrêté"}


def close():
    """Arrête Chatterbox : la carte graphique est libérée pour les autres modèles."""
    p = _WORKER.pop("p", None)
    if p and p.poll() is None:
        try:
            p.stdin.close()
            p.wait(timeout=20)
        except Exception:
            p.kill()


def synthesize(text, path, params):
    """Écrit la réplique en MP3, avec la vitesse et le volume demandés."""
    import imageio_ffmpeg

    ref = reference(params)
    raw = str(path) + ".cb.wav"
    job = {"text": text, "ref": str(ref), "exaggeration": INTENSITY.get(params.get("emotion") or "neutral", 0.5),
           "cfg": 0.5, "out": raw}
    with _LOCK:
        p = _worker()
        p.stdin.write(json.dumps(job) + "\n")
        p.stdin.flush()
        answer = _answer(p)
    if "error" in answer:
        raise RuntimeError(answer["error"])
    speed = max(0.5, min(2.0, 1 + _number(params.get("rate")) / 100))
    gain = 1 + _number(params.get("volume")) / 100
    tmp = path.with_suffix(".part.mp3")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "quiet", "-y", "-i", raw, "-filter:a",
                    f"atempo={speed:.3f},volume={gain:.3f}", "-codec:a", "libmp3lame", "-b:a", "128k", str(tmp)], check=True)
    os.replace(tmp, path)
    os.remove(raw)


if __name__ == "__main__":  # essai : python -m manhwa.chatterbox_tts "texte"
    from pathlib import Path

    out = Path(sys.argv[2] if len(sys.argv) > 2 else "essai.mp3")
    synthesize(sys.argv[1], out, {"voice": "en-US-AndrewNeural", "rate": "+25%", "emotion": "angry"})
    close()
    print(out)
