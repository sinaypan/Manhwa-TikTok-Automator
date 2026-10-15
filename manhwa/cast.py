"""Personnages d'une série et « qui parle » : ce que l'écran Personnages du Studio affiche et modifie.

    inbox/<série>/characters.json   les personnages de la série : {"id", "name", "cover"}
    project.json → "faces"          les visages du chapitre, chacun rangé dans un personnage
    .studio/faces/<id>.jpg          la vignette de chaque visage
    .studio/faces.npz               leur description (pour reconnaître les personnages ailleurs)
    frame → "speakers"              qui dit chaque réplique validée : {texte de la bulle: id}

Les noms sont donnés une fois par série : un personnage reconnu dans l'épisode suivant
garde son nom. Une réplique peut aussi être dite par le narrateur (NARRATOR).
"""
import json
import math
import os
from collections import Counter, defaultdict

import numpy as np

from manhwa.project import Chapter, is_chapter_dir

CAST_FILE = "characters.json"
FACES_DIR = "faces"
NARRATOR = "narrator"


# ---------- Personnages de la série ----------

def series_dir(chapter):
    return chapter.root.parent


def cast_path(chapter):
    return series_dir(chapter) / CAST_FILE


def load_cast(chapter):
    path = cast_path(chapter)
    cast = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    cast.setdefault("characters", [])
    cast.setdefault("next", 1)
    return cast


def save_cast(chapter, cast):
    path = cast_path(chapter)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cast, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def new_character(cast, cover=None):
    cid = f"c{cast['next']}"
    cast["next"] += 1
    cast["characters"].append({"id": cid, "name": "", "cover": cover})
    return cid


def character(cast, cid):
    return next((c for c in cast["characters"] if c["id"] == cid), None)


def series_chapters(chapter):
    folder = series_dir(chapter)
    return sorted((Chapter(p) for p in folder.iterdir() if p.is_dir() and is_chapter_dir(p)), key=lambda c: c.root.name)


def faces_dir(chapter):
    from manhwa.panels import STUDIO_DIR

    return chapter.root / STUDIO_DIR / FACES_DIR


def vectors_path(chapter):
    from manhwa.panels import STUDIO_DIR

    return chapter.root / STUDIO_DIR / "faces.npz"


def chapter_faces(data):
    return (data.get("faces") or {}).get("list", [])


def _load_vectors(chapter):
    path = vectors_path(chapter)
    if not path.is_file():
        return {}
    with np.load(path) as z:
        return dict(zip(z["ids"].tolist(), z["vecs"]))


def known_faces(chapter):
    """Ce que la série sait déjà : {personnage: centre}, et les formes écartées (pas des visages)."""
    sums, rejected = defaultdict(list), []
    for other in series_chapters(chapter):
        data = other.load()
        vecs = _load_vectors(other)
        for face in chapter_faces(data):
            v = vecs.get(face["id"])
            if v is None:
                continue
            if face.get("not_face"):
                rejected.append(v)
            elif face.get("char"):
                sums[face["char"]].append(v)
    centers = {}
    for cid, vs in sums.items():
        c = np.mean(vs, axis=0)
        centers[cid] = c / (np.linalg.norm(c) + 1e-9)
    return centers, rejected


def prune(chapter, cast):
    """Retire les personnages sans nom qui n'ont plus aucun visage ni réplique dans la série."""
    used = set()
    for other in series_chapters(chapter):
        data = other.load()
        used |= {f["char"] for f in chapter_faces(data) if f.get("char") and not f.get("not_face")}
        for frame in data["frames"]:
            used |= set((frame.get("speakers") or {}).values())
    cast["characters"] = [c for c in cast["characters"] if c["name"] or c["id"] in used]


def refresh_covers(chapter, data, cast):
    """Chaque personnage montre un de ses visages (le premier de cet épisode, sinon celui d'avant)."""
    here = chapter.root.name
    by_char = defaultdict(list)
    for f in chapter_faces(data):
        if f.get("char") and not f.get("not_face"):
            by_char[f["char"]].append(f["id"])
    for c in cast["characters"]:
        cover = c.get("cover")
        still = cover and (not cover.startswith(here + "/") or cover.split("/", 1)[1] in by_char.get(c["id"], []))
        if not still:
            c["cover"] = f"{here}/{by_char[c['id']][0]}" if by_char.get(c["id"]) else None


# ---------- Repérage ----------

def run_faces(chapter, cfg, force=False, progress=None):
    """Cherche les visages des frames du chapitre et les range par personnage."""
    import cv2

    from manhwa.faces import THUMB, assign, detect, embed, faces_key, head_box
    from manhwa.images import load_strip, write_jpeg
    from manhwa.panels import load_analysis

    data = chapter.load()
    frames = data["frames"]
    if not frames:
        print("  Aucune frame : crée d'abord la découpe.")
        return 0
    analysis = load_analysis(chapter, cfg, compute=False)
    key = faces_key(analysis, frames)
    if not force and (data.get("faces") or {}).get("key") == key:
        print("  Visages déjà à jour.")
        return 0

    known, rejected = known_faces(chapter)  # avant d'effacer : les visages déjà rangés servent de modèles
    strip, _ = load_strip(chapter.pages(), cfg["slicer"]["max_src_width"])
    folder = faces_dir(chapter)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.jpg"):
        old.unlink()

    faces, vecs = [], []
    for i, frame in enumerate(frames):
        x, y, w, h = frame["crop"]
        crop = strip[y:y + h, x:x + w]
        for box in detect(crop):
            hx, hy, hw, hh = head_box(box, w, h)
            head = crop[hy:hy + hh, hx:hx + hw]
            fid = f"f{len(faces) + 1:04d}"
            write_jpeg(folder / f"{fid}.jpg", cv2.resize(head, (THUMB, THUMB), interpolation=cv2.INTER_AREA), 88)
            faces.append({"id": fid, "frame": frame["file"], "box": box, "char": None})
            vecs.append(embed(head))
        if progress:
            progress(i + 1, len(frames))

    cast = load_cast(chapter)
    assign(faces, vecs, known, rejected, lambda: new_character(cast))
    tmp = vectors_path(chapter).with_suffix(".part.npz")
    np.savez(tmp, ids=np.array([f["id"] for f in faces]), vecs=np.stack(vecs) if vecs else np.zeros((0, 384), np.float32))
    os.replace(tmp, vectors_path(chapter))

    data = chapter.load()
    data["faces"] = {"key": key, "list": faces}
    chapter.save(data)
    refresh_covers(chapter, data, cast)
    prune(chapter, cast)
    save_cast(chapter, cast)
    print(f"  {len(faces)} visages, {len({f['char'] for f in faces if f['char']})} personnages.")
    return len(faces)


