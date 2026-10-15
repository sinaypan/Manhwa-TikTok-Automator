"""Des lignes OCR aux bulles : regroupement, ordre de lecture, tri dialogue / SFX / bruit.

Entrée : les lignes d'un moteur (manhwa/ocr_engines.py), dans le repère de la case.
Sortie : [{"text", "kind", "conf", "box"}] dans l'ordre de lecture, où kind vaut
    "dialogue"  à lire (bulles, pensées, narration) ;
    "sfx"       onomatopée (coréenne ou anglaise) : pas lue, servira aux bruitages ;
    "silent"    bulle de ponctuation seule (« ... », « ! ») : pas lue ;
    "noise"     1 à 4 lettres lues au hasard dans le dessin : pas lu ;
    "number"    chiffre seul (numéro de page, chiffre du décor) : pas lu ;
    "watermark" / "credit" / "title" : filigrane du site, page de crédits, titre de chapitre.
"""

BUBBLES_VERSION = 3  # à incrémenter quand le tri change : les bulles sont recalculées
                     # depuis les lignes OCR gardées, sans relire le chapitre
import re
import statistics

HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]")
WATERMARK = re.compile(r"asura\s*scans?|\.com\b|\.net\b|\.org\b", re.IGNORECASE)
CREDIT = re.compile(r"\b(read at|fastest releases?|discord|patreon|join us|translat(or|ed by)|proofread|typeset)", re.IGNORECASE)
TITLE = re.compile(r"^(prologue|epilogue|chapter\s*\d+|episode\s*\d+|side story)\W*$", re.IGNORECASE)
SFX_WORDS = {
    "bam", "boom", "pow", "crash", "bang", "slam", "thud", "wham", "whoosh", "swoosh", "swish",
    "krr", "krk", "tsk", "grr", "argh", "snap", "tap", "clack", "click", "ring", "ding", "buzz",
    "zip", "zap", "crack", "crunch", "thump", "rumble", "shff", "fwoosh", "whack", "smack", "clang",
}


def clean(text):
    """Petites corrections communes : espaces, apostrophes, « 1 » lu à la place de « I »."""
    t = re.sub(r"\s+", " ", text.replace("’", "'").replace("‘", "'")).strip()
    words = t.split()
    has_other_digits = any(ch.isdigit() for w in words if w != "1" for ch in w)
    letters = sum(w.isalpha() for w in words)
    if letters >= 2 and not has_other_digits:
        words = ["I" if w == "1" else w for w in words]
    return " ".join(words)


def line_kind(text):
    if HANGUL.search(text):
        return "sfx"
    if WATERMARK.search(text):
        return "watermark"
    if CREDIT.search(text):
        return "credit"
    if not re.search(r"[A-Za-z0-9]", text):
        return "silent"
    return None  # à décider au niveau de la bulle


def group(lines):
    """Regroupe les lignes proches (l'une sous l'autre, qui se chevauchent en largeur)."""
    n = len(lines)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        xi, yi, wi, hi = lines[i]["box"]
        for j in range(i + 1, n):
            xj, yj, wj, hj = lines[j]["box"]
            h = max(1, min(hi, hj))
            vgap = max(yi, yj) - min(yi + hi, yj + hj)  # négatif si elles se chevauchent
            overlap = min(xi + wi, xj + wj) - max(xi, xj)
            same_row = vgap < -0.5 * h  # se chevauchent de plus de la moitié en hauteur
            # l'une sous l'autre (même bulle), ou côte à côte sur la même ligne : un moteur rend
            # parfois chaque mot à part, et un « I » isolé passerait pour du bruit
            if (vgap < 0.9 * h and overlap > -0.3 * h) or (same_row and overlap > -1.5 * h):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(lines[i])
    return [in_rows(g) for g in groups.values()]


def in_rows(lines):
    """Ordre de lecture dans une bulle : par rangée, puis de gauche à droite.

    Un moteur rend parfois un mot à la fois ; un mot 1 px plus bas que son voisin ne
    doit pas passer devant lui (« DON'T ANY FEEL »).
    """
    rows = []
    for l in sorted(lines, key=lambda l: l["box"][1] + l["box"][3] / 2):
        center = l["box"][1] + l["box"][3] / 2
        if rows and abs(center - rows[-1]["center"]) < 0.5 * min(l["box"][3], rows[-1]["h"]):
            rows[-1]["items"].append(l)
        else:
            rows.append({"center": center, "h": l["box"][3], "items": [l]})
    return [l for row in rows for l in sorted(row["items"], key=lambda l: l["box"][0])]


