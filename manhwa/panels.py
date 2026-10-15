"""Découpe automatique : repérer les gouttières (bandes unies entre les cases).

Toutes les positions sont en lignes du strip (le chapitre empilé en une seule image).
- profil : pour chaque ligne, sa texture (écart-type) et sa luminosité ;
- gouttière : une suite de lignes unies, de la couleur du fond ou assez longue ;
- coupe : le milieu d'une gouttière. « sure » = gouttière large de la couleur du fond ;
  les autres sont à vérifier dans le Studio.
- case : ce qu'il y a entre deux coupes, sans ses marges unies.
"""
import math

import cv2
import numpy as np

from manhwa.images import load_strip
from manhwa.project import fingerprint

PROFILE_VERSION = 1      # change la clé du cache .studio/ (profil des lignes)
AUTOCUT_VERSION = 2      # version de la proposition de coupes (v2 : séparations cachées)
BLANK_STD = 8.0          # texture max d'une ligne « unie » (le bruit JPEG/WebP reste dessous)
THIN_LINE_STD = 4.0      # un trait fin entre deux cases doit être parfaitement uni
ANALYSIS_FILE = "analysis.npz"
STUDIO_DIR = ".studio"   # cache du chapitre (profil, vignettes), jamais nécessaire au rendu


# ---------- Profil des lignes ----------

def row_profile(strip, col_step=4, chunk=8192):
    """Texture et luminosité de chaque ligne (une colonne sur `col_step`, par paquets)."""
    H = strip.shape[0]
    std = np.empty(H, np.float32)
    mean = np.empty(H, np.float32)
    for y in range(0, H, chunk):
        part = np.ascontiguousarray(strip[y:y + chunk, ::col_step])
        gray = cv2.cvtColor(part, cv2.COLOR_BGR2GRAY).astype(np.float32)
        std[y:y + chunk] = gray.std(axis=1)
        mean[y:y + chunk] = gray.mean(axis=1)
    return std, mean