# ---------- Corrections ----------

def move_faces(chapter, data, cast, face_ids, target):
    """Range des visages : target = id de personnage, "new", "none" (autres visages) ou "not_face"."""
    if target == "new":
        target = new_character(cast)
    elif target not in ("none", "not_face") and not character(cast, target):
        raise ValueError("Personnage inconnu")
    ids = set(face_ids)
    for face in chapter_faces(data):
        if face["id"] in ids:
            face["not_face"] = target == "not_face"
            face["char"] = target if target not in ("none", "not_face") else None
    refresh_covers(chapter, data, cast)
    return target


def rename(cast, cid, name):
    c = character(cast, cid)
    if not c:
        raise ValueError("Personnage inconnu")
    c["name"] = " ".join(str(name).split())[:40]


# ---------- Qui parle ----------

def _center(box):
    return box[0] + box[2] / 2, box[1] + box[3] / 2


def _view(frame, bubble, faces):
    """Le morceau de la case à montrer : la bulle et les visages, sans dépasser 1,6 largeur."""
    _, _, w, h = frame["crop"]
    boxes = [bubble["box"]] + [f["box"] for f in faces]
    y0 = min(b[1] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    pad = 0.06 * w
    y0, y1 = y0 - pad, y1 + pad
    if y1 - y0 < 0.6 * w:  # pas trop étroit : on doit voir la scène
        mid = (y0 + y1) / 2
        y0, y1 = mid - 0.3 * w, mid + 0.3 * w
    if y1 - y0 > 1.6 * w:  # trop haut : centré sur la bulle
        mid = _center(bubble["box"])[1]
        y0, y1 = mid - 0.8 * w, mid + 0.8 * w
    height = min(h, y1 - y0)
    y0 = max(0, min(y0, h - height))
    return [0, round(y0), w, max(1, round(height))]


def lines(data, cast):
    """Les répliques du chapitre, chacune avec son personnage validé et les plus probables.

    Probable = un visage proche de la bulle dans la même case, sinon un personnage des
    cases voisines, sinon un personnage fréquent du chapitre.
    """
    ids = {c["id"] for c in cast["characters"]}
    faces = [f for f in chapter_faces(data) if f.get("char") in ids and not f.get("not_face")]
    by_frame = defaultdict(list)
    for f in faces:
        by_frame[f["frame"]].append(f)
    counts = Counter(f["char"] for f in faces)
    total = sum(counts.values()) or 1
    frames = data["frames"]
    out = []
    for i, frame in enumerate(frames):
        here = by_frame.get(frame["file"], [])
        speakers = frame.get("speakers") or {}
        for j, bubble in enumerate(frame.get("bubbles") or []):
            if bubble["kind"] != "dialogue":
                continue
            scores = defaultdict(float)
            bx, by = _center(bubble["box"])
            width = frame["crop"][2] or 1
            for f in here:
                fx, fy = _center(f["box"])
                d = math.hypot(fx - bx, fy - by) / width
                scores[f["char"]] = max(scores[f["char"]], 1 / (1 + 2 * d))
            for offset, weight in ((-1, 0.35), (1, 0.25), (-2, 0.2)):
                k = i + offset
                if 0 <= k < len(frames):
                    for f in by_frame.get(frames[k]["file"], []):
                        scores[f["char"]] = max(scores[f["char"]], weight)
            for cid, n in counts.items():
                scores[cid] = max(scores[cid], 0.1 * n / total)
            ranked = sorted(scores, key=lambda c: -scores[c])
            speaker = speakers.get(bubble["text"])
            if speaker not in ids and speaker != NARRATOR:
                speaker = None
            out.append({
                "key": f"{frame['file']}#{j}",
                "frame": frame["file"],
                "text": bubble["text"],
                "box": bubble["box"],
                "speaker": speaker,
                "suggestion": ranked[0] if ranked else None,
                "candidates": ranked[:4],
                "view": _view(frame, bubble, here),
                "faces": [{"id": f["id"], "box": f["box"], "char": f["char"]} for f in here],
            })
    return out


def set_speakers(data, choices):
    """choices : [{"key": "frame_0003.jpg#1", "char": id | "narrator" | None}]. Renvoie le nombre changé."""
    frames = {f["file"]: f for f in data["frames"]}
    changed = 0
    for choice in choices:
        file, _, index = str(choice["key"]).partition("#")
        frame = frames.get(file)
        bubbles = (frame or {}).get("bubbles") or []
        if not index.isdigit() or int(index) >= len(bubbles):
            continue
        text = bubbles[int(index)]["text"]
        speakers = frame.setdefault("speakers", {})
        if choice.get("char"):
            speakers[text] = choice["char"]
        else:
            speakers.pop(text, None)
        changed += 1
    return changed
