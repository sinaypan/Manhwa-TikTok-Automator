"""Des images moins plates : l'image réagit aux bruitages.

    - la caméra tremble sur un coup, un choc contre un mur, une explosion (plus fort si le
      moment est violent : la « force » choisie par GPT dans l'onglet Sons) ;
    - un flash blanc très court sur un coup violent.

L'effet part avec le son (0,05 s après le début de la case) et s'éteint en moins d'une seconde.
Réglé dans config.toml : [render] effects = true.
"""
import math

START = 0.05  # comme le premier bruitage au rendu
# combien chaque son fait trembler l'image (1 = un coup de poing normal)
SHAKE = {"punch": 1.0, "impact": 0.8, "slam": 1.3, "fall": 0.7, "explosion": 1.4, "thunder": 0.9, "metal": 0.6,
         "rumble": 1.0, "wood": 0.4, "glass": 0.5, "energy": 0.7}
FLASH = {"punch", "slam", "explosion", "thunder", "energy", "slash", "impact"}
STRENGTH = {1: 0.4, 2: 0.8, 3: 1.3}
SHAKE_PX = 16  # amplitude d'un coup normal (image de 1080 de large)
MIN_PX = 4


def effects(hits):
    """hits : [(couches, force)] d'une case → {"shake": pixels, "flash": 0..1} (ou {})."""
    shake, flash = 0.0, 0.0
    for cats, strength in hits:
        k = STRENGTH.get(strength or 2, 0.8)
        shake = max([shake] + [SHAKE_PX * SHAKE.get(c, 0) * k for c in cats])
        if (strength or 2) >= 3 and any(c in FLASH for c in cats):
            flash = 0.55
    out = {}
    if shake >= MIN_PX:
        out["shake"] = round(shake, 1)
    if flash:
        out["flash"] = flash
    return out


def offset(t, amount):
    """Le décalage de la caméra à l'instant t (secondes depuis le début de la case)."""
    dt = t - START
    if dt < 0 or dt > 0.8 or not amount:
        return 0.0, 0.0
    fade = math.exp(-dt / 0.16)
    return amount * fade * math.sin(2 * math.pi * 17 * dt), 0.7 * amount * fade * math.cos(2 * math.pi * 13 * dt + 1)


def flash_at(t, amount):
    dt = t - START
    return amount * math.exp(-dt / 0.07) if amount and 0 <= dt <= 0.35 else 0.0


def apply(clip, fx):
    """La case avec ses effets (rien à faire si fx est vide)."""
    if not fx:
        return clip
    import cv2
    import numpy as np

    shake, flash = fx.get("shake", 0), fx.get("flash", 0)

    def frame(get_frame, t):
        img = get_frame(t)
        dx, dy = offset(t, shake)
        if dx or dy:
            h, w = img.shape[:2]
            m = np.float32([[1.02, 0, dx - 0.01 * w], [0, 1.02, dy - 0.01 * h]])  # un peu zoomé : pas de bord vide
            img = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT101)
        a = flash_at(t, flash)
        if a > 0.01:
            img = (img.astype(np.float32) * (1 - a) + 255 * a).astype(np.uint8)
        return img

    return clip.transform(frame)


# ---------- Profondeur : le premier plan avance un peu plus que le fond ----------
# Depth Anything V2 Small (Apache 2.0, version ONNX d'onnx-community) estime ce qui est devant.
# Pendant le léger zoom de la case, ce qui est proche grossit un peu plus que le fond : l'image
# prend du relief. La carte de profondeur est très lissée : une bulle bouge d'un bloc, son texte
# ne se tord pas. Réglé dans config.toml : [render] depth = true.

DEPTH_MODEL = {"depth_anything_v2_small_fp16.onnx": (
    "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model_fp16.onnx",
    "2df6223f206b5164e21f664ace61dabeb9bb6a49b8b5a3e00510b4807d0f5b04")}
DEPTH_SIDE = 518
PARALLAX = 0.9  # le premier plan zoome jusqu'à 90 % de plus que le zoom de la case
_DEPTH = {}


def _depth_session():
    if "s" not in _DEPTH:
        import onnxruntime as ort

        from manhwa.faces import ensure_models, models_dir
        from manhwa.gpu import onnx_providers

        ensure_models(DEPTH_MODEL)
        _DEPTH["s"] = ort.InferenceSession(str(models_dir() / next(iter(DEPTH_MODEL))), providers=onnx_providers())
    return _DEPTH["s"]


