"""Sous-titres karaoké : la réplique par petits morceaux, le mot dit en couleur.

Chaque réplique est coupée en groupes de quelques mots (comme sur TikTok) ; pendant un
groupe, le mot prononcé passe en jaune. Le moment de chaque mot vient de Whisper quand la
réplique a déjà été réécoutée (segment["words"], manhwa/listen.py), sinon il est réparti
sur la durée de la voix selon la longueur des mots (une virgule ou un point marque une
petite pause).

Réglages dans config.toml → [render] : captions (true / false), captions_words (mots par
groupe), captions_font (vide = une police grasse de Windows), captions_size.
"""
import bisect
import os
import re
import threading

import numpy as np

FONTS = ("impact.ttf", "ariblk.ttf", "arialbd.ttf", "segoeuib.ttf")
COLOR = (255, 255, 255)
SPOKEN = (255, 214, 10)   # le mot en train d'être dit
STROKE = (0, 0, 0)
WORD = re.compile(r"\S+")


def font_path(cfg):
    wanted = (cfg["render"].get("captions_font") or "").strip()
    if wanted and os.path.isfile(wanted):
        return wanted
    folder = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in FONTS:
        if os.path.isfile(os.path.join(folder, name)):
            return os.path.join(folder, name)
    return None


def word_times(text, duration, heard=None):
    """[(mot, début, fin)] dans la réplique (secondes depuis le début de sa voix).

    heard : [[mot, début, fin]] de Whisper ; gardé s'il y a autant de mots, sinon on répartit.
    """
    words = WORD.findall(text)
    if not words or duration <= 0:
        return []
    if heard and len(heard) == len(words):
        return [(w, float(s), float(e)) for w, (_, s, e) in zip(words, heard)]
    weights = [len(re.sub(r"\W", "", w)) + 1.5 + (2.5 if w[-1] in ".!?…," else 0) for w in words]
    total = sum(weights)
    out, t = [], 0.0
    for w, k in zip(words, weights):
        d = duration * k / total
        out.append((w, t, t + d))
        t += d
    return out


def groups(timed, size=4, max_chars=24):
    """Les mots par groupes à afficher ensemble (au plus `size` mots ou `max_chars` lettres)."""
    out, cur = [], []
    for item in timed:
        if cur and (len(cur) >= size or sum(len(w) + 1 for w, _, _ in cur) + len(item[0]) > max_chars):
            out.append(cur)
            cur = []
        cur.append(item)
        if item[0][-1] in ".!?…":  # une phrase finie : nouveau groupe
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def events(lines, size=4):
    """lines : [(texte, début dans la vidéo, durée de la voix, mots de Whisper)].

    Renvoie [(début, fin, [mots du groupe], index du mot dit)] triés par début.
    """
    out = []
    for text, start, duration, heard in lines:
        for g in groups(word_times(text, duration, heard), size):
            words = [w for w, _, _ in g]
            for k, (_, s, e) in enumerate(g):
                end = g[k + 1][1] if k + 1 < len(g) else e
                out.append((start + s, start + end, words, k))
    out.sort(key=lambda x: x[0])
    return out


def draw(words, spoken, width, font_file, size):
    """Le groupe de mots en RGBA, centré, le mot dit en jaune, sur une ou deux lignes."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(font_file, size) if font_file else ImageFont.load_default()
    stroke = max(2, size // 12)
    space = font.getlength(" ")
    lines, cur, w = [], [], 0.0
    for k, word in enumerate(words):
        lw = font.getlength(word)
        if cur and w + space + lw > width * 0.86:
            lines.append(cur)
            cur, w = [], 0.0
        cur.append((k, word, lw))
        w += (space if len(cur) > 1 else 0) + lw
    if cur:
        lines.append(cur)
    line_h = int(size * 1.2)
    img = Image.new("RGBA", (width, line_h * len(lines) + 2 * stroke), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for row, line in enumerate(lines):
        total = sum(lw for _, _, lw in line) + space * (len(line) - 1)
        x = (width - total) / 2
        for k, word, lw in line:
            d.text((x, row * line_h + stroke), word, font=font, fill=SPOKEN if k == spoken else COLOR,
                   stroke_width=stroke, stroke_fill=STROKE)
            x += lw + space
    return np.array(img)


def burn(clip, evts, cfg, y):
    """Incruste les sous-titres dans la vidéo (seulement la bande où ils sont : plus rapide
    qu'un calque sur toute l'image)."""
    size = int(cfg["render"].get("captions_size", 78))
    font_file = font_path(cfg)
    width = clip.size[0]
    starts = [e[0] for e in evts]
    cache = {}
    lock = threading.Lock()  # plusieurs images peuvent se calculer en même temps (render.write_video)

    def caption(t):
        i = bisect.bisect_right(starts, t) - 1
        if i < 0 or t >= evts[i][1]:
            return None
        with lock:
            return _cached(i)

    def _cached(i):
        if i not in cache:
            if len(cache) > 4:
                cache.clear()
            img = draw(evts[i][2], evts[i][3], width, font_file, size)
            ys, xs = np.nonzero(img[:, :, 3])  # seulement le rectangle du texte : le reste de la bande est vide
            if not len(xs):
                cache[i] = None
            else:
                y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
                cut = img[y0:y1, x0:x1]
                cache[i] = (y0, x0, cut[:, :, :3].astype(np.float32), cut[:, :, 3:4].astype(np.float32) / 255.0)
        return cache[i]

    def frame(get_frame, t):
        out = get_frame(t)
        cap = caption(t)
        if cap is None:
            return out
        dy, x0, rgb, alpha = cap
        top = y + dy
        h = min(rgb.shape[0], out.shape[0] - top)
        if h <= 0:
            return out
        out = out.copy()  # l'image peut être gardée ailleurs (visages qui parlent) : on n'écrit pas dedans
        w = rgb.shape[1]
        band = out[top:top + h, x0:x0 + w].astype(np.float32)
        out[top:top + h, x0:x0 + w] = (band * (1 - alpha[:h]) + rgb[:h] * alpha[:h]).astype(np.uint8)
        return out

    return clip.transform(frame)
