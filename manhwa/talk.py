"""Les visages qui parlent : la bouche de celui qui parle bat au rythme de sa voix, les yeux clignent.

Comme dans un animé : pour chaque visage qui parle, FLUX.2 [klein] 4B (Apache 2.0, edit_worker.py)
redessine dans le style de la case trois bouches (fermée, entrouverte, ouverte) et les yeux fermés.
Au rendu, la vidéo passe d'un dessin à l'autre, 12 fois par seconde au plus :
    bouche   ouverte au cœur de chaque syllabe, fermée entre deux et dans les silences
    yeux     fermés le temps d'un clignement (0,25 s), toutes les 3 à 5 s

Où sont la bouche et les yeux : là où le modèle a changé l'image (la bouche redessinée diffère de
l'originale là où est la bouche) ; seules ces zones sont collées, en fondu, sur la case d'origine.

Gardé dans <chapitre>/.studio/face_parts.json (dessins et zones dans .studio/talk/) :
    {visage: {"key", "box": [x, y, côté] (le carré redessiné, repère de la case), "states": {état: png},
              "mouth": png de la zone, "eyes": png, "seed", "ok": true | false | absent}}
(visage : l'identifiant de faces.json, qui dit à quel personnage il est). « ok » : false, refusé dans le
Studio (pas animé) ; true, validé ; absent, pas encore regardé (animé quand même).
"""
import json
import os
import subprocess

import numpy as np

from manhwa.config import ROOT
from manhwa.panels import STUDIO_DIR
from manhwa.project import fingerprint

ENV_FPS = 60     # précision du suivi de la voix
BLINK = 0.25     # s : durée d'un clignement
BLINK_EVERY = (3.0, 5.0)
FLAP = 12        # comme un animé : 12 changements par seconde au plus, pas un mouvement continu
MOUTHS = (0.0, 0.55, 1.0)  # trois bouches : fermée, entrouverte, ouverte
SYLLABLE = 9     # ±0,15 s autour de l'instant : assez pour voir où on en est dans la syllabe
MIN_FACE = 100   # px dans la case : en dessous, la bouche est trop petite pour qu'on la voie bouger
EDIT_SIDE = 640  # le carré redessiné (multiple de 16) : 9 s par dessin ; à 768, 17 s et la carte de 6 Go déborde
SMALL_SIDE = 512  # un visage de moins de 560 px à l'écran : 6,6 s par dessin, la bouche aussi nette
SCREEN_W = 1080
TALK_VERSION = 1  # à incrémenter quand les dessins changent : ils sont refaits

STATES = {
    "mouth_closed": "Close the character's mouth, lips gently closed. Change only the mouth. "
                    "Keep the face, eyes, hair, lighting and the manhwa art style exactly the same.",
    "mouth_half": "Make the character's mouth slightly open, as if in the middle of saying a word. Change only the mouth. "
                  "Keep the face, eyes, hair, lighting and the manhwa art style exactly the same.",
    "mouth_open": "Open the character's mouth wide, as if talking loudly. Change only the mouth. "
                  "Keep the face, eyes, hair, lighting and the manhwa art style exactly the same.",
    "eyes_closed": "Close the character's eyes, as in the middle of a blink. Change only the eyes. "
                   "Keep the face, mouth, hair, lighting and the manhwa art style exactly the same.",
}
DRAWN_MOUTHS = ("mouth_closed", "mouth_half", "mouth_open")  # pour MOUTHS = 0, 0,55, 1


# ---------- La voix : quand la bouche s'ouvre ----------
def envelope(audio, duration):
    """Le volume (0 → 1) au fil d'une réplique, ENV_FPS valeurs par seconde."""
    try:
        sound = audio.to_soundarray()  # à sa fréquence : to_soundarray(fps=…) rend du silence (moviepy 2)
        rate = int(audio.fps)
    except Exception:
        return np.zeros(max(1, int(duration * ENV_FPS)), np.float32)
    mono = np.abs(sound.mean(axis=1) if sound.ndim > 1 else sound).astype(np.float32)
    hop = rate // ENV_FPS
    n = len(mono) // hop
    if not n:
        return np.zeros(1, np.float32)
    rms = np.sqrt((mono[:n * hop].reshape(n, hop) ** 2).mean(axis=1))
    loud = np.percentile(rms, 90) or 1.0
    raw = np.clip((rms / loud - 0.12) / 0.88, 0, 1) ** 0.7
    out, v = np.zeros_like(raw), 0.0
    for i, x in enumerate(raw):  # s'ouvre vite, se referme un peu moins vite (comme une vraie bouche)
        v += (x - v) * (0.85 if x > v else 0.45)
        out[i] = v
    return out


