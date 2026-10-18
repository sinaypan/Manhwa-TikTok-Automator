"""Le défilement (scroll.py) calculé par la carte graphique : la même image, ≈ 8 fois plus vite.

Sur le processeur, chaque image se fait en plusieurs passes (copier la fenêtre, déformer la case
pour le relief, coller les visages, agrandir, trembler). Ici, pour chaque pixel de l'écran, on
calcule d'où il vient dans la planche (caméra, zoom, tremblement, relief de la case lue), puis la
carte va le chercher en une fois (grid_sample de Paddle, déjà là pour la lecture du texte).
Mesuré : 3,8 ms par image, retour compris, au lieu de ≈ 30 ms sur un cœur.

Si la carte n'est pas là (ou Paddle sans CUDA), scroll.scroll_clip fait tout sur le processeur.
"""
import math
import threading

import numpy as np

from manhwa import motion
from manhwa.scroll import DRIFT, FADE, MIN_RELIEF_H, RELIEF, _ease, camera_keys, camera_path, relief_quarter

_PADDLE = {}


def available():
    """Paddle sur la carte graphique (essayé une fois)."""
    if "ok" not in _PADDLE:
        try:
            from manhwa.gpu import before_paddle

            before_paddle()
            import paddle

            _PADDLE["ok"] = paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0
        except Exception:
            _PADDLE["ok"] = False
    return _PADDLE["ok"]


