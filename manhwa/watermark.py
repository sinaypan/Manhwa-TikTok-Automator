"""Les filigranes du site effacés de la planche (« ASURASCANS.COM » et son bandeau), les pages de pub sautées.

1. Les graines : les filigranes que la lecture du texte a déjà reconnus (bubbles.py, « watermark »).
2. Le modèle : le même filigrane revient sur des fonds différents. Calés les uns sur les autres, ce
   qui ne change pas d'une fois à l'autre est le filigrane : sa forme entière (bandeau, logo, texte),
   pas seulement les lettres lues. Il est gardé pour la série : un autre épisode du même site s'en sert.
3. La recherche : les lettres du modèle sont cherchées dans toute la planche, et chaque trouvaille
   douteuse est relue par l'OCR. Sur l'épisode 1 : les 15 filigranes lus, plus 2 que la lecture
   avait ratés, sans fausse alerte.
4. L'effacement : LaMa (entraîné sur 300 000 images de mangas ; MIT, version ONNX Apache 2.0,
   200 Mo) repeint la zone d'après ce qui l'entoure : 0,18 s par filigrane. Mesuré aussi : retirer
   le bandeau par le calcul (sa transparence estimée) laissait des fantômes de lettres.
5. Les pages de pub du site (« READ AT … FOR THE FASTEST RELEASES ») ne sont pas montrées.

Les morceaux repeints sont gardés dans .studio/watermarks/ et recollés sur la planche à chaque usage
(frames, rendu) : les pages d'origine ne sont jamais modifiées. Réglé dans config.toml, [watermark].
"""
import difflib
import json
import re

import cv2
import numpy as np

from manhwa.panels import STUDIO_DIR
from manhwa.project import fingerprint

WATERMARK_VERSION = 1
MODELS = {"lama_manga_dynamic.onnx": (
    "https://huggingface.co/ogkalu/lama-manga-onnx-dynamic/resolve/ee4ed4a8447b6730fc41d34f90876b6c48af925a/lama-manga-dynamic.onnx",
    "de31ffa5ba26916b8ea35319f6c12151ff9654d4261bccf0583a69bb095315f9")}
MIN_SEEDS = 3          # en dessous, pas de modèle : on efface seulement les lettres lues
LETTERS_SURE, LETTERS_MAYBE = 0.68, 0.50  # ressemblance des lettres : sûr ; à faire relire par l'OCR
PAD = 64               # px de contexte autour du filigrane pour LaMa
AD_SHARE = 0.1         # une case dont les crédits du site couvrent au moins 10 % : une pub
WATERMARK_TEXT = re.compile(r"scans?\b|\.com\b|\.net\b|\.org\b|read at|fastest release", re.IGNORECASE)
_SESSION = {}


def folder(chapter):
    return chapter.root / STUDIO_DIR / "watermarks"


def series_template_path(chapter):
    return chapter.root.parent / STUDIO_DIR / "watermark.npz"


# ---------- 1. Les graines ----------

def seeds(data):
    """Les filigranes lus par l'OCR, dans le repère de la planche : [(x, y, w, h, texte)]."""
    out = []
    for frame in data["frames"]:
        x, y = frame["crop"][:2]
        for b in frame.get("bubbles") or []:
            if b.get("kind") == "watermark":
                bx, by, bw, bh = b["box"]
                out.append((x + bx, y + by, bw, bh, b.get("text") or ""))
    return out


def is_ad(frame):
    """Une case de pub du site : rien à lire, et des crédits du site qui en couvrent une bonne part."""
    bubbles = frame.get("bubbles") or []
    if any(b.get("kind") == "dialogue" for b in bubbles):
        return False
    area = max(1, frame["crop"][2] * frame["crop"][3])
    credit = sum(b["box"][2] * b["box"][3] for b in bubbles if b.get("kind") in ("credit", "watermark"))
    return any(b.get("kind") == "credit" for b in bubbles) and credit / area >= AD_SHARE


# ---------- 2. Le modèle ----------