def _step(x, levels, cuts):
    """La valeur ramenée à l'une des positions dessinées (levels), selon les seuils (cuts)."""
    return levels[sum(x >= c for c in cuts)]


def syllable(env, i):
    """La bouche (une de MOUTHS) à l'instant i de la réplique : elle s'ouvre et se ferme à chaque syllabe.

    Comparée au volume juste avant et juste après, pas au volume de toute la réplique : une voix forte
    et régulière fait quand même battre la bouche, ouverte au cœur de la syllabe, fermée entre deux.
    """
    a = float(env[i])
    if a < 0.12:  # silence ou fin de mot
        return MOUTHS[0]
    near = env[max(0, i - SYLLABLE):i + SYLLABLE + 1]
    low, high = float(near.min()), float(near.max())
    local = (a - low) / (high - low) if high - low > 0.08 else 0.6
    pose = _step(local, MOUTHS, (0.3, 0.72))
    return MOUTHS[1] if pose == MOUTHS[2] and high < 0.45 else pose  # voix basse : pas grande ouverte


def blink_at(t, seed=0):
    """Les yeux fermés au temps t ? Un clignement toutes les 3 à 5 s."""
    rng = np.random.default_rng(seed)
    start = rng.uniform(0.6, 1.6)
    while start <= t:
        if t - start < BLINK:
            return True
        start += rng.uniform(*BLINK_EVERY)
    return False


# ---------- Les visages qui parlent, leurs dessins et leurs zones ----------
def parts_path(chapter):
    return chapter.root / STUDIO_DIR / "face_parts.json"


def talk_dir(chapter):
    return chapter.root / STUDIO_DIR / "talk"


def load_parts(chapter):
    path = parts_path(chapter)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save_parts(chapter, parts):
    path = parts_path(chapter)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part.json")
    tmp.write_text(json.dumps(parts, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def talkers(data):
    """Les visages qui parlent : dans chaque case, le plus grand visage de chaque personnage qui y parle."""
    frames = {f["file"]: f for f in data["frames"]}
    best = {}
    for f in (data.get("faces") or {}).get("list") or []:
        frame = frames.get(f["frame"])
        if not frame or f.get("not_face") or not f.get("char") or min(f["box"][2:]) < MIN_FACE:
            continue
        if f["char"] not in {s.get("speaker") for s in frame.get("segments") or []}:
            continue
        k = (f["frame"], f["char"])
        if k not in best or f["box"][2] * f["box"][3] > best[k]["box"][2] * best[k]["box"][3]:
            best[k] = f
    return list(best.values())


def square(face, crop_w, crop_h):
    """Le carré redessiné autour d'un visage (repère de la case) : [x, y, côté]."""
    bx, by, bw, bh = face["box"]
    side = min(int(1.6 * max(bw, bh)), crop_w, crop_h)
    cx, cy = bx + bw / 2, by + bh * 0.55  # un peu sous le centre : la bouche et le menton dedans
    x0 = int(min(max(0, cx - side / 2), crop_w - side))
    y0 = int(min(max(0, cy - side / 2), crop_h - side))
    return [x0, y0, side]


def edit_side(side, crop_w):
    """La taille du dessin : celle du visage à l'écran (case en pleine largeur), 512 ou 640 px."""
    return SMALL_SIDE if side * SCREEN_W / max(1, crop_w) <= 560 else EDIT_SIDE


def _blob(binary, keep):
    """Les plus grandes taches d'une image binaire (keep : combien), en masque 0/1."""
    import cv2

    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary.astype(np.uint8), 8)
    order = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])[:keep]
    return np.isin(labels, order) if order else np.zeros_like(binary, bool)


