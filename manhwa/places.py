"""Les lieux de l'épisode : une ambiance de fond, et des voix qui sonnent dans le lieu.

Une vidéo où seules les voix et la musique s'entendent sonne vide : une prison, un marché et
une forêt y sonnent pareil, et les voix (enregistrées « à sec ») semblent collées sur l'image.

1. GPT lit l'épisode dans l'ordre (ce qui se passe dans chaque case, les répliques) et le coupe
   en lieux : « a dark wooden prison, indoors », sa taille (small, large, outdoor) et ce qu'on
   y entend (« quiet prison room tone, distant drips »).
2. CLAP (soundbank.py) choisit l'ambiance Sonniss la plus proche de ce qu'on y entend ; elle
   tourne en boucle sous la scène, très bas, en fondu d'un lieu à l'autre.
3. Les voix du lieu prennent un peu de chaleur (graves), perdent leurs aigus durs et résonnent
   comme le lieu : un peu dans une petite pièce, plus dans une grande salle, presque pas dehors.

Résultat dans <chapitre>/.studio/places.json. Réglé dans config.toml : [render] ambience, voice_space.
"""
import base64
import hashlib
import json
import os
import subprocess

import numpy as np

from manhwa.panels import STUDIO_DIR

SPACES = ("small", "large", "outdoor")
# la voix dans le lieu (filtres ffmpeg) : chaleur, moins d'aigus durs, compression douce, résonance
WARM = ("equalizer=f=170:t=q:w=1.1:g=2.5,equalizer=f=3200:t=q:w=1.4:g=-2.5,equalizer=f=9000:t=q:w=1:g=-1.5,"
        "acompressor=threshold=-20dB:ratio=2.5:attack=8:release=150:makeup=1.5")
ROOM = {"small": "aecho=0.85:0.5:23|41|59:0.22|0.14|0.08",
        "large": "aecho=0.8:0.55:47|89|137|191:0.26|0.19|0.13|0.08",
        "outdoor": "aecho=0.9:0.4:31:0.06"}


def places_path(chapter):
    return chapter.root / STUDIO_DIR / "places.json"


def load_places(chapter):
    try:
        return json.loads(places_path(chapter).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _key(data):
    return hashlib.sha1(json.dumps([f["file"] for f in data["frames"]]).encode()).hexdigest()[:12]


def run_places(chapter, cfg=None, progress=None):
    """GPT coupe l'épisode en lieux ; CLAP choisit leur ambiance. Gardé tant que les cases ne changent pas."""
    from manhwa import soundbank
    from manhwa.llm import chat
    from manhwa.review import effective, is_spoken
    from manhwa.scene import load_scene

    data = chapter.load()
    if not data["frames"]:
        return 0
    old = load_places(chapter)
    if old.get("key") == _key(data) and old.get("scenes"):
        return 0
    seen = load_scene(chapter)
    panels = [{"panel": i + 1, "shows": (seen.get(f["file"]) or {}).get("desc") or None,
               "lines": [b["text"] for b in effective(f) if is_spoken(b)][:3] or None}
              for i, f in enumerate(data["frames"])]
    rule = ("You split a manhwa episode into places, for its background ambience. Read the panels in order. A place "
            "lasts many panels: start a new one only when the story clearly moves to another location for a while "
            "(a new building, going outside, a long flashback), never for a close-up, a reaction or a single panel. "
            f"An episode of {len(panels)} panels has about {max(3, len(panels) // 15)} places. For each place give: "
            "from (first panel number), place (English, under 10 words), space (small: a room or cell; large: a hall, "
            "a cave, a temple; outdoor), hear (English, under 10 words: only the steady background you would hear "
            "there, like room tone, rain, a distant crowd, a fire, birds, water drips; never events like "
            "screams, glass breaking or footsteps; wind only for a really windy place: a storm, a mountain top, a "
            "desert). Cover every panel. Answer JSON: {\"places\": [{\"from\", "
            "\"place\", \"space\", \"hear\"}]}")
    answer = chat([{"role": "system", "content": rule},
                   {"role": "user", "content": json.dumps({"panels": panels}, ensure_ascii=False)}], max_tokens=4000)
    scenes = []
    for x in answer.get("places", []):
        try:
            start = max(1, min(len(panels), int(x.get("from"))))
        except (TypeError, ValueError):
            continue
        scenes.append({"from": start, "place": str(x.get("place") or "")[:80],
                       "space": x.get("space") if x.get("space") in SPACES else "small",
                       "hear": str(x.get("hear") or "")[:100]})
    scenes = sorted({s["from"]: s for s in scenes}.values(), key=lambda s: s["from"])
    if not scenes:
        return 0
    scenes[0]["from"] = 1
    if progress:
        progress(1, 2)
    pick_ambiences(scenes)
    path = places_path(chapter)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": _key(data), "scenes": scenes}, ensure_ascii=False), encoding="utf-8")
    if progress:
        progress(2, 2)
    return len(scenes)


def pick_ambiences(scenes):
    """L'ambiance de chaque lieu : la boucle la plus proche de ce qu'on y entend (CLAP)."""
    from manhwa import soundbank

    if not scenes or not soundbank.ambience_ready():
        return
    try:
        vecs = soundbank.embed_texts([f"{s['hear']}, ambience" for s in scenes])
        for s, v in zip(scenes, vecs):
            s["q"] = base64.b64encode(v.astype(np.float16).tobytes()).decode()
            s["ambience"] = soundbank.best_ambience(v)
    finally:
        soundbank.close()


def refresh_ambiences(chapter):
    """Les lieux gardés, leur ambiance rechoisie (la bibliothèque ou leur description a changé)."""
    places = load_places(chapter)
    if places.get("scenes"):
        pick_ambiences(places["scenes"])
        places_path(chapter).write_text(json.dumps(places, ensure_ascii=False), encoding="utf-8")
    return len(places.get("scenes") or [])


def frame_places(chapter, data):
    """Le lieu de chaque case (dans l'ordre), ou None si l'épisode n'a pas encore ses lieux."""
    scenes = load_places(chapter).get("scenes") or []
    if not scenes:
        return [None] * len(data["frames"])
    out, k = [], 0
    for i in range(len(data["frames"])):
        while k + 1 < len(scenes) and scenes[k + 1]["from"] <= i + 1:
            k += 1
        out.append(scenes[k])
    return out


def sections(places, durations):
    """[(ambiance, début, fin)] : les cases d'un même lieu ensemble, en secondes."""
    out, t = [], 0.0
    for place, d in zip(places, durations):
        amb = (place or {}).get("ambience")
        if out and out[-1][0] == amb:
            out[-1][2] = t + d
        else:
            out.append([amb, t, t + d])
        t += d
    return [tuple(s) for s in out if s[0]]


def voice_in_space(chapter, path, space):
    """La réplique (mp3) avec la chaleur et la résonance du lieu : un .wav gardé dans .studio/voicefx/."""
    import imageio_ffmpeg

    space = space if space in ROOM else "small"
    src = str(path)
    stat = os.stat(src)
    name = hashlib.sha1(f"{src}:{stat.st_size}:{stat.st_mtime_ns}:{space}:{WARM}:{ROOM[space]}".encode()).hexdigest()[:20]
    out = chapter.root / STUDIO_DIR / "voicefx" / f"{name}.wav"
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".part.wav")
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "quiet", "-y", "-i", src, "-af", f"{WARM},{ROOM[space]}",
                        "-ar", "44100", str(tmp)], check=True)
        os.replace(tmp, out)
    return out
