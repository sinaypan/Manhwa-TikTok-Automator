"""Banc d'essai OCR : compare les moteurs à une vérité de référence lue à la main.

La référence est dans <chapitre>/.studio/ocr_gold.json (jamais commitée : ce sont les
dialogues de l'œuvre) : pour quelques frames, le texte que la voix doit lire.

Mesures, sur les mots (majuscules, sans ponctuation) :
- rappel    : part des mots attendus qui sont bien lus ;
- précision : part des mots lus qui sont justes ;
- en trop   : mots lus sur des frames où il n'y a rien à lire (SFX, filigranes…).
Calculées sur le texte brut du moteur, puis sur ce que la voix lirait après le tri en
bulles (manhwa/bubbles.py).
"""
import difflib
import json
import re
import time

from manhwa.bubbles import spoken_text
from manhwa.images import load_strip
from manhwa.ocr import read_bubbles
from manhwa.ocr_engines import ENGINES
from manhwa.panels import STUDIO_DIR

GOLD_FILE = "ocr_gold.json"


def words(text):
    return re.findall(r"[A-Z0-9']+", (text or "").upper().replace("’", "'"))


def match(expected, got):
    """(mots justes, mots attendus, mots lus) dans l'ordre (alignement de séquences)."""
    e, g = words(expected), words(got)
    ok = sum(block.size for block in difflib.SequenceMatcher(None, e, g, autojunk=False).get_matching_blocks())
    return ok, len(e), len(g)


def run_bench(chapter, cfg, engines=None):
    gold_path = chapter.root / STUDIO_DIR / GOLD_FILE
    if not gold_path.is_file():
        raise RuntimeError(f"Pas de référence : {gold_path}")
    gold = json.loads(gold_path.read_text(encoding="utf-8"))["frames"]
    data = chapter.load()
    strip, _ = load_strip(chapter.pages(), data["strip"]["max_width"])
    engines = engines or list(ENGINES)

    report, details = {}, {}
    for name in engines:
        totals = {"raw": [0, 0, 0], "spoken": [0, 0, 0]}
        junk = {"raw": 0, "spoken": 0}
        elapsed = 0.0
        for number, expected in gold.items():
            frame = data["frames"][int(number) - 1]
            x, y, w, h = frame["crop"]
            t = time.time()
            cfg = {**cfg, "ocr": {**cfg["ocr"], "engine": name}}
            bubbles = read_bubbles(strip[y:y + h, x:x + w], cfg)  # exactement comme le pipeline
            elapsed += time.time() - t
            lines = [{"text": b["text"], "box": b["box"]} for b in bubbles]
            raw = " ".join(l["text"] for l in sorted(lines, key=lambda l: (l["box"][1], l["box"][0])))
            spoken = spoken_text(bubbles) or ""
            target = " ".join(expected["read"])
            for kind, got in (("raw", raw), ("spoken", spoken)):
                ok, n_exp, n_got = match(target, got)
                totals[kind] = [a + b for a, b in zip(totals[kind], (ok, n_exp, n_got))]
                if not expected["read"]:
                    junk[kind] += n_got
            details.setdefault(number, {"attendu": target})[name] = {
                "lu_par_la_voix": spoken, "bulles": [(b["kind"], b["text"]) for b in bubbles]}
        report[name] = {
            kind: {
                "rappel": round(ok / n_exp, 3) if n_exp else None,
                "precision": round(ok / n_got, 3) if n_got else None,
                "mots_en_trop": junk[kind],
            }
            for kind, (ok, n_exp, n_got) in totals.items()
        } | {"secondes_par_frame": round(elapsed / len(gold), 2)}

    out = chapter.root / STUDIO_DIR / "ocr_bench.json"
    out.write_text(json.dumps({"resume": report, "frames": details}, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, out
