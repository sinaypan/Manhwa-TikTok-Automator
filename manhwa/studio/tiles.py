"""Vignettes du strip pour l'affichage : le chapitre découpé en tranches JPEG légères.

Un strip fait souvent plus de 200 000 px de haut : impossible à afficher d'un bloc
dans un navigateur. On le sert en tranches de TILE_H px (à TILE_W de large), chargées
au fil du défilement.
"""
import json

import cv2
import numpy as np

from manhwa.images import FLAT_RATIO, letterbox, load_strip, page_color, read_image, write_jpeg
from manhwa.panels import STUDIO_DIR, horizontal_bounds, load_analysis, split_tall

TILE_W = 600   # largeur d'affichage (≈ 2× la largeur à l'écran, pour rester net)
TILE_H = 1600  # hauteur d'une tranche en pixels d'affichage


def tiles_dir(chapter):
    return chapter.root / STUDIO_DIR / "tiles"


def read_meta(chapter):
    path = tiles_dir(chapter) / "meta.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def prepare(chapter, cfg):
    """Profil + vignettes à jour (le strip n'est chargé qu'une fois, et seulement si besoin)."""
    analysis = load_analysis(chapter, cfg, compute=False)
    meta = read_meta(chapter)
    if analysis and meta and meta["key"] == analysis["key"]:
        return analysis, meta

    strip, _ = load_strip(chapter.pages(), cfg["slicer"]["max_src_width"])
    if strip is None:
        return None, None
    analysis = load_analysis(chapter, cfg, strip=strip)
    H, W = strip.shape[:2]
    rows = max(1, round(TILE_H * W / TILE_W))  # hauteur d'une tranche en lignes du strip
    folder = tiles_dir(chapter)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.jpg"):
        old.unlink()
    count = 0
    for i, y in enumerate(range(0, H, rows)):
        part = strip[y:y + rows]
        h = max(1, round(part.shape[0] * TILE_W / W))
        write_jpeg(folder / f"{i:04d}.jpg", cv2.resize(part, (TILE_W, h), interpolation=cv2.INTER_AREA), 82)
        count += 1
    meta = {"key": analysis["key"], "rows": rows, "count": count, "width": TILE_W}
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return analysis, meta


def _block(chapter, meta, analysis, y0, y1):
    """Les lignes y0 → y1 du strip, en résolution d'affichage, depuis les vignettes."""
    scale = meta["width"] / analysis["width"]
    rows = meta["rows"]
    first, last = y0 // rows, max(y0, y1 - 1) // rows
    parts = [read_image(tiles_dir(chapter) / f"{i:04d}.jpg") for i in range(first, last + 1)]
    parts = [p for p in parts if p is not None]
    if not parts:
        return None, scale
    block = np.vstack(parts)
    top = round((y0 - first * rows) * scale)
    return block[top:top + max(1, round((y1 - y0) * scale))], scale


def panel_frames(chapter, meta, analysis, y0, y1):
    """Les frames que la vidéo fera pour cette case : mêmes marges et même découpage
    que build_frames (calculés ici sur les vignettes), pour un aperçu fidèle.

    Renvoie {"x0", "x1", "parts": [[a, b], ...]} en lignes du strip, ou None.
    """
    block, scale = _block(chapter, meta, analysis, y0, y1)
    if block is None:
        return None
    bx0, bx1 = horizontal_bounds(block, 0, block.shape[0])
    x0, x1 = round(bx0 / scale), round(bx1 / scale)
    parts = split_tall(y0, y1, x1 - x0, analysis["std"])
    return {"x0": x0, "x1": x1, "parts": [[int(a), int(b)] for a, b in parts]}


def preview(chapter, meta, analysis, y0, y1, x0=None, x1=None, size=(270, 480), bg_mode="auto"):
    """Aperçu 9:16 d'une frame, assemblé depuis les vignettes (rapide, sans recharger le strip).

    x0/x1 (lignes du strip) : marges de la case ; sinon calculées sur ce morceau. On prend
    aussi un peu de page autour, pour reconnaître le fond uni comme le fait build_frames.
    """
    margin = 12
    top_y = max(0, y0 - margin)
    block, scale = _block(chapter, meta, analysis, top_y, min(analysis["height"], y1 + margin))
    if block is None:
        return None
    top = round((y0 - top_y) * scale)
    height = max(1, round((y1 - y0) * scale))
    crop = block[top:top + height]
    if x0 is None or x1 is None:
        cx0, cx1 = horizontal_bounds(crop, 0, crop.shape[0])
    else:
        cx0, cx1 = round(x0 * scale), round(x1 * scale)
    around = None
    if crop.shape[0] < FLAT_RATIO * (cx1 - cx0):  # même règle que flat_page_color
        around = page_color(block, cx0, top, cx1 - cx0, crop.shape[0], band=max(2, round(8 * scale)))
    return letterbox(crop[:, cx0:cx1], size[0], size[1], bg_mode, 21, around=around)


def region(chapter, meta, analysis, x, y, w, h, out_w=360):
    """Un rectangle du strip (lignes et colonnes du strip), en petite image pour l'écran Personnages."""
    block, scale = _block(chapter, meta, analysis, max(0, y), min(analysis["height"], y + h))
    if block is None:
        return None
    x0, x1 = max(0, round(x * scale)), min(block.shape[1], round((x + w) * scale))
    part = block[:, x0:x1]
    if part.size == 0:
        return None
    out_h = max(1, round(part.shape[0] * out_w / part.shape[1]))
    return cv2.resize(part, (out_w, out_h), interpolation=cv2.INTER_AREA)
