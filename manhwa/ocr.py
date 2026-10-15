"""OCR Tesseract (V1) : lit le texte de chaque frame découpée.

Temporaire : remplacé par l'OCR local (détecteur de bulles + PaddleOCR) en phase 2.
L'OCR se fait sur le crop d'origine dans le strip, pas sur la frame 9:16 (plus net).
"""
import os
import re
import shutil

import cv2
from PIL import Image

from manhwa.images import load_strip
from manhwa.project import fingerprint

OCR_VERSION = 2  # à incrémenter si les filtres changent, pour refaire l'OCR
WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

STRICT = {
    "min_chars": 6,             # pour garder "WAKE UP!"
    "min_words": 2,             # dialogue minimal
    "min_avg_conf": 68,         # bulles petites
    "min_letters_ratio": 0.65,  # apostrophes / !!
    "max_punct_ratio": 0.35,    # tolère "!?',."
    "max_digit_ratio": 0.10,
}

SFX_BLACKLIST = {
    "bam", "boom", "pow", "crash", "bang", "slam", "thud", "wham", "whoosh", "swoosh",
    "krr", "krk", "tsk", "ugh", "ahh", "hah", "ha", "hm", "hmm", "mm", "grr", "argh",
    "snap", "tap", "clack", "click", "ring", "ding", "buzz", "zip", "zap",
}

_configured = False


def _pytesseract(cfg):
    """Import paresseux + chemin de tesseract : config, sinon PATH, sinon emplacement Windows."""
    global _configured
    import pytesseract

    if not _configured:
        cmd = cfg["ocr"].get("tesseract_cmd") or shutil.which("tesseract")
        if not cmd and os.path.isfile(WINDOWS_TESSERACT):
            cmd = WINDOWS_TESSERACT
        if not cmd:
            raise RuntimeError(
                "Tesseract introuvable. Installe-le (https://github.com/UB-Mannheim/tesseract/wiki) "
                "ou indique son chemin dans config.toml → [ocr] tesseract_cmd."
            )
        pytesseract.pytesseract.tesseract_cmd = cmd
        _configured = True
    return pytesseract


def preprocess(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def normalize_text(s):
    s = re.sub(r"\s+", " ", s.replace("\n", " ")).strip()
    return s.replace("—", "-").replace("–", "-").replace("…", "...")


def looks_like_sfx(text):
    t = text.strip()
    if not t:
        return True
    low = re.sub(r"[^a-zA-Z\s]", "", t).lower().strip()
    if any(w in SFX_BLACKLIST for w in low.split()):
        return True
    # SFX typique : un seul mot court
    if len(t.split()) == 1 and len(re.sub(r"[^A-Za-z]", "", t)) <= 6:
        return True
    if re.search(r"(.)\1\1\1", t):
        return True
    non_alnum = sum(not c.isalnum() and not c.isspace() for c in t)
    return non_alnum / len(t) > 0.45


def pass_strict_rules(text, avg_conf):
    t = normalize_text(text)
    if len(t) < STRICT["min_chars"]:
        return False
    words = t.split()
    # Exception dialogue : 2+ mots avec une bonne confiance, même tout en majuscules
    if len(words) >= 2 and avg_conf >= STRICT["min_avg_conf"] and not looks_like_sfx(t):
        return True
    if looks_like_sfx(t):
        return False

    total = len(t)
    letters = sum(c.isalpha() for c in t)
    digits = sum(c.isdigit() for c in t)
    punct = sum(not c.isalnum() and not c.isspace() for c in t)
    return (
        letters / total >= STRICT["min_letters_ratio"]
        and digits / total <= STRICT["max_digit_ratio"]
        and punct / total <= STRICT["max_punct_ratio"]
        and len(words) >= STRICT["min_words"]
        and avg_conf >= STRICT["min_avg_conf"]
    )


def read_text(crop, cfg):
    """Texte du crop, ou None si c'est du bruit / un SFX.

    image_to_data donne une confiance par mot : on ne garde que les mots fiables,
    puis on filtre le résultat (SFX, trop court, trop de symboles).
    """
    pytesseract = _pytesseract(cfg)
    tess_config = f"--oem 1 --psm {cfg['ocr']['psm']}"
    try:
        data = pytesseract.image_to_data(
            Image.fromarray(preprocess(crop)),
            lang=cfg["ocr"]["lang"],
            config=tess_config,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as e:
        print(f"[OCR] Erreur : {e}")
        return None

    tokens, confs = [], []
    for raw, conf in zip(data["text"], data["conf"]):
        txt = (raw or "").strip()
        if not txt:
            continue
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = -1.0
        one_letter_word = txt.strip(".,!?'\"").upper() in ("I", "A")  # "I", "A" sont de vrais mots
        if conf < 60 or (sum(c.isalpha() for c in txt) < 2 and not one_letter_word) or re.search(r"(.)\1\1\1", txt):
            continue
        tokens.append(txt)
        confs.append(conf)

    if not tokens:
        return None
    text = normalize_text(" ".join(tokens))
    avg_conf = sum(confs) / len(confs)
    if avg_conf < STRICT["min_avg_conf"] or not pass_strict_rules(text, avg_conf):
        return None
    return text


def ocr_key(frame, data, cfg):
    return fingerprint(OCR_VERSION, frame["crop"], data.get("strip"), cfg["ocr"]["lang"], cfg["ocr"]["psm"])


def run_ocr(chapter, cfg, force=False):
    """Lit le texte des frames qui ne l'ont pas encore (ou dont le crop a changé)."""
    data = chapter.load()
    frames = data["frames"]
    if not frames:
        print("  Aucune frame : lance d'abord la découpe.")
        return 0

    todo = [f for f in frames if force or f.get("ocr_key") != ocr_key(f, data, cfg)]
    if not todo:
        print(f"  OCR déjà à jour ({len(frames)} frames).")
        return 0

    strip, _ = load_strip(chapter.pages(), data["strip"]["max_width"])
    if strip is None:
        print("  Pages introuvables : impossible de relire les crops.")
        return 0
    if [strip.shape[1], strip.shape[0]] != [data["strip"]["width"], data["strip"]["height"]]:
        print("  [!] Les pages ont changé depuis la découpe : refais la découpe de ce chapitre.")
        return 0

    found = 0
    for frame in todo:
        x, y, w, h = frame["crop"]
        frame["text"] = read_text(strip[y:y + h, x:x + w], cfg)
        frame["ocr_key"] = ocr_key(frame, data, cfg)
        if frame["text"]:
            found += 1
            print(f"  [OK] {frame['file']} | {frame['text'][:70]}")
        else:
            print(f"  [--] {frame['file']} | (rien / bruit)")
    chapter.save(data)
    print(f"  OCR : {found} textes trouvés sur {len(todo)} frames relues.")
    return len(todo)
