"""Lecture du texte de chaque frame : moteur OCR → bulles → texte à lire.

Le moteur se choisit dans config.toml ([ocr] engine) : « paddle » par défaut, le meilleur
au banc d'essai du chapitre 1 de Myst Might Mayhem (100 % des mots attendus, 0 mot en
trop, contre 71 % pour l'ancien Tesseract filtré). « windows » est 30× plus rapide mais
se trompe sur le texte stylisé ; « tesseract » reste disponible.

L'OCR se fait sur le crop d'origine dans le strip, pas sur la frame 9:16 (plus net).
Chaque frame garde ses bulles (dialogue, SFX, filigrane…) : les SFX serviront aux bruitages.
"""
import cv2

from manhwa.bubbles import spoken_text, to_bubbles
from manhwa.images import border_color, load_strip
from manhwa.ocr_engines import read_lines
from manhwa.project import fingerprint

OCR_VERSION = 4  # v4 : marge autour du crop + mots d'une même ligne regroupés
WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def read_bubbles(crop, cfg):
    """Bulles d'un crop. Le crop est d'abord entouré d'une marge de la couleur de son bord :
    une case rognée au ras des lettres (« THAT IS HOW HE DIED. ») est mal détectée sinon."""
    h, w = crop.shape[:2]
    pad = max(24, round(0.04 * w))
    color = border_color(crop) or (255, 255, 255)
    padded = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=color)
    lines = read_lines(padded, cfg)
    for line in lines:  # positions ramenées dans le repère du crop
        line["box"] = [line["box"][0] - pad, line["box"][1] - pad, line["box"][2], line["box"][3]]
    return to_bubbles(lines, w)


def read_text(crop, cfg):
    """Ce que la voix lira pour ce crop, ou None (rien à lire)."""
    return spoken_text(read_bubbles(crop, cfg))


def ocr_key(frame, data, cfg):
    return fingerprint(OCR_VERSION, frame["crop"], data.get("strip"), cfg["ocr"].get("engine", "paddle"))


def run_ocr(chapter, cfg, force=False, progress=None):
    """Lit le texte des frames qui ne l'ont pas encore (ou dont le crop a changé).

    progress(faites, total) est appelé après chaque frame (pour le Studio).
    """
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
    for done, frame in enumerate(todo, start=1):
        x, y, w, h = frame["crop"]
        bubbles = read_bubbles(strip[y:y + h, x:x + w], cfg)
        frame["bubbles"] = bubbles
        frame["text"] = spoken_text(bubbles)
        frame["ocr_key"] = ocr_key(frame, data, cfg)
        sfx = [b["text"] for b in bubbles if b["kind"] == "sfx"]
        if frame["text"]:
            found += 1
            print(f"  [OK] {frame['file']} | {frame['text'][:70]}")
        else:
            print(f"  [--] {frame['file']} | (rien à lire)")
        if sfx:
            print(f"       SFX : {', '.join(sfx)[:60]}")
        if progress:
            progress(done, len(todo))
        if done % 10 == 0:
            chapter.save(data)  # l'OCR est long : on ne perd rien en cas d'arrêt
    chapter.save(data)
    print(f"  OCR : {found} textes trouvés sur {len(todo)} frames relues.")
    return len(todo)
