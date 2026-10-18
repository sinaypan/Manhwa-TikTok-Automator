"""Le défilement continu : la vidéo lit la planche comme sur un téléphone, au lieu d'une case par image.

La planche entière, en pleine largeur, défile de case en case ([render] layout = "scroll") :
    caméra   elle glisse vers la case suivante (GLIDE s), la centre ; une case plus haute que
             l'écran défile jusqu'à la bulle de chaque réplique (ou d'un bout à l'autre)
    relief   dans la case lue, le premier plan avance puis revient (0 au début et à la fin de la
             case, 0 vers ses bords) : les gouttières restent droites, le défilement reste lisse
    reste    visages qui parlent, tremblement et flash des coups : sur la case lue, comme avant
    zoom     [render] scroll_fit : la caméra zoome pour que la case lue remplisse la largeur de
             l'écran (aussi grande qu'une case par image), et ajuste le zoom en glissant

Rien n'est découpé pour l'affichage : ni visage ni texte coupé, les blancs (ou noirs) entre les
cases sont ceux de l'auteur. Les cases restent l'unité de travail (voix, sons, visages…).
"""
import bisect
import math

import numpy as np

GLIDE = 0.6       # s : passage d'une case à la suivante
HOLD_EDGE = 0.12  # une case haute sans bulle : un temps d'arrêt en haut et en bas (part de sa durée)
RELIEF = 0.035    # le premier plan grossit de 3,5 % au plus fort de la case
DRIFT = 0.02      # et glisse de 2 % de la largeur
MAX_ZOOM = 2.0    # avec fit : une case étroite n'est pas agrandie plus de 2 fois
MIN_RELIEF_H = 240  # px : une bande de texte basse n'a pas de relief (il pousserait ses lettres dehors)
FIT_MARGIN = 0.04  # et une petite marge de chaque côté : un texte qui dépasse de la case reste entier


def _ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class Panel:
    """Une case dans la planche mise à la largeur de la vidéo (coordonnées de la planche agrandie)."""

    def __init__(self, crop, k, start, duration, bubbles=(), fx=None, anim=None, depth=None):
        x, y, w, h = crop
        self.x, self.y, self.w, self.h = round(x * k), round(y * k), round(w * k), round(h * k)
        self.start, self.duration = start, duration
        self.bubbles = bubbles  # [(instant dans la case, y du centre de la bulle, planche agrandie)]
        self.fx = fx or {}
        self.anim = anim        # anim(t) : l'image de la case à l'instant t (visages qui parlent)
        self.depth = depth      # relief au quart de la taille de la case (motion.depth_map), ou None
        self.span = (self.x, self.x + self.w)  # ce qui doit tenir en largeur (la case et ses bulles)


def camera_keys(panels, out_w, out_h, total_h, fit=False):
    """[(instant, (centre x, centre y, zoom), durée du trajet)] : où va la caméra, d'arrêt en arrêt.

    fit : la case lue remplit la largeur de l'écran (zoom jusqu'à MAX_ZOOM), comme une case par image.
    """
    keys = []
    for p in panels:
        x0, x1 = p.span
        z = max(1.0, min(MAX_ZOOM, out_w / max(1, (x1 - x0) * (1 + 2 * FIT_MARGIN)))) if fit else 1.0
        view_h = out_h / z
        cx = (x0 + x1) / 2 if fit else out_w / 2
        at = lambda c: (cx, min(total_h - view_h / 2, max(view_h / 2, c)), z)
        if p.h <= view_h:
            keys.append((p.start, at(p.y + p.h / 2), GLIDE))
            continue
        first, last = p.y + view_h / 2, p.y + p.h - view_h / 2  # case haute : de son haut à son bas
        keys.append((p.start, at(first), GLIDE))
        inside = sorted((max(p.start + GLIDE, p.start + t - 0.3), at(min(last, max(first, c)))) for t, c in p.bubbles)
        if inside:  # elle va voir la bulle de chaque réplique
            for k, (when, view) in enumerate(inside):
                nxt = inside[k + 1][0] if k + 1 < len(inside) else p.start + p.duration
                keys.append((when, view, max(0.6, min(1.4, nxt - when))))
        else:  # sans bulle : un temps en haut, elle descend doucement, un temps en bas
            go = p.start + HOLD_EDGE * p.duration
            keys.append((go, at(last), max(0.6, (1 - 2 * HOLD_EDGE) * p.duration)))
    keys.sort(key=lambda k: k[0])
    return keys


def camera_path(keys):
    """camera(t) → (centre x, centre y, zoom) : on glisse vers chaque arrêt, puis on y reste."""
    times = [k[0] for k in keys]
    begin = [np.array(keys[0][1], float)]  # d'où part chaque trajet (là où en était la caméra)

    def along(i, t):
        when, view, move = keys[i]
        return begin[i] + (np.array(view, float) - begin[i]) * _ease((t - when) / move)

    for i in range(1, len(keys)):
        begin.append(along(i - 1, keys[i][0]))

    def camera(t):
        i = bisect.bisect_right(times, t) - 1
        return np.array(keys[0][1], float) if i < 0 else along(i, t)

    return camera


