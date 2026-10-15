"""Outils images partagés : tri naturel, lecture/écriture, strip, format 9:16."""
import re
from pathlib import Path

import cv2
import numpy as np

SUPPORTED = (".jpg", ".jpeg", ".png", ".webp")
BG_MODES = ("blur", "black", "gray")


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

    target_w = min(min(im.shape[1] for im in imgs), max_width)
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


def letterbox(crop, out_w, out_h, bg_mode="blur", blur_ksize=61):
    """Place le crop au centre d'une image out_w x out_h, sur un fond flou/noir/gris."""
    if crop is None or crop.size == 0:
        return None
    ch, cw = crop.shape[:2]

    # "cover" : le crop agrandi remplit tout le cadre et sert de base au fond
    scale_cover = max(out_w / cw, out_h / ch)
    cover = cv2.resize(crop, (int(cw * scale_cover), int(ch * scale_cover)), interpolation=cv2.INTER_AREA)
    y0 = (cover.shape[0] - out_h) // 2
    x0 = (cover.shape[1] - out_w) // 2
    frame = cover[y0:y0 + out_h, x0:x0 + out_w].copy()
    bg = make_background(frame, bg_mode, blur_ksize)

    # "contain" : le crop entier, net, collé au centre
    scale_contain = min(out_w / cw, out_h / ch)
    new_w, new_h = int(cw * scale_contain), int(ch * scale_contain)
    crop_rs = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
    y = (out_h - new_h) // 2
    x = (out_w - new_w) // 2
    bg[y:y + new_h, x:x + new_w] = crop_rs
    return bg