def panel_rect(image, crop_size):
    """Où est la case dans la frame 9:16 (images.letterbox) : (x, y, l, h)."""
    import numpy as np

    from manhwa.images import SOLID_MARGIN

    h, w = image.shape[:2]
    cw, ch = crop_size
    s = min(w / cw, h / ch)  # la case entière, au centre (fond flou)
    fit = (round(cw * s), round(ch * s))
    s2 = min(w * (1 - 2 * SOLID_MARGIN) / cw, h * (1 - 2 * SOLID_MARGIN) / ch)  # fond uni : avec une marge
    margin = (round(cw * s2), round(ch * s2))
    nw, nh = margin
    x, y = (w - nw) // 2, (h - nh) // 2
    ring = np.concatenate([image[max(0, y - 6):y - 2, x:x + nw].reshape(-1, 3), image[y + nh + 2:y + nh + 6, x:x + nw].reshape(-1, 3),
                           image[y:y + nh, max(0, x - 6):x - 2].reshape(-1, 3), image[y:y + nh, x + nw + 2:x + nw + 6].reshape(-1, 3)])
    nw, nh = margin if len(ring) and ring.std(axis=0).max() < 4 else fit  # autour, une couleur unie : fond uni
    return (w - nw) // 2, (h - nh) // 2, nw, nh


def depth_map(rgb, rect=None):
    """0 (loin) → 1 (près) dans la case (rect), 0 autour ; à la taille de l'image, très lissé.

    Le relief s'éteint vers les bords de la case : ses bords restent droits.
    """
    import cv2
    import numpy as np

    H, W = rgb.shape[:2]
    x0, y0, w, h = rect or (0, 0, W, H)
    img = rgb[y0:y0 + h, x0:x0 + w]
    scale = DEPTH_SIDE / min(h, w)
    nh, nw = (max(14, round(h * scale / 14) * 14), max(14, round(w * scale / 14) * 14))
    if max(nh, nw) > 4 * DEPTH_SIDE:  # case très haute : on garde une taille raisonnable
        f = 4 * DEPTH_SIDE / max(nh, nw)
        nh, nw = max(14, round(nh * f / 14) * 14), max(14, round(nw * f / 14) * 14)
    x = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
    x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    s = _depth_session()
    inp = s.get_inputs()[0]
    x = x.transpose(2, 0, 1)[None].astype(np.float16 if "16" in inp.type else np.float32)
    d = s.run(None, {inp.name: x})[0][0].astype(np.float32)
    lo, hi = np.percentile(d, 2), np.percentile(d, 98)
    d = np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)
    d = cv2.resize(d, (w, h), interpolation=cv2.INTER_LINEAR)
    k = int(0.08 * min(w, h)) | 1  # lissage fort : pas de bord net, donc pas de texte tordu
    d = cv2.GaussianBlur(d, (k, k), 0)
    d -= float(np.median(d))  # le plan du milieu suit le zoom de la case
    edge = max(4, int(0.08 * min(w, h)))  # fondu vers 0 près des bords de la case
    ry = np.clip(np.minimum(np.arange(h), np.arange(h)[::-1]) / edge, 0, 1)
    rx = np.clip(np.minimum(np.arange(w), np.arange(w)[::-1]) / edge, 0, 1)
    out = np.zeros((H, W), np.float32)
    out[y0:y0 + h, x0:x0 + w] = d * np.outer(ry, rx)
    return out


_GRID = {}


def _grid(h, w):
    """Les coordonnées de chaque pixel par rapport au centre (une fois par taille d'image)."""
    import numpy as np

    if (h, w) not in _GRID:
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        _GRID[(h, w)] = (xs - (w - 1) / 2, ys - (h - 1) / 2)
    return _GRID[(h, w)]


def depth_zoom_clip(image, depth, duration, amount, zoom_in=True):
    """Comme render.zoom_clip, mais le premier plan zoome un peu plus que le fond (relief)."""
    import cv2
    import numpy as np
    from moviepy import VideoClip

    from manhwa.render import _ease

    h, w = image.shape[:2]
    # gardée au quart de la taille (une case = 0,5 Mo au lieu de 8) : elle est très lisse de toute façon
    near = cv2.resize(depth, (w // 4, h // 4), interpolation=cv2.INTER_AREA).astype(np.float32)
    cx, cy = (w - 1) / 2, (h - 1) / 2

    def frame(t):
        p = _ease(t / duration) if duration else 0
        k = float(p if zoom_in else 1 - p)  # moviepy donne un temps numpy : on reste en float32 pour cv2.remap
        dx, dy = _grid(h, w)
        s = 1 + amount * k + amount * PARALLAX * k * cv2.resize(near, (w, h), interpolation=cv2.INTER_LINEAR)
        return cv2.remap(image, (cx + dx / s).astype(np.float32), (cy + dy / s).astype(np.float32), cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REFLECT101)

    return VideoClip(frame, duration=duration)