def _grab(strip, x0, y0, s, w, h):
    """La fenêtre w × h dont le coin est (x0, y0) dans la planche, à l'échelle s (hors planche : le bord répété)."""
    a, b = int(max(0, y0 - 4)), int(min(strip.shape[0], y0 + h * s + 4))
    if b <= a:
        return np.zeros((h, w, 3), np.uint8)
    m = np.float32([[s, 0, x0], [0, s, y0 - a]])
    return cv2.warpAffine(strip[a:b], m, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE)


def _locate(gray, tmpl, x, y, w, h, scales):
    """Où (et à quelle échelle) le texte tmpl se trouve près de la boîte lue : (score, échelle, x, y)."""
    best = (-1.0, 1.0, float(x), float(y))
    for s in scales:
        t = cv2.resize(tmpl, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        m = int(0.4 * max(w, t.shape[1])) + 10
        a0, b0 = max(0, y - m), max(0, x - m)
        area = gray[a0:y + h + m, b0:x + w + m]
        if area.shape[0] < t.shape[0] or area.shape[1] < t.shape[1]:
            continue
        _, v, _, loc = cv2.minMaxLoc(cv2.matchTemplate(area, t, cv2.TM_CCOEFF_NORMED))
        if v > best[0]:
            best = (float(v), float(s), float(b0 + loc[0]), float(a0 + loc[1]))
    return best


def learn(strip, found):
    """Le filigrane appris de ses graines : {median, std, mask, box}, ou None s'il y en a trop peu."""
    found = found[:16]
    if len(found) < MIN_SEEDS:
        return None
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    # la graine de référence : parmi celles de taille habituelle (une boîte lue trop large englobe autre
    # chose), celle qui ressemble le plus aux autres ; l'échelle de chacune est cherchée, pas devinée
    mw, mh = np.median([f[2] for f in found]), np.median([f[3] for f in found])
    typical = sorted(range(len(found)), key=lambda i: abs(found[i][2] / mw - 1) + abs(found[i][3] / mh - 1))[:5]
    best = None
    for r in typical:
        rx, ry, rw, rh, _ = found[r]
        tmpl = gray[max(0, ry - 2):ry + rh + 2, max(0, rx - 2):rx + rw + 2]
        at = [_locate(gray, tmpl, x, y, w, h, np.arange(0.75, 1.36, 0.02)) for x, y, w, h, _ in found]
        score = float(np.median([a[0] for a in at]))
        if best is None or score > best[0]:
            best = (score, r, at)
    _, r, at = best
    rx, ry, rw, rh, _ = found[r]
    L, R, T = 1.8 * rh, 1.0 * rh, 0.8 * rh  # le texte, avec la place d'un logo à gauche et d'une flèche à droite
    cw, ch = int(rw + L + R), int(rh + 2 * T)
    keep = [a for a in at if a[0] > 0.3]
    if len(keep) < MIN_SEEDS:
        return None
    # (x, y) : le coin du texte de référence (rogné 2 px plus large) ; la fenêtre commence L plus à gauche, T plus haut
    at = [(x + 2 * s - L * s, y + 2 * s - T * s, s) for _, s, x, y in keep]
    wins = np.array([_grab(strip, x, y, s, cw, ch) for x, y, s in at], np.float32)
    std = cv2.GaussianBlur(wins.std(axis=0).mean(axis=2), (5, 5), 0)
    u8 = np.clip(std / max(1e-3, np.percentile(std, 99)) * 255, 0, 255).astype(np.uint8)
    _, low = cv2.threshold(u8, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)  # ce qui ne change pas : le filigrane
    low = cv2.morphologyEx(low, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    low = cv2.morphologyEx(low, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(low)
    box = (int(L), int(T), int(rw), int(rh))
    text = np.zeros_like(low)
    text[box[1]:box[1] + box[3], box[0]:box[0] + box[2]] = 1
    mask = np.zeros_like(low)
    for k in range(1, n):  # les morceaux qui touchent le texte lu
        if (text[lab == k]).any():
            mask[lab == k] = 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    flood = mask.copy()
    cv2.floodFill(flood, np.zeros((ch + 2, cw + 2), np.uint8), (0, 0), 255)
    mask |= cv2.bitwise_not(flood)  # les trous à l'intérieur aussi
    if mask.mean() / 255 > 0.85 or not mask[box[1]:box[1] + box[3], box[0]:box[0] + box[2]].any():
        mask = np.zeros_like(low)  # rien de sûr : seulement le texte, un peu élargi
        mask[max(0, box[1] - 6):box[1] + box[3] + 6, max(0, box[0] - 6):box[0] + box[2] + 6] = 255
    return {"median": np.median(wins, axis=0).astype(np.uint8), "std": std.astype(np.float32), "mask": mask,
            "box": np.array(box), "at": np.array(at, np.float32)}


def save_template(path, t):
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **t)


def load_template(path):
    if not path.is_file():
        return None
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


# ---------- 3. La recherche ----------

CHUNK = 16384  # lignes de planche à la fois


def find(strip, t, verify=None, limit=40):
    """Les filigranes de la planche : [(x, y, score)], coin de la fenêtre du modèle (à l'échelle 1).

    On cherche les lettres du modèle (leur ressemblance tient malgré le fond qui transparaît), d'abord
    sur la planche réduite de moitié (4 fois plus vite), puis au pixel près. Mesuré sur l'épisode 1 :
    vrais filigranes de 0,56 à 0,84 ; des planches de bois ou des dents montent jusqu'à 0,62. Au-dessus
    de 0,68 c'est sûr ; entre 0,50 et 0,68, verify(x, y) fait relire l'OCR (les graines, déjà lues,
    sont gardées de toute façon).
    """
    ch, cw = t["mask"].shape
    bx, by, bw, bh = (int(v) for v in t["box"])
    m = 3
    letters = cv2.cvtColor(t["median"], cv2.COLOR_BGR2GRAY)[max(0, by - m):by + bh + m, max(0, bx - m):bx + bw + m]
    ox, oy = bx - min(m, bx), by - min(m, by)  # où commencent les lettres dans la fenêtre
    # la planche bordée : un filigrane coupé par le bord de la page se trouve aussi
    # (une bordure unie : recopier le bord ferait des rayures, que l'on prendrait pour des lettres)
    gray = cv2.copyMakeBorder(cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY), ch, ch, cw, cw, cv2.BORDER_CONSTANT, value=128)
    lh, lw = letters.shape
    H, W = strip.shape[:2]
    small, little = cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),         cv2.resize(letters, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    sh, sw = little.shape
    peaks = []
    for y0 in range(0, max(1, small.shape[0] - sh + 1), CHUNK // 2):
        part = small[y0:y0 + CHUNK // 2 + sh - 1]
        if part.shape[0] < sh:
            break
        r = np.nan_to_num(cv2.matchTemplate(part, little, cv2.TM_CCOEFF_NORMED), nan=0, posinf=0, neginf=0)
        while True:
            _, v, _, (x, y) = cv2.minMaxLoc(r)
            if v < LETTERS_MAYBE - 0.08:  # réduite, la ressemblance est un peu moins nette
                break
            r[max(0, y - sh):y + sh + 1, max(0, x - sw // 2):x + sw // 2 + 1] = 0
            X, Y = 2 * x, 2 * (y0 + y)  # au pixel près, sur la planche entière
            area = gray[max(0, Y - 6):Y + lh + 6, max(0, X - 6):X + lw + 6]
            if area.shape[0] < lh or area.shape[1] < lw:
                continue
            _, v, _, (dx, dy) = cv2.minMaxLoc(cv2.matchTemplate(area, letters, cv2.TM_CCOEFF_NORMED))
            if v >= LETTERS_MAYBE:
                peaks.append((float(v), max(0, X - 6) + dx - cw - ox, max(0, Y - 6) + dy - ch - oy))
    peaks.sort(reverse=True)
    out, asked = [], 0
    for v, x, y in peaks:
        inside = min(W, x + ox + lw) - max(0, x + ox)
        if inside < 0.6 * lw or any(abs(x - a) < cw // 2 and abs(y - b) < ch // 2 for a, b, _ in out):
            continue  # les lettres surtout hors de la page, ou le même filigrane déjà trouvé
        if v < LETTERS_SURE:
            if not verify or asked >= limit:
                continue
            asked += 1
            if not verify(x, y):
                continue
        out.append((int(x), int(y), round(v, 3)))
    return sorted(out, key=lambda f: f[1])


def ocr_check(strip, t, cfg, texts):
    """verify(x, y) : l'OCR lit-il un filigrane dans la fenêtre ? (le texte d'un site, ou celui des graines)."""
    from manhwa.ocr import read_crop_lines

    ch, cw = t["mask"].shape
    known = [s.lower() for s in texts if s]

    def verify(x, y):
        x0, y0 = max(0, x), max(0, y)
        crop = strip[y0:y + ch, x0:x + cw]
        if crop.size == 0:
            return False
        for line in read_crop_lines(crop, cfg):
            said = (line.get("text") or "").lower()
            if WATERMARK_TEXT.search(said) or any(difflib.SequenceMatcher(None, said, k).ratio() >= 0.6 for k in known):
                return True
        return False

    return verify


# ---------- 4. L'effacement ----------

def _lama():
    if "s" not in _SESSION:
        import onnxruntime as ort

        from manhwa.faces import ensure_models, models_dir
        from manhwa.gpu import onnx_providers

        ensure_models(MODELS)
        _SESSION["s"] = ort.InferenceSession(str(models_dir() / "lama_manga_dynamic.onnx"), providers=onnx_providers())
    return _SESSION["s"]


def inpaint(img, hole):
    """img (BGR) repeinte par LaMa là où hole > 0."""
    h, w = img.shape[:2]
    ph, pw = (-h) % 8, (-w) % 8
    im = cv2.copyMakeBorder(img, 0, ph, 0, pw, cv2.BORDER_REFLECT)
    mk = cv2.copyMakeBorder(hole, 0, ph, 0, pw, cv2.BORDER_REFLECT)
    x = cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255
    out = _lama().run(None, {"image": x, "mask": (mk > 0).astype(np.float32)[None, None]})[0][0].transpose(1, 2, 0)
    if out.max() <= 1.5:
        out = out * 255
    out = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)[:h, :w]
    res = img.copy()
    res[hole > 0] = out[hole > 0]
    return res


def erase(strip, x, y, mask, s=1.0):
    """Le morceau repeint pour un filigrane dont le masque (repère de la fenêtre, échelle s) commence en
    (x, y) : (x0, y0, image), ou None s'il tombe hors de la planche."""
    H, W = strip.shape[:2]
    x, y = int(round(x)), int(round(y))
    if abs(s - 1) > 1e-3:
        mask = cv2.resize(mask, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
    mh, mw = mask.shape
    hole = np.zeros((mh + 2 * PAD, mw + 2 * PAD), np.uint8)
    hole[PAD:PAD + mh, PAD:PAD + mw] = mask
    hole = cv2.dilate(hole, np.ones((9, 9), np.uint8))  # le contour du bandeau aussi : un reste ferait une tache
    X0, Y0 = x - PAD, y - PAD  # la zone avec son contexte, rognée à la planche
    a, b = max(0, Y0), min(H, Y0 + hole.shape[0])
    c, d = max(0, X0), min(W, X0 + hole.shape[1])
    if a >= b or c >= d:
        return None
    hole = hole[a - Y0:b - Y0, c - X0:d - X0]
    if not hole.any():
        return None
    done = inpaint(strip[a:b, c:d], hole)
    ys, xs = np.nonzero(hole)  # on ne garde que le rectangle repeint
    return c + xs.min(), a + ys.min(), done[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


# ---------- L'étape, et la planche nettoyée ----------

def run_watermarks(chapter, cfg, progress=None, force=False):
    """Efface les filigranes de la planche et réécrit les frames ; renvoie le nombre de filigranes effacés."""
    from manhwa.images import load_strip
    from manhwa.panels import build_frames, pages_key

    wm = cfg.get("watermark", {})
    if not wm.get("remove", True):
        return 0
    data = chapter.load()
    sc = cfg["slicer"]
    strip, _ = load_strip(chapter.pages(), sc["max_src_width"])
    if strip is None:
        return 0
    found = seeds(data)
    pkey = pages_key(chapter, sc["max_src_width"])
    key = fingerprint(WATERMARK_VERSION, pkey, [s[:4] for s in found], LETTERS_SURE, LETTERS_MAYBE)
    index = folder(chapter) / "index.json"
    if not force and (data["steps"].get("watermark") or {}).get("key") == key and index.is_file():
        return (data["steps"]["watermark"] or {}).get("removed", 0)
    t = learn(strip, found)
    if t is not None:  # gardé pour les autres épisodes de la série (sans les places de celui-ci)
        save_template(series_template_path(chapter), {k: v for k, v in t.items() if k != "at"})
    else:
        t = load_template(series_template_path(chapter))
    if t is not None:
        ch, cw = t["mask"].shape
        spots = [(x, y, t["mask"], float(s)) for x, y, s in t.get("at", [])]  # les graines, à leur échelle
        for x, y, _ in find(strip, t, ocr_check(strip, t, cfg, [s[4] for s in found])):
            if not any(abs(x - a) < cw // 2 and abs(y - b) < ch // 2 for a, b, _, _ in spots):
                spots.append((x, y, t["mask"], 1.0))
    else:  # trop peu de graines et pas de modèle pour la série : seulement les lettres lues
        spots = []
        for x, y, w, h, _ in found:
            m = int(0.35 * h)
            spots.append((x - m, y - m, np.full((h + 2 * m, w + 2 * m), 255, np.uint8), 1.0))
    out = folder(chapter)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    patches = []
    for i, (x, y, mask, s) in enumerate(spots):
        piece = erase(strip, x, y, mask, s)
        if piece is not None:
            px, py, img = piece
            name = f"{i:03d}.png"
            cv2.imwrite(str(out / name), img)
            patches.append({"file": name, "x": int(px), "y": int(py)})
        if progress:
            progress(i + 1, len(spots))
    index.write_text(json.dumps({"pages": pkey, "patches": patches}, indent=1), encoding="utf-8")
    data = chapter.load()
    data["steps"]["watermark"] = {"key": key, "removed": len(patches), "seeds": len(found),
                                  "ads": [f["file"] for f in data["frames"] if is_ad(f)]}
    chapter.save(data)
    build_frames(chapter, cfg)  # les frames refaites depuis la planche nettoyée (textes et voix gardés)
    print(f"  Filigranes : {len(patches)} effacés ({len(found)} lus par l'OCR)")
    return len(patches)


def clean(chapter, strip, cfg):
    """La planche avec les filigranes effacés (les morceaux repeints recollés), si l'étape est faite pour ces pages."""
    from manhwa.panels import pages_key

    if strip is None or not cfg.get("watermark", {}).get("remove", True):
        return strip
    index = folder(chapter) / "index.json"
    if not index.is_file():
        return strip
    info = json.loads(index.read_text(encoding="utf-8"))
    if info.get("pages") != pages_key(chapter, cfg["slicer"]["max_src_width"]) or not info.get("patches"):
        return strip
    strip = strip.copy()
    for p in info["patches"]:
        img = cv2.imread(str(folder(chapter) / p["file"]))
        if img is None:
            continue
        h, w = img.shape[:2]
        h, w = min(h, strip.shape[0] - p["y"]), min(w, strip.shape[1] - p["x"])
        if h > 0 and w > 0:
            strip[p["y"]:p["y"] + h, p["x"]:p["x"] + w] = img[:h, :w]
    return strip


def key(chapter):
    """Ce qui change la planche nettoyée (pour la clé du rendu)."""
    index = folder(chapter) / "index.json"
    return index.read_text(encoding="utf-8") if index.is_file() else None
