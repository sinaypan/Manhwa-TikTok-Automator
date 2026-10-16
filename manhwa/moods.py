"""Musique selon l'ambiance : calme, tension, combat, tristesse.

L'ambiance de chaque case vient de ce que montre l'image (scene.py : lame, coup, sang,
explosion…) et du ton des répliques (colère, peur, tristesse). Elle est lissée pour que la
musique ne change pas à chaque case (au moins MIN_SECTION secondes par ambiance ; sur le ch. 1 : combat au début et pendant
l'attaque des brigands, calme ailleurs) ; on passe
d'une ambiance à l'autre par un fondu enchaîné.

Les morceaux : le premier fichier de music/<ambiance>/ (tes musiques, libres de droits de
préférence pour TikTok), sinon une nappe générée (manhwa/ambient.py, sans droits).
Réglage : config.toml → [render] music_moods (false = un seul morceau, comme avant).
"""
from collections import Counter

from manhwa.config import ROOT

MOODS = ("calm", "tension", "combat", "sad")
LABELS = {"calm": "calme", "tension": "tension", "combat": "combat", "sad": "tristesse"}
FIGHT = ("slash", "punch", "impact", "explosion", "metal")
FIGHT_AT = 0.45        # l'image montre un combat à partir de cette probabilité
MIN_SECTION = 15.0     # secondes : une ambiance dure au moins ça
MUSIC_EXT = (".mp3", ".wav", ".ogg", ".m4a", ".flac")


def frame_mood(frame, scene):
    cats = ((scene or {}).get(frame["file"]) or {}).get("cats") or {}
    emotions = Counter(s.get("emotion") for s in frame.get("segments") or [])
    if max((cats.get(c, 0) for c in FIGHT), default=0) >= FIGHT_AT or emotions["angry"] + emotions["shouting"] >= 1:
        return "combat"
    if emotions["scared"] or cats.get("thunder", 0) >= FIGHT_AT:
        return "tension"
    if emotions["sad"] or emotions["pain"]:
        return "sad"
    return "calm"


def sections(moods, durations, min_section=MIN_SECTION):
    """[(ambiance, début, fin)] : les ambiances des cases, regroupées et lissées."""
    if not moods:
        return []
    out = []
    t = 0.0
    for m, d in zip(moods, durations):
        if out and out[-1][0] == m:
            out[-1][2] = t + d
        else:
            out.append([m, t, t + d])
        t += d
    changed = True
    while changed and len(out) > 1:  # une ambiance trop courte rejoint la plus longue de ses voisines
        changed = False
        for i, (m, a, b) in enumerate(out):
            if b - a >= min_section:
                continue
            left = out[i - 1] if i > 0 else None
            right = out[i + 1] if i + 1 < len(out) else None
            host = max((x for x in (left, right) if x), key=lambda x: x[2] - x[1])
            host[1], host[2] = min(host[1], a), max(host[2], b)
            del out[i]
            merged = []  # deux voisines de même ambiance ne font plus qu'une
            for s in out:
                if merged and merged[-1][0] == s[0]:
                    merged[-1][2] = s[2]
                else:
                    merged.append(s)
            out[:] = merged
            changed = True
            break
    return [tuple(s) for s in out]


def tracks():
    """{ambiance: fichier} : music/<ambiance>/ s'il y en a, sinon la nappe générée (mise en cache)."""
    from manhwa.ambient import write_mood

    out = {}
    for mood in MOODS:
        folder = ROOT / "music" / mood
        mine = sorted(p for p in folder.iterdir() if p.suffix.lower() in MUSIC_EXT) if folder.is_dir() else []
        if mine:
            out[mood] = str(mine[0])
            continue
        path = ROOT / ".cache" / "music" / f"{mood}.wav"
        if not path.is_file():
            write_mood(mood, path)
        out[mood] = str(path)
    return out


def plan(chapter, data, durations, files):
    """Les ambiances de la vidéo, case par case puis lissées : [(ambiance, début, fin)]."""
    from manhwa.scene import load_scene

    scene = load_scene(chapter)
    frames = {f["file"]: f for f in data["frames"]}
    return sections(smooth([frame_mood(frames[f], scene) for f in files]), durations)


def smooth(moods, window=7, need=2):
    """Une ambiance l'emporte quand au moins `need` des `window` cases autour la demandent.

    Les cases de combat arrivent souvent seules au milieu de cases calmes : c'est leur
    densité qui fait une scène de combat, pas une case isolée.
    """
    half = window // 2
    out = []
    for i in range(len(moods)):
        around = Counter(m for m in moods[max(0, i - half):i + half + 1] if m != "calm")
        best = max(("combat", "tension", "sad"), key=lambda m: (around[m], -("combat", "tension", "sad").index(m)))
        out.append(best if around[best] >= need else "calm")
    return out