def _relief_maps(panel, local, side, rows):
    """Où prendre chaque pixel des lignes rows de la case, pour le relief à l'instant local (ou None)."""
    import cv2

    e = math.sin(math.pi * min(1.0, max(0.0, local / max(panel.duration, 1e-3))))  # 0 → 1 → 0
    if e < 0.01 or panel.depth is None or panel.h < MIN_RELIEF_H:
        return None
    if not hasattr(panel, "_grid"):  # une fois par case : la grille au quart, le relief ramené à ±1
        near = panel.depth.astype(np.float32)
        qh, qw = near.shape[:2]
        # éteint vers les quatre bords (8 % de la largeur, 8 % de la hauteur) : rien ne sort de la case
        ramp = lambda n: np.clip(np.minimum(np.arange(n), np.arange(n)[::-1]) / max(1.0, 0.08 * n), 0, 1)
        near = near * np.outer(ramp(qh), ramp(qw)).astype(np.float32)
        near = near / max(1e-3, float(np.abs(near).max()))
        cx, cy = (panel.w - 1) / 2, (panel.h - 1) / 2
        dx = ((np.arange(qw, dtype=np.float32) + 0.5) * panel.w / qw - 0.5 - cx)[None, :]
        dy = ((np.arange(qh, dtype=np.float32) + 0.5) * panel.h / qh - 0.5 - cy)[:, None]
        qx = ((np.arange(panel.w, dtype=np.float32) + 0.5) * qw / panel.w - 0.5)[None, :]
        panel._grid = (near, cx, cy, dx, dy, qx, qh / panel.h)
    near, cx, cy, dx, dy, qx, fy = panel._grid
    s = 1 + RELIEF * e * near
    shift = side * DRIFT * panel.w * e * near
    map_x = (cx + (dx - shift) / s).astype(np.float32)
    map_y = (cy + dy / s).astype(np.float32)
    # agrandies seulement pour les lignes visibles (lues dans la grille au quart, en douceur)
    r0, r1 = rows
    qy = ((np.arange(r0, r1, dtype=np.float32) + 0.5) * fy - 0.5)[:, None]
    gx = np.ascontiguousarray(np.broadcast_to(qx, (r1 - r0, panel.w)))
    gy = np.ascontiguousarray(np.broadcast_to(qy, (r1 - r0, panel.w)))
    mx = cv2.remap(map_x, gx, gy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    my = cv2.remap(map_y, gx, gy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return mx, my


def scroll_clip(strip_rgb, panels, out_w, out_h, total, fit=False):
    """La vidéo qui défile. strip_rgb : la planche en RGB, déjà à la largeur out_w.

    fit : la caméra zoome pour que la case lue remplisse la largeur (et ajuste le zoom en glissant).
    """
    import cv2
    from moviepy import VideoClip

    from manhwa import motion

    H = strip_rgb.shape[0]
    if H < out_h:  # planche plus courte que l'écran : on complète en bas
        pad = np.zeros((out_h - H, out_w, 3), np.uint8)
        strip_rgb = np.vstack([strip_rgb, pad])
        H = out_h
    camera = camera_path(camera_keys(panels, out_w, out_h, H, fit))
    starts = [p.start for p in panels]

    def frame(t):
        t = float(t)
        cx, cy, z = camera(t)
        vw, vh = min(out_w, round(out_w / z)), min(H, round(out_h / z))  # ce que voit la caméra, dans la planche
        left = int(min(max(0, round(cx - vw / 2)), out_w - vw))
        top = int(min(max(0, round(cy - vh / 2)), H - vh))
        img = strip_rgb[top:top + vh, left:left + vw].copy()
        i = max(0, bisect.bisect_right(starts, t) - 1)
        cur = panels[i]
        local = t - cur.start
        for j in (i - 1, i):  # la case lue (et la précédente, si elle est encore à l'écran)
            if j < 0:
                continue
            p = panels[j]
            r0, r1 = max(0, top - p.y), min(p.h, top + vh - p.y)
            c0, c1 = max(0, left - p.x), min(p.w, left + vw - p.x)
            if r1 <= r0 or c1 <= c0:
                continue
            here = t - p.start
            src = p.anim(min(here, p.duration - 1e-3)) if p.anim else None  # la précédente : sa dernière pose
            maps = _relief_maps(p, here, 1 if j % 2 == 0 else -1, (r0, r1)) if j == i else None
            if src is None and maps is None:
                continue
            panel_img = src if src is not None else strip_rgb[p.y:p.y + p.h, p.x:p.x + p.w]
            if maps is not None:  # les lignes visibles de la case, en relief
                part = cv2.remap(panel_img, maps[0], maps[1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            else:
                part = panel_img[r0:r1]
            y0, x0 = p.y + r0 - top, p.x + c0 - left
            img[y0:y0 + part.shape[0], x0:x0 + (c1 - c0)] = part[:, c0:c1]
        if (vw, vh) != (out_w, out_h):
            img = cv2.resize(img, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        if cur.fx:  # le coup : tremblement, zoom « punch », flash
            img = motion.fx_frame(img, local, cur.fx)
        return img

    return VideoClip(frame, duration=total)
