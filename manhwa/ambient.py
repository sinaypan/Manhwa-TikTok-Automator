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
