"""Une nappe d'ambiance générée (pas de droits) : musique de fond par défaut, à remplacer à volonté.

Quatre accords lents (la mineur, fa, do, sol), sons doux qui montent et descendent,
un peu d'écho ; la fin rejoint le début pour tourner en boucle sans coupure.
"""
import wave

import numpy as np

RATE = 44100
CHORDS = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (196.0, 261.63, 329.63), (196.0, 246.94, 293.66)]


def pad(seconds_per_chord=12.0, rate=RATE):
    n = int(seconds_per_chord * rate)
    t = np.arange(n) / rate
    left, right = [], []
    for chord in CHORDS:
        env = np.sin(np.pi * t / seconds_per_chord) ** 2  # chaque accord entre et sort en douceur
        l = np.zeros(n)
        r = np.zeros(n)
        for k, f in enumerate(chord):
            for detune, side in ((0.997, l), (1.003, r)):
                ff = f * detune
                tone = 0.6 * np.sin(2 * np.pi * ff * t) + 0.25 * np.sin(2 * np.pi * 2 * ff * t + k)
                side += tone * (0.8 + 0.2 * np.sin(2 * np.pi * 0.1 * t + k))
            low = np.sin(2 * np.pi * chord[0] / 2 * t)  # une basse très douce
            l += 0.35 * low
            r += 0.35 * low
        left.append(l * env)
        right.append(r * env)
    # les accords se chevauchent de moitié : pas de trou entre deux
    step = n // 2
    total = step * (len(CHORDS) * 2)
    out = np.zeros((total + n, 2))
    order = CHORDS * 2
    for i in range(len(order)):
        j = i % len(CHORDS)
        out[i * step:i * step + n, 0] += left[j]
        out[i * step:i * step + n, 1] += right[j]
    out[:n] += out[total:total + n]  # la queue rejoint le début : boucle sans coupure
    out = out[:total]
    echo = int(0.38 * rate)
    out[echo:] += 0.3 * out[:-echo]
    return 0.5 * out / (np.abs(out).max() + 1e-9)


def write_default(path):
    samples = pad()
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return path


# ---------- Une nappe par ambiance (moods.py) ----------

SAD_CHORDS = [(146.83, 174.61, 220.0), (116.54, 146.83, 174.61), (98.0, 116.54, 146.83), (110.0, 138.59, 164.81)]


def _drone(seconds, freqs, rate=RATE, wobble=0.07):
    t = np.arange(int(seconds * rate)) / rate
    out = np.zeros((len(t), 2))
    for k, f in enumerate(freqs):
        for side, detune in ((0, 0.998), (1, 1.002)):
            out[:, side] += np.sin(2 * np.pi * f * detune * t + k) * (0.7 + 0.3 * np.sin(2 * np.pi * wobble * t + k))
    return out, t


def _hit(rate, freq=58.0, length=0.45, decay=9.0):
    t = np.arange(int(length * rate)) / rate
    sweep = freq * (1 + 1.5 * np.exp(-t * 25))  # le « boum » descend un peu, comme un taiko
    return np.sin(2 * np.pi * np.cumsum(sweep) / rate) * np.exp(-t * decay)


def mood_pad(mood, rate=RATE):
    """Une boucle stéréo (≈ 48 s) pour l'ambiance : calm, sad, tension ou combat."""
    if mood == "sad":
        global CHORDS
        saved, CHORDS = CHORDS, SAD_CHORDS
        try:
            return 0.8 * pad(seconds_per_chord=12.0, rate=rate)
        finally:
            CHORDS = saved
    if mood in ("tension", "combat"):
        seconds = 48.0
        out, t = _drone(seconds, (73.42, 77.78, 146.83) if mood == "tension" else (73.42, 110.0, 146.83), rate)
        out *= 0.35 * (0.75 + 0.25 * np.sin(2 * np.pi * 0.5 * t))[:, None]  # le bourdon respire
        beat = 60 / (70 if mood == "tension" else 112)
        pattern = (1, 0, 0, 0) if mood == "tension" else (1, 0, 1, 1, 0, 1, 0, 0)
        hit = _hit(rate, 52.0 if mood == "tension" else 60.0)
        step = 0
        while step * beat < seconds - 0.5:
            if pattern[step % len(pattern)]:
                i = int(step * beat * rate)
                n = min(len(hit), len(out) - i)
                out[i:i + n] += (0.9 if step % len(pattern) == 0 else 0.6) * hit[:n, None]
            step += 1
        return 0.5 * out / (np.abs(out).max() + 1e-9)
    return pad(rate=rate)


def write_mood(mood, path):
    samples = mood_pad(mood)
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return path