def reading_order(bubbles):
    """De haut en bas ; deux bulles à la même hauteur se lisent de gauche à droite."""
    bubbles = sorted(bubbles, key=lambda b: b["box"][1])
    out = []
    for b in bubbles:
        out.append(b)
        k = len(out) - 1
        # remonte la bulle tant qu'elle est sur la même ligne qu'une bulle plus à droite
        while k > 0:
            prev = out[k - 1]
            same_row = b["box"][1] < prev["box"][1] + 0.5 * prev["box"][3]
            if same_row and b["box"][0] + b["box"][2] <= prev["box"][0]:
                out[k - 1], out[k] = out[k], out[k - 1]
                k -= 1
            else:
                break
    return out


NOISE_CONF = 0.7       # sous cette confiance, un mot isolé de 1 à 4 lettres est du bruit
HUGE_TEXT = 0.1        # lettres plus hautes que 10 % de la largeur de la case : onomatopée
TINY_TEXT = 0.015      # lettres plus petites que 1,5 % de la largeur : traits du dessin


def to_bubbles(lines, width, typical_height=None):
    """Lignes OCR d'une case de `width` px → bulles classées, dans l'ordre de lecture."""
    lines = [dict(l, text=clean(l["text"])) for l in lines if l["text"].strip()]
    if not lines:
        return []
    heights = [l["box"][3] for l in lines if line_kind(l["text"]) is None] or [l["box"][3] for l in lines]
    typical = typical_height or statistics.median(heights)

    bubbles = []
    for g in group(lines):
        kinds = [line_kind(l["text"]) for l in g]
        keep = [l for l, k in zip(g, kinds) if k is None]
        x0 = min(l["box"][0] for l in g)
        y0 = min(l["box"][1] for l in g)
        x1 = max(l["box"][0] + l["box"][2] for l in g)
        y1 = max(l["box"][1] + l["box"][3] for l in g)
        confs = [l["conf"] for l in g if l.get("conf") is not None]
        bubble = {"box": [x0, y0, x1 - x0, y1 - y0], "conf": round(min(confs), 3) if confs else None}

        if not keep:
            # toute la bulle est du bruit : on garde le type le plus parlant
            first = next(k for k in ("sfx", "watermark", "credit", "silent") if k in kinds)
            bubble.update(text=" ".join(l["text"] for l in g), kind=first)
        else:
            text = " ".join(l["text"] for l in keep)
            words = re.findall(r"[A-Za-z']+", text)
            height = statistics.median(l["box"][3] for l in keep)
            big = height > 2.2 * typical or height > HUGE_TEXT * width
            letters = sum(c.isalpha() for c in text)
            low_conf = bubble["conf"] is not None and bubble["conf"] < NOISE_CONF
            if CREDIT.search(text):
                kind = "credit"  # « READ AT … FOR THE FASTEST RELEASES » découpé en mots
            elif TITLE.match(text):
                kind = "title"
            elif not words and re.fullmatch(r"[\d\s.,:/-]+", text):
                kind = "number"  # chiffre seul : numéro de page, de chapitre, chiffre du décor
            elif height < TINY_TEXT * width:
                kind = "noise"  # minuscule (traits du dessin) : le dialogue fait 35 à 55 px de haut
            elif words and all(len(w.strip("'")) <= 1 for w in words) and not (bubble["conf"] or 0) >= 0.95:
                # que des lettres isolées (« I i i 2 », « N I I ») sans lecture quasi certaine
                kind = "sfx" if big else "noise"
            elif letters <= 4 and len(words) <= 2 and low_conf:
                # 1 à 4 lettres lues au hasard : en très gros, c'est un SFX coréen stylisé ;
                # en petit, une forme du dessin prise pour une lettre (bruit)
                kind = "sfx" if big else "noise"
            elif words and len(words) <= 3 and (
                all(w.lower().strip("'") in SFX_WORDS for w in words)
                # 1 à 3 mots en très gros ET lus avec hésitation ou lettres répétées (« KRAAAK ») ;
                # une bulle écrite gros mais nette (« A WISE CHOICE. ») reste du dialogue
                or big and ((bubble["conf"] is not None and bubble["conf"] < 0.9) or re.search(r"(.)\1\1", text))
            ):
                kind = "sfx"
            else:
                kind = "dialogue"
            bubble.update(text=text, kind=kind)
        bubbles.append(bubble)
    return reading_order(bubbles)


def spoken_text(bubbles):
    """Ce que la voix lit : les bulles de dialogue, dans l'ordre."""
    parts = [b["text"] for b in bubbles if b["kind"] == "dialogue"]
    return " ".join(parts) if parts else None
