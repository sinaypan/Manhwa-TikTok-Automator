"""Kokoro : un deuxième moteur de voix, local (Apache-2.0, ≈ 330 Mo, sur la carte graphique).

Une voix Kokoro s'écrit « kokoro:am_michael » dans characters.json ; elle se choisit dans la
même liste que les voix edge-tts (onglet Personnages). Kokoro ne règle pas la hauteur :
on la décale après coup (rééchantillonnage), en gardant la vitesse demandée.

Le texte en majuscules (« WHAT NOW? ») est remis en casse normale avant d'être lu, sinon
certains mots seraient épelés. La prononciation passe par phonemizer et espeak-ng
(licence GPL-3.0 : sans effet sur les vidéos, à savoir si le programme était distribué).
"""
import os
import re
import subprocess
import threading

import numpy as np

_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
MODELS = {
    "kokoro-v1.0.onnx": (f"{_RELEASE}/kokoro-v1.0.onnx",
                         "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a"),
    "kokoro-voices-v1.0.bin": (f"{_RELEASE}/voices-v1.0.bin",
                               "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
}
PREFIX = "kokoro:"
# les voix anglaises : a = américain, b = britannique ; f = femme, m = homme
VOICES = ["af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore", "af_nicole", "af_nova", "af_river",
          "af_sarah", "af_sky", "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx",
          "am_puck", "am_santa", "bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable",
          "bm_george", "bm_lewis"]
HZ_PER_SEMITONE = 10  # ≈ pour une voix parlée de 120 à 200 Hz
_ENGINE = {}
_LOCK = threading.Lock()


def available():
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return False
    return True


def catalog():
    """Les voix Kokoro au format de voices.list_voices()."""
    return [{"name": PREFIX + v, "gender": "Male" if v[1] == "m" else "Female",
             "locale": "en-US" if v[0] == "a" else "en-GB", "traits": "Kokoro (local)"} for v in VOICES]


def is_kokoro(name):
    return str(name or "").startswith(PREFIX)


def label(name):
    """« kokoro:am_michael » → « Michael (US, Kokoro) »."""
    v = name[len(PREFIX):]
    return f"{v[3:].capitalize()} ({'US' if v[0] == 'a' else 'UK'}, Kokoro)"


def _engine():
    if "k" not in _ENGINE:
        import onnxruntime as ort
        from kokoro_onnx import Kokoro

        from manhwa.faces import ensure_models, models_dir
        from manhwa.gpu import onnx_providers

        ensure_models(MODELS)
        folder = models_dir()
        sess = ort.InferenceSession(str(folder / "kokoro-v1.0.onnx"), providers=onnx_providers())
        _ENGINE["k"] = Kokoro.from_session(sess, str(folder / "kokoro-voices-v1.0.bin"))
    return _ENGINE["k"]


def readable(text):
    """« I DON'T THINK SO. YOU? » → « I don't think so. You? » (Kokoro épelle les mots en majuscules)."""
    letters = [c for c in text if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) < 0.6 * len(letters):
        return text
    out = re.sub(r"(^|[.!?…]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text.lower())
    return re.sub(r"\bi\b", "I", out)


def _number(value):
    m = re.search(r"[-+]?\d+", str(value or "0"))
    return int(m.group()) if m else 0


def synthesize(text, path, params):
    """Écrit la réplique en MP3 (même format que les voix edge-tts)."""
    import imageio_ffmpeg

    name = params["voice"][len(PREFIX):]
    speed = 1 + _number(params.get("rate")) / 100
    factor = 2 ** (_number(params.get("pitch")) / HZ_PER_SEMITONE / 12)  # > 1 : plus aigu
    with _LOCK:  # une seule synthèse à la fois sur la carte
        audio, rate = _engine().create(readable(text), voice=name, speed=float(np.clip(speed / factor, 0.5, 2.0)),
                                       lang="en-us" if name[0] == "a" else "en-gb")
    if abs(factor - 1) > 1e-3:  # rejouée plus vite (ou plus lentement) : plus aiguë (ou plus grave)
        n = max(1, int(len(audio) / factor))
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio)
    audio = np.clip(audio * (1 + _number(params.get("volume")) / 100), -1, 1)
    pcm = (audio * 32767).astype(np.int16).tobytes()
    tmp = path.with_suffix(".part.mp3")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "quiet", "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1",
                    "-i", "-", "-codec:a", "libmp3lame", "-b:a", "128k", str(tmp)], input=pcm, check=True)
    os.replace(tmp, path)