def zones(original, drawn):
    """Où sont la bouche et les yeux : là où les dessins diffèrent de l'original. → (bouche, yeux) en 0 → 255.

    Le modèle retouche un peu tout le carré (de 5 à 15 niveaux) : seules les fortes différences comptent.
    La bouche : la plus grande tache des trois bouches ; les yeux : les deux plus grandes taches des yeux
    fermés au-dessus de la bouche (dessiner une bouche grande ouverte fait parfois lever les sourcils).
    """
    import cv2

    side = original.shape[0]
    soft = lambda im: cv2.GaussianBlur(im, (0, 0), 1.5).astype(np.int16)
    base = soft(original)
    diff = lambda im: np.abs(soft(im) - base).max(axis=2)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, side // 40),) * 2)

    def strong(d):
        b = cv2.morphologyEx((d > 40).astype(np.uint8), cv2.MORPH_CLOSE, k)
        return cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))

    mouth = None
    mouths = [drawn[s] for s in DRAWN_MOUTHS if s in drawn]
    if mouths:
        m = _blob(strong(np.max([diff(im) for im in mouths], axis=0)), 1)
        if m.sum() > (side / 40) ** 2:
            mouth = m
    eyes = None
    if "eyes_closed" in drawn:
        e = strong(diff(drawn["eyes_closed"])).astype(bool)
        if mouth is not None:
            ys = np.nonzero(mouth)[0]
            e[int(ys.min() - side * 0.02):] = False  # rien sous le haut de la bouche
        e = _blob(e, 2)
        if e.sum() > (side / 60) ** 2:
            eyes = e

    def feather(mask, grow):
        if mask is None:
            return None
        m = cv2.dilate(mask.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow, grow)))
        return cv2.GaussianBlur(m, (0, 0), grow / 3)

    return feather(mouth, max(5, side // 26)), feather(eyes, max(5, side // 24))


def _key(face, frame, seed):
    return fingerprint(TALK_VERSION, face["frame"], face["box"], frame["crop"], seed, STATES)


def edit_python():
    exe = ROOT / ".venv-edit" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return exe if exe.is_file() else None


def run_talk(chapter, cfg=None, progress=None, only=None):
    """Les dessins des visages qui parlent (only : un seul visage à refaire, avec une autre graine)."""
    import cv2

    from manhwa.config import load_config
    from manhwa.images import load_strip, read_image

    cfg = cfg or load_config()
    if edit_python() is None:
        print("  Visages qui parlent : FLUX.2 [klein] absent (.venv-edit, voir manhwa/edit_worker.py)")
        return False
    data = chapter.load()
    frames = {f["file"]: f for f in data["frames"]}
    parts = load_parts(chapter)
    wanted = talkers(data)
    keep = {f["id"] for f in wanted}
    folder = talk_dir(chapter)
    folder.mkdir(parents=True, exist_ok=True)
    for fid in [k for k in parts if k not in keep]:  # visages disparus (découpe refaite)
        parts.pop(fid)
    todo = []
    for f in wanted:
        old = parts.get(f["id"]) or {}
        seed = int(old.get("seed", 1)) + (1 if only == f["id"] else 0)
        key = _key(f, frames[f["frame"]], seed)
        if (only and f["id"] != only) or (not only and old.get("key") == key):
            continue
        todo.append((f, seed, key))
    print(f"  Visages qui parlent : {len(wanted)}, {len(todo)} à dessiner")
    if not todo:
        save_parts(chapter, parts)
        return False

    strip, _ = load_strip(chapter.pages(), cfg["slicer"]["max_src_width"])
    jobs, boxes, kept = [], {}, 0
    for f, seed, key in todo:
        x, y, w, h = frames[f["frame"]]["crop"]
        crop = strip[y:y + h, x:x + w]
        x0, y0, side = boxes[f["id"]] = square(f, w, h)
        edit = edit_side(side, w)
        patch = cv2.resize(crop[y0:y0 + side, x0:x0 + side], (edit, edit),
                           interpolation=cv2.INTER_AREA if side > edit else cv2.INTER_CUBIC)
        src = folder / f"{f['id']}.png"
        png = cv2.imencode(".png", patch)[1].tobytes()
        if not src.is_file() or src.read_bytes() != png:  # inchangé : les dessins déjà faits restent bons
            src.write_bytes(png)
        stamp = folder / f"{f['id']}.seed"
        if stamp.is_file() and stamp.read_text() != str(seed):  # une autre graine : tout est à redessiner
            for state in STATES:
                (folder / f"{f['id']}_{state}.png").unlink(missing_ok=True)
        stamp.write_text(str(seed))
        for state, prompt in STATES.items():
            out = folder / f"{f['id']}_{state}.png"
            if out.is_file() and out.stat().st_mtime >= src.stat().st_mtime:
                kept += 1  # déjà dessiné (une étape interrompue reprend là où elle s'était arrêtée)
                continue
            jobs.append({"image": str(src), "prompt": prompt, "out": str(out), "seed": seed})
    if kept:
        print(f"  {kept} dessins déjà faits, gardés")
    done, failed, spent = 0, set(), []
    if jobs:
        job_file = folder / "jobs.json"
        job_file.write_text(json.dumps(jobs), encoding="utf-8")
        worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edit_worker.py")
        from manhwa.gpu import release_models

        release_models()  # FLUX prend presque toute la carte
        proc = subprocess.Popen([str(edit_python()), "-u", worker, str(job_file)], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "ok" in msg or "error" in msg:
                done += 1
                spent.append(msg.get("s") or 0)
                if "error" in msg:
                    failed.add(msg["out"])
                if progress:
                    progress(done, len(jobs))
        if proc.wait() != 0 and done < len(jobs):
            raise RuntimeError("FLUX.2 [klein] s'est arrêté (mémoire de la carte ?) : relance, les dessins faits sont gardés")
        print(f"  {done} dessins, {sum(spent) / max(1, len(spent)):.0f} s chacun")

    for f, seed, key in todo:
        fid = f["id"]
        original = read_image(folder / f"{fid}.png")
        drawn = {s: read_image(folder / f"{fid}_{s}.png") for s in STATES
                 if str(folder / f"{fid}_{s}.png") not in failed}
        drawn = {s: im for s, im in drawn.items() if im is not None}
        mouth, eyes = zones(original, drawn)
        entry = {"key": key, "seed": seed, "frame": f["frame"], "char": f["char"], "box": boxes[fid],
                 "states": {s: f"talk/{fid}_{s}.png" for s in drawn}}
        for name, mask in (("mouth", mouth), ("eyes", eyes)):
            if mask is not None:
                cv2.imwrite(str(folder / f"{fid}_{name}.png"), mask)
                entry[name] = f"talk/{fid}_{name}.png"
        parts[fid] = entry  # redessiné : à regarder de nouveau
    save_parts(chapter, parts)
    print(f"  Visages qui parlent : {len(todo)} dessinés"
          f" ({sum('mouth' in parts[f['id']] for f, _, _ in todo)} bouches trouvées)")
    return True


# ---------- Au rendu ----------
def _layer(path, size, crop, mask=None):
    import cv2

    from manhwa.images import read_image

    img = read_image(path)
    if img is None:
        return None
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    img = img if mask else cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img[:crop[1], :crop[0]].astype(np.float32)
    return img[..., :1] / 255 if mask else img


def drawn_layers(chapter, image, scale, offset, part):
    """Les dessins d'un visage, à la place et à la taille de l'image : (x, y, {état: dessin}, bouche, yeux)."""
    x0, y0, side = part["box"]
    ox, oy = offset
    px, py = int(round(ox + x0 * scale)), int(round(oy + y0 * scale))
    size = int(round(side * scale))
    h, w = image.shape[:2]
    crop = (min(w, px + size) - px, min(h, py + size) - py)
    if crop[0] < 8 or crop[1] < 8 or px < 0 or py < 0:
        return None
    base = chapter.root / STUDIO_DIR
    states = {s: _layer(base / p, size, crop) for s, p in part["states"].items()}
    mouth = _layer(base / part["mouth"], size, crop, mask=True) if part.get("mouth") else None
    eyes = _layer(base / part["eyes"], size, crop, mask=True) if part.get("eyes") else None
    return px, py, {s: im for s, im in states.items() if im is not None}, mouth, eyes


def _paste(img, px, py, drawn, mask):
    h, w = drawn.shape[:2]
    roi = img[py:py + h, px:px + w].astype(np.float32)
    img[py:py + h, px:px + w] = (roi * (1 - mask) + drawn * mask).astype(img.dtype)


def animator(chapter, image, scale, offset, faces, parts, lines, seed=0):
    """image(t) d'une case, avec les visages qui parlent ; None si aucun visage n'est dessiné.

    scale, offset : du repère de la case à celui de l'image (image = case × scale + offset) ;
    faces : les visages de la case (faces.json) ; lines : [(personnage, début, enveloppe)].
    """
    placed = []
    for f in faces:
        p = parts.get(f["id"])
        if not p or p.get("ok") is False or not (p.get("mouth") or p.get("eyes")) or "box" not in p:
            continue
        layers = drawn_layers(chapter, image, scale, offset, p)
        if layers:
            said = [(start, env) for who, start, env in lines if who == f.get("char")]
            placed.append((layers, said))
    if not placed:
        return None

    cache = {}

    def at(t):
        t = int(float(t) * FLAP) / FLAP  # la pose tient 2 images (24 i/s), comme un animé
        pose = []
        for k, (layers, said) in enumerate(placed):
            mouth = MOUTHS[0]
            for start, env in said:
                i = int((t - start) * ENV_FPS)
                if 0 <= i < len(env):
                    mouth = max(mouth, syllable(env, i))
            pose.append((DRAWN_MOUTHS[MOUTHS.index(mouth)], blink_at(t, seed + k)))
        pose = tuple(pose)
        if pose not in cache:  # peu de poses différentes : chacune n'est faite qu'une fois
            img = image.copy()
            for (px, py, states, mouth_zone, eyes_zone), (mouth, closed) in zip((l for l, _ in placed), pose):
                if mouth_zone is not None and mouth in states:
                    _paste(img, px, py, states[mouth], mouth_zone)
                if closed and eyes_zone is not None and "eyes_closed" in states:
                    _paste(img, px, py, states["eyes_closed"], eyes_zone)
            cache[pose] = img
        return cache[pose]

    return at


# ---------- Pour le Studio : regarder chaque visage, le valider ou le refuser ----------
def detail(chapter, data=None):
    """Les visages dessinés, dans l'ordre de l'épisode, pour l'onglet Personnages."""
    data = data or chapter.load()
    index = {f["file"]: i for i, f in enumerate(data["frames"])}
    parts = load_parts(chapter)
    faces = [{"id": fid, "frame": p.get("frame"), "case": index.get(p.get("frame"), -1) + 1, "char": p.get("char"),
              "ok": p.get("ok"), "mouth": bool(p.get("mouth")), "eyes": bool(p.get("eyes")), "v": (p.get("key") or "")[:8]}
             for fid, p in parts.items() if p.get("states")]
    faces.sort(key=lambda f: (f["case"], f["id"]))
    return {"available": edit_python() is not None, "faces": faces, "talkers": len(talkers(data))}


def preview(chapter, fid, state, side=320):
    """Le visage tel qu'il sera dans la vidéo : l'original, la bouche (ou les yeux) dessinée collée dessus."""
    import cv2

    from manhwa.images import read_image

    p = load_parts(chapter).get(fid)
    if not p or state not in STATES:
        return None
    base = chapter.root / STUDIO_DIR
    img = read_image(talk_dir(chapter) / f"{fid}.png")
    if img is None:
        return None
    img = img.astype(np.float32)
    steps = [("mouth_closed", "mouth"), ("eyes_closed", "eyes")] if state == "eyes_closed" else [(state, "mouth")]
    for s, zone in steps:
        drawn = read_image(base / p["states"][s]) if s in p["states"] else None
        mask = read_image(base / p[zone]) if p.get(zone) else None
        if drawn is not None and mask is not None:
            m = mask[..., :1].astype(np.float32) / 255
            img = img * (1 - m) + drawn.astype(np.float32) * m
    return cv2.resize(img.astype(np.uint8), (side, side), interpolation=cv2.INTER_AREA)


def set_ok(chapter, fid, ok):
    """Validé (True), refusé : pas animé (False), ou de nouveau à regarder (None)."""
    parts = load_parts(chapter)
    if fid not in parts:
        raise ValueError("Visage inconnu")
    if ok is None:
        parts[fid].pop("ok", None)
    else:
        parts[fid]["ok"] = bool(ok)
    save_parts(chapter, parts)