def scroll_clip_gpu(strip_rgb, panels, out_w, out_h, total, fit=False):
    """Comme scroll.scroll_clip, calculé par la carte graphique."""
    import paddle
    import paddle.nn.functional as F
    from moviepy import VideoClip

    paddle.set_device("gpu:0")
    H = strip_rgb.shape[0]
    if H < out_h:
        strip_rgb = np.vstack([strip_rgb, np.zeros((out_h - H, out_w, 3), np.uint8)])
        H = out_h
    camera = camera_path(camera_keys(panels, out_w, out_h, H, fit))
    starts = [p.start for p in panels]
    strip = paddle.to_tensor(np.ascontiguousarray(strip_rgb.transpose(2, 0, 1)))  # 3 × H × W, en 8 bits
    Y, X = paddle.meshgrid(paddle.arange(out_h, dtype="float32"), paddle.arange(out_w, dtype="float32"))
    lock = threading.Lock()  # la carte une image à la fois ; le reste (sous-titres, YUV) reste en parallèle
    poses = {}               # les poses des visages qui parlent, déjà sur la carte (en 32 bits)
    before = {}
    chunk = {}               # un morceau de la planche en 32 bits, gardé tant que la caméra y reste
    CHUNK = 6144

    def strip_rows(y0, y1):
        """La planche entre y0 et y1, en 32 bits : (tenseur, sa première ligne)."""
        c = chunk.get("rows")
        if not c or y0 < c[0] or y1 > c[1]:
            a = max(0, min(y0 - 512, H - CHUNK))
            b = min(H, max(a + CHUNK, y1 + 512))
            chunk["rows"] = (a, b, strip[:, a:b].astype("float32").unsqueeze(0))
            c = chunk["rows"]
        return c[2], c[0]

    def sample(img, sx, sy, y0=0):
        """img (1 × 3 × h × w, 32 bits) lu aux coordonnées (sx, sy) (pixels ; y à partir de y0) → 3 × out_h × out_w."""
        h, w = img.shape[2], img.shape[3]
        grid = paddle.stack([sx * (2 / max(1, w - 1)) - 1, (sy - y0) * (2 / max(1, h - 1)) - 1], axis=-1).unsqueeze(0)
        return F.grid_sample(img, grid, mode="bilinear", padding_mode="border", align_corners=True)[0]

    def on_card(img):
        key = id(img)
        if key not in poses:
            if len(poses) > 24:
                poses.clear()
            poses[key] = (img, paddle.to_tensor(np.ascontiguousarray(img.transpose(2, 0, 1))).astype("float32").unsqueeze(0))
        return poses[key][1]

    def render(t):
        cx, cy, z = camera(t)
        vw, vh = min(out_w, round(out_w / z)), min(H, round(out_h / z))
        left = int(min(max(0, round(cx - vw / 2)), out_w - vw))
        top = int(min(max(0, round(cy - vh / 2)), H - vh))
        i = max(0, int(np.searchsorted(starts, t, side="right")) - 1)
        cur = panels[i]
        local = t - cur.start
        # le coup : tremblement et zoom « punch » (motion.fx_frame), repris dans le calcul des coordonnées
        px, py = X, Y
        if cur.fx:
            dx, dy = motion.offset(local, cur.fx.get("shake", 0))
            zz = motion.punch_at(local, cur.fx.get("punch", 0))
            if dx or dy or zz:
                s = 1.04 + zz
                px = (X - dx - (1 - s) * out_w / 2) / s
                py = (Y - dy - (1 - s) * out_h / 2) / s
        sx = left + (px + 0.5) * (vw / out_w) - 0.5  # comme cv2.resize (centres des pixels)
        sy = top + (py + 0.5) * (vh / out_h) - 0.5
        layers = []  # les cases dont un visage parle : lues dans leur propre image
        for j in (i - 1, i):  # la case lue (et la précédente encore à l'écran) : relief, visages qui parlent
            if j < 0:
                continue
            p = panels[j]
            if p.y + p.h < top or p.y > top + vh or p.x + p.w < left or p.x > left + vw:
                continue
            here = t - p.start
            pose = p.anim(min(here, p.duration - 1e-3)) if p.anim else None
            relief = _relief_quarter(p, here, 1 if j % 2 == 0 else -1) if j == i else None
            if pose is None and relief is None:
                continue
            u, v = sx - p.x, sy - p.y
            inside = (u >= -0.5) & (u < p.w - 0.5) & (v >= -0.5) & (v < p.h - 0.5)
            if relief is not None:  # d'où vient chaque pixel de la case, lu dans la grille au quart
                maps, qw, qh = relief
                grid = paddle.stack([((u + 0.5) * (qw / p.w) - 0.5) * (2 / max(1, qw - 1)) - 1,
                                     ((v + 0.5) * (qh / p.h) - 0.5) * (2 / max(1, qh - 1)) - 1], axis=-1).unsqueeze(0)
                mm = F.grid_sample(maps, grid, mode="bilinear", padding_mode="border", align_corners=True)[0]
                u, v = mm[0], mm[1]
            if pose is not None:
                layers.append((inside, on_card(pose), u, v))
            else:  # même planche : seules les coordonnées changent, une seule lecture pour tout
                sx = paddle.where(inside, u + p.x, sx)
                sy = paddle.where(inside, v + p.y, sy)
        rows, y0 = strip_rows(max(0, top - 64), min(H, top + vh + 64))
        out = sample(rows, sx, sy, y0)
        for inside, img, u, v in layers:
            out = paddle.where(inside.unsqueeze(0), sample(img, u, v), out)
        if cur.fx:
            a = motion.flash_at(local, cur.fx.get("flash", 0))
            if a > 0.01:
                out = out * (1 - a) + 255 * a
        return out, i, local

    def frame(t):
        t = float(t)
        with lock:
            out, i, local = render(t)
            cur = panels[i]
            if cur.enter == "fade" and i and local < FADE:  # un autre lieu : fondu depuis la dernière image d'avant
                if i not in before:
                    before.clear()
                    before[i] = render(cur.start - 1e-3)[0]
                a = _ease(local / FADE)
                out = before[i] * (1 - a) + out * a
            img = out.clip(0, 255).astype("uint8").transpose([1, 2, 0]).numpy()
        return img

    return VideoClip(frame, duration=total)


def _relief_quarter(panel, local, side):
    """Les cartes du relief au quart (comme scroll.relief_quarter), calculées sur la carte : (1 × 2 × qh × qw, qw, qh).

    La grille de la case est envoyée une fois ; à chaque image il ne reste que quelques opérations sur
    la carte (au lieu de refaire les cartes sur le processeur et de les envoyer : 5 ms par image).
    """
    import paddle

    e = math.sin(math.pi * min(1.0, max(0.0, local / max(panel.duration, 1e-3))))
    if e < 0.01 or panel.depth is None or panel.h < MIN_RELIEF_H:
        return None
    if not hasattr(panel, "_gpu"):
        relief_quarter(panel, local, side)  # prépare panel._grid
        near, cx, cy, dx, dy, _, _ = panel._grid
        qh, qw = near.shape
        panel._gpu = (paddle.to_tensor(near), cx, cy, paddle.to_tensor(np.broadcast_to(dx, near.shape).copy()),
                      paddle.to_tensor(np.broadcast_to(dy, near.shape).copy()), qw, qh)
    near, cx, cy, dx, dy, qw, qh = panel._gpu
    s = 1 + RELIEF * e * near
    map_x = cx + (dx - side * DRIFT * panel.w * e * near) / s
    map_y = cy + dy / s
    return paddle.stack([map_x, map_y]).unsqueeze(0), qw, qh
