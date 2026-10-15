"""Outils images partagés : tri naturel, lecture/écriture, strip, format 9:16."""
import re
from pathlib import Path

import cv2
import numpy as np

SUPPORTED = (".jpg", ".jpeg", ".png", ".webp")
BG_MODES = ("auto", "blur", "black", "gray")
SOLID_MARGIN = 0.07  # fond uni : marge de chaque côté (7 % de la largeur de la frame)


def natural_key(name):
    """Clé de tri qui range "2.jpg" avant "10.jpg" (et "99" avant "100")."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def list_images(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED]
    return sorted(files, key=lambda p: natural_key(p.name))


def read_image(path):
    """cv2.imread ne gère pas les chemins avec accents sous Windows : on passe par imdecode."""
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def write_jpeg(path, img, quality=92):
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise OSError(f"Encodage JPEG impossible : {path}")
    buf.tofile(str(path))


def dominant_width(sizes):
    """Largeur des vraies pages : celle qui couvre le plus de hauteur au total.

    `sizes` = [(largeur, hauteur)]. Les bannières et vignettes sont rares et courtes,
    elles ne l'emportent jamais sur les pages du chapitre.
    """
    totals = {}
    for w, h in sizes:
        totals[w] = totals.get(w, 0) + h
    return max(totals, key=totals.get) if totals else None


def load_strip(files, max_width):
    """Empile les pages en un seul long strip, toutes à la même largeur.

    Renvoie (strip, fichiers_utilisés) ou (None, []) si aucune image n'est lisible.
    Déterministe : mêmes fichiers + même max_width = même strip (l'OCR en dépend).
    """
    imgs, used = [], []
    for f in files:
        im = read_image(f)
        if im is None:
            print(f"[!] Image illisible ignorée : {Path(f).name}")
            continue
        imgs.append(im)
        used.append(Path(f))
    if not imgs:
        return None, []

    # largeur des vraies pages (et non la plus petite image, qui rendait tout flou)
    target_w = min(dominant_width([(im.shape[1], im.shape[0]) for im in imgs]), max_width)
    resized = []
    for im in imgs:
        h, w = im.shape[:2]
        if w != target_w:
            im = cv2.resize(im, (target_w, int(h * target_w / w)), interpolation=cv2.INTER_AREA)
        resized.append(im)
    return cv2.vconcat(resized), used


def make_background(frame, mode, blur_ksize=61):
    if mode == "black":
        return np.zeros_like(frame)
    if mode == "gray":
        return np.full_like(frame, 40)
    k = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1
    return cv2.GaussianBlur(frame, (k, k), 0)


def border_color(crop, band=3, tol=24, share=0.75):
    """Couleur du fond autour de la case si son bord est uni (blanc, noir…), sinon None.

    Le crop est déjà rogné au plus près du contenu : une case de texte touche ses bords
    par endroits. On regarde donc si la plupart des pixels du bord (75 %) ont la même
    couleur, pas tous.
    """
    h, w = crop.shape[:2]
    b = max(1, min(band, h // 4, w // 4))
    edge = np.concatenate([
        crop[:b].reshape(-1, 3), crop[-b:].reshape(-1, 3),
        crop[:, :b].reshape(-1, 3), crop[:, -b:].reshape(-1, 3),
    ]).astype(np.int16)
    median = np.median(edge, axis=0)
    close = (np.abs(edge - median).max(axis=1) <= tol).mean()
    return tuple(int(v) for v in median) if close >= share else None


def letterbox(crop, out_w, out_h, bg_mode="auto", blur_ksize=61):
    """Place le crop au centre d'une image out_w x out_h.

    bg_mode "auto" : si la case est posée sur un fond uni (texte sur blanc, case sur
    noir), le fond reprend cette couleur et la case garde une marge de chaque côté,
    comme sur la page ; sinon fond flou. "blur" / "black" / "gray" : forcé.
    """
    if crop is None or crop.size == 0:
        return None
    ch, cw = crop.shape[:2]

    if bg_mode == "auto":
        color = border_color(crop)
        if color is None:
            bg_mode = "blur"
        else:
            bg = np.full((out_h, out_w, 3), color, np.uint8)
            box_w, box_h = round(out_w * (1 - 2 * SOLID_MARGIN)), round(out_h * (1 - 2 * SOLID_MARGIN))
            scale = min(box_w / cw, box_h / ch)
            new_w, new_h = max(1, round(cw * scale)), max(1, round(ch * scale))
            y, x = (out_h - new_h) // 2, (out_w - new_w) // 2
            bg[y:y + new_h, x:x + new_w] = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
            return bg

    # "cover" : le crop agrandi remplit tout le cadre et sert de base au fond
    scale_cover = max(out_w / cw, out_h / ch)
    # au moins out_w x out_h : un arrondi à 1 px près donnait un décalage négatif → frame vide
    cover_size = (max(out_w, round(cw * scale_cover)), max(out_h, round(ch * scale_cover)))
    cover = cv2.resize(crop, cover_size, interpolation=cv2.INTER_AREA)
    y0 = (cover.shape[0] - out_h) // 2
    x0 = (cover.shape[1] - out_w) // 2
    frame = cover[y0:y0 + out_h, x0:x0 + out_w].copy()
    bg = make_background(frame, bg_mode, blur_ksize)

    # "contain" : le crop entier, net, collé au centre
    scale_contain = min(out_w / cw, out_h / ch)
    new_w = min(out_w, max(1, round(cw * scale_contain)))
    new_h = min(out_h, max(1, round(ch * scale_contain)))
    crop_rs = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
    y = (out_h - new_h) // 2
    x = (out_w - new_w) // 2
    bg[y:y + new_h, x:x + new_w] = crop_rs
    return bg