def _runs(mask):
    """[(début, fin)] des suites de True (fin exclue)."""
    padded = np.concatenate(([False], mask, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


# ---------- Gouttières et coupes ----------

def find_gutters(std, mean, width):
    """Les bandes unies qui séparent des cases : [{"y0", "y1", "sure"}]."""
    min_gap = max(6, int(width * 0.015))
    runs = [(a, b) for a, b in _runs(std < BLANK_STD) if b - a >= min_gap]
    if not runs:
        return []

    # couleur du fond : la luminosité qui couvre le plus de lignes unies
    weight = np.zeros(256)
    for a, b in runs:
        weight[int(np.clip(np.median(mean[a:b]), 0, 255))] += b - a
    background = int(np.argmax(np.convolve(weight, np.ones(9), mode="same")))

    gutters = []
    for a, b in runs:
        lum = float(np.median(mean[a:b]))
        # blanc ou noir pur = fond de webtoon ; un ciel uni au milieu d'une case n'en est pas un
        on_background = abs(lum - background) <= 25 or lum >= 235 or lum <= 20
        if on_background or b - a >= width * 0.3:
            gutters.append({"y0": a, "y1": b, "sure": on_background and b - a >= 2 * min_gap})
    return gutters


def content_bounds(std, y0, y1):
    """(début, fin) du contenu entre y0 et y1, sans les lignes unies au bord ; None si vide."""
    rows = np.flatnonzero(std[y0:y1] >= BLANK_STD)
    if rows.size == 0:
        return None
    return y0 + int(rows[0]), y0 + int(rows[-1]) + 1


def auto_cuts(std, mean, width):
    """Coupes proposées : [{"y", "sure"}], triées.

    Les tout petits morceaux (un « ... », une ligne de crédits) sont recollés à la case
    voisine quand elles sont proches ; une bulle seule loin de tout reste une case.
    """
    H = len(std)
    gutters = [g for g in find_gutters(std, mean, width) if g["y0"] > 0 and g["y1"] < H]
    cuts = [{"y": (g["y0"] + g["y1"]) // 2, "sure": g["sure"], "gap": g["y1"] - g["y0"]} for g in gutters]

    min_panel = width * 0.12
    max_gap_to_merge = width * 0.2
    changed = True
    while changed:
        changed = False
        bounds = [0] + [c["y"] for c in cuts] + [H]
        for i in range(len(bounds) - 1):
            span = content_bounds(std, bounds[i], bounds[i + 1])
            if span is not None and span[1] - span[0] >= min_panel:
                continue
            # coupe au-dessus = cuts[i-1], coupe en dessous = cuts[i]
            candidates = [j for j in (i - 1, i) if 0 <= j < len(cuts) and cuts[j]["gap"] <= max_gap_to_merge]
            if span is None:
                candidates = [j for j in (i - 1, i) if 0 <= j < len(cuts)]  # morceau vide : on le supprime
            if candidates:
                del cuts[min(candidates, key=lambda j: cuts[j]["gap"])]
                changed = True
                break
    out = [{"y": c["y"], "sure": c["sure"]} for c in cuts]
    return sorted(out + hidden_separations(std, [c["y"] for c in out], width), key=lambda c: c["y"])


def hidden_separations(std, cut_ys, width):
    """Dans les cases hautes, les séparations probables qui ne sont pas de vraies marges.

    Une marge trop fine pour être une vraie gouttière (quelques px) sépare souvent deux
    cases. On la propose comme coupe incertaine (« à vérifier »), jamais près du bord
    d'une case, au plus une par écran.
    """
    screen = width * 16 / 9
    min_gap = max(6, int(width * 0.015))
    found = []
    for y0, y1 in panels_from_cuts(cut_ys, std):
        h = y1 - y0
        if h <= 1.5 * screen:
            continue
        lo, hi = y0 + int(0.25 * screen), y1 - int(0.25 * screen)
        inner = std[lo:hi]
        # marge très fine : quelques lignes parfaitement unies (un trait entre deux cases).
        # Seuil plus strict que BLANK_STD : un aplat sombre du dessin (vêtement, nuit) est
        # presque uni et donnait de fausses alertes. Les zones « calmes » (fondu, brume) ont
        # aussi été essayées : elles attrapaient les cheveux et les vêtements sombres.
        candidates = [(a, b) for a, b in _runs(inner < THIN_LINE_STD) if 3 <= b - a < min_gap]
        # les plus longues d'abord, sans doublons proches
        chosen = []
        for a, b in sorted(candidates, key=lambda r: r[1] - r[0], reverse=True):
            y = lo + (a + b) // 2
            if all(abs(y - c) > 0.4 * screen for c in chosen):
                chosen.append(y)
            if len(chosen) >= int(h // screen):
                break
        found += [{"y": y, "sure": False} for y in chosen]
    return found


def snap(y, gutters, radius):
    """Aimante une coupe ajoutée à la main sur le milieu de la gouttière la plus proche."""
    best, best_dist = y, radius + 1
    for g in gutters:
        dist = 0 if g["y0"] <= y < g["y1"] else min(abs(y - g["y0"]), abs(y - g["y1"]))
        if dist < best_dist:
            best, best_dist = (g["y0"] + g["y1"]) // 2, dist
    return int(best)


def panels_from_cuts(cut_ys, std):
    """Cases [(y0, y1)] entre les coupes, marges unies retirées, cases vides ignorées."""
    H = len(std)
    bounds = [0] + sorted(int(y) for y in cut_ys if 0 < y < H) + [H]
    panels = []
    for a, b in zip(bounds, bounds[1:]):
        span = content_bounds(std, a, b)
        if span and span[1] - span[0] >= 8:
            panels.append(span)
    return panels


# ---------- Frames 9:16 ----------

def horizontal_bounds(strip, y0, y1):
    """(x0, x1) sans les marges unies à gauche et à droite (si elles valent le coup)."""
    W = strip.shape[1]
    step = max(1, (y1 - y0) // 400)
    gray = cv2.cvtColor(np.ascontiguousarray(strip[y0:y1:step]), cv2.COLOR_BGR2GRAY).astype(np.float32)
    cols = np.flatnonzero(gray.std(axis=0) >= BLANK_STD)
    if cols.size == 0:
        return 0, W
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    if x0 < W * 0.02:
        x0 = 0
    if W - x1 < W * 0.02:
        x1 = W
    if x1 - x0 < W * 0.3:  # trop étroit : on garde toute la largeur
        return 0, W
    return x0, x1


MAX_SCREENS_WHOLE = 2.0  # jusqu'à 2 écrans, une case reste entière (un peu réduite, pas zoomée)


def split_tall(y0, y1, width, std):
    """Une case de plus de 2 écrans 9:16 est coupée en plusieurs frames.

    En dessous, on la garde entière : couper un visage en deux frames zoomées est pire
    qu'une case un peu réduite (c'était le cas dès 1,25 écran avant).
    Temporaire : en phase 5, une case haute sera parcourue en défilement.
    Chaque coupe tombe sur la ligne la moins chargée près du découpage régulier,
    pour éviter de trancher une bulle.
    """
    screen = width * 16 / 9
    if (y1 - y0) <= MAX_SCREENS_WHOLE * screen:
        return [(y0, y1)]
    n = math.ceil((y1 - y0) / (screen * 1.6))
    step = (y1 - y0) / n
    edges = [y0]
    for k in range(1, n):
        ideal = int(y0 + k * step)
        window = int(step * 0.1)
        lo, hi = max(edges[-1] + 1, ideal - window), min(y1 - 1, ideal + window)
        edges.append(lo + int(np.argmin(std[lo:hi])) if hi > lo else ideal)
    edges.append(y1)
    return list(zip(edges, edges[1:]))


def frame_crops(strip, panels, std):
    """[(case, [x, y, w, h])] : les crops des frames, dans l'ordre de lecture."""
    crops = []
    for index, (y0, y1) in enumerate(panels):
        x0, x1 = horizontal_bounds(strip, y0, y1)
        for a, b in split_tall(y0, y1, x1 - x0, std):
            crops.append((index, [x0, a, x1 - x0, b - a]))
    return crops


# ---------- Analyse mise en cache ----------

def pages_key(chapter, max_width):
    pages = chapter.pages()
    stats = [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in pages]
    return fingerprint(PROFILE_VERSION, max_width, stats)


def analysis_path(chapter):
    return chapter.root / STUDIO_DIR / ANALYSIS_FILE


def load_analysis(chapter, cfg, strip=None, compute=True):
    """Profil des lignes du chapitre (calculé une fois, puis lu depuis .studio/).

    Renvoie {"key", "width", "height", "std", "mean", "pages", "max_width"} ou None.
    compute=False : seulement le cache, None s'il manque ou n'est plus à jour.
    """
    max_width = cfg["slicer"]["max_src_width"]
    key = pages_key(chapter, max_width)
    path = analysis_path(chapter)
    if path.is_file():
        with np.load(path, allow_pickle=False) as z:
            if str(z["key"]) == key:
                return {"key": key, "width": int(z["width"]), "height": int(z["std"].shape[0]),
                        "std": z["std"], "mean": z["mean"], "pages": z["pages"].tolist(), "max_width": max_width}

    if not compute:
        return None
    used = None
    if strip is None:
        strip, used = load_strip(chapter.pages(), max_width)
        if strip is None:
            return None
    pages = [p.name for p in (used or chapter.pages())]
    std, mean = row_profile(strip)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("analysis.tmp.npz")
    np.savez_compressed(tmp, key=key, width=strip.shape[1], std=std, mean=mean, pages=np.array(pages))
    tmp.replace(path)
    return {"key": key, "width": strip.shape[1], "height": strip.shape[0],
            "std": std, "mean": mean, "pages": pages, "max_width": max_width}


def strip_info(analysis):
    return {"width": analysis["width"], "height": analysis["height"],
            "max_width": analysis["max_width"], "pages": list(analysis["pages"])}


def ensure_cuts(chapter, cfg, data=None, analysis=None):
    """Les coupes du chapitre : celles enregistrées, sinon la proposition automatique."""
    data = data if data is not None else chapter.load()
    analysis = analysis or load_analysis(chapter, cfg)
    if analysis is None:
        return data, None
    cut = data.get("cut")
    pages_changed = not cut or cut.get("key") != analysis["key"]
    # une découpe retouchée à la main n'est jamais remplacée, sauf si les pages ont changé
    outdated = cut and not cut.get("edited") and cut.get("auto_version", 1) != AUTOCUT_VERSION
    if pages_changed or outdated:
        data["cut"] = {
            "key": analysis["key"],
            "auto_version": AUTOCUT_VERSION,
            "cuts": auto_cuts(analysis["std"], analysis["mean"], analysis["width"]),
            "edited": False,
            "validated": False,
        }
        chapter.save(data)
    return data, analysis


# ce qu'une frame garde quand son crop n'a pas changé : pas besoin de relire ni de revoicer
KEPT_FRAME_KEYS = ("lines", "bubbles", "bubbles_version", "text", "ocr_key", "audio", "audio_key", "speakers", "review", "segments", "sounds", "action_sound")


def build_frames(chapter, cfg, bg_mode=None, progress=None):
    """Écrit les frames 9:16 d'après les coupes, en gardant OCR et voix des crops inchangés."""
    from manhwa.images import flat_page_color, letterbox, write_jpeg

    sc = cfg["slicer"]
    strip, used = load_strip(chapter.pages(), sc["max_src_width"])
    if strip is None:
        return 0
    analysis = load_analysis(chapter, cfg, strip=strip)
    data, _ = ensure_cuts(chapter, cfg, analysis=analysis)
    panels = panels_from_cuts([c["y"] for c in data["cut"]["cuts"]], analysis["std"])
    crops = frame_crops(strip, panels, analysis["std"])

    bg_mode = bg_mode or sc["bg_mode"]
    previous = {tuple(f["crop"]): f for f in data["frames"] if data.get("strip") == strip_info(analysis)}
    chapter.frames_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, (panel, crop) in enumerate(crops, start=1):
        x, y, w, h = crop
        name = f"frame_{i:04d}.jpg"
        out = letterbox(strip[y:y + h, x:x + w], cfg["output"]["width"], cfg["output"]["height"],
                        bg_mode, sc["blur_ksize"], around=flat_page_color(strip, x, y, w, h))
        write_jpeg(chapter.frames_dir / name, out, sc["jpeg_quality"])
        if progress:
            progress(i, len(crops))
        frame = {k: v for k, v in previous.get(tuple(crop), {}).items() if k in KEPT_FRAME_KEYS}
        frame.update({"file": name, "crop": crop, "bg": bg_mode, "panel": panel})
        frames.append(frame)

    keep = {f["file"] for f in frames}
    for old in chapter.frames_dir.glob("frame_*.jpg"):
        if old.name not in keep:
            old.unlink()
    data["frames"] = frames
    data["strip"] = strip_info(analysis)
    data["cut"]["validated"] = True
    chapter.save(data)
    return len(frames)
