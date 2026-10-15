"""Vignettes du strip pour l'affichage : le chapitre découpé en tranches JPEG légères.

Un strip fait souvent plus de 200 000 px de haut : impossible à afficher d'un bloc
dans un navigateur. On le sert en tranches de TILE_H px (à TILE_W de large), chargées
au fil du défilement.
"""
import json

import cv2
import numpy as np

from manhwa.images import letterbox, load_strip, read_image, write_jpeg
from manhwa.panels import STUDIO_DIR, horizontal_bounds, load_analysis

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


def preview(chapter, meta, analysis, y0, y1, size=(270, 480), bg_mode="blur"):
    """Aperçu 9:16 d'une case, assemblé depuis les vignettes (rapide, sans recharger le strip)."""
    scale = meta["width"] / analysis["width"]
    rows = meta["rows"]
    first, last = y0 // rows, max(y0, y1 - 1) // rows
    parts = [read_image(tiles_dir(chapter) / f"{i:04d}.jpg") for i in range(first, last + 1)]
    parts = [p for p in parts if p is not None]
    if not parts:
        return None
    block = np.vstack(parts)
    top = round((y0 - first * rows) * scale)
    crop = block[top:top + max(1, round((y1 - y0) * scale))]
    x0, x1 = horizontal_bounds(crop, 0, crop.shape[0])
    return letterbox(crop[:, x0:x1], size[0], size[1], bg_mode, 21)
