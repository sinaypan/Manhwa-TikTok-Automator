"""Le ton d'une réplique sans GPT : ponctuation et interjections.

Quand GPT n'a pas donné de ton (pas de clé), la voix n'est plus neutre partout :
    « ?! », « !? »                  → surpris
    question très courte (« WHAT? ») → surpris
    « HAHA », « KUKUK »             → moqueur ;  « UGH », « ARGH » → douleur
    exclamation très courte          → crie ;   longue → excité
    phrase qui traîne (« … »)        → pensée
Le ton de GPT, ou le tien, passe toujours devant (review.effective).
Le tout en majuscules ne compte pas : un manhwa est toujours en majuscules.
"""
import re

EMOTION_VERSION = 1
LAUGHS = re.compile(r"\b(HA){2,}H?\b|\bHEH(EH)*\b|\bKU(KU)+K?\b|\bHUHU\b|\bPFF+T?\b", re.IGNORECASE)
PAIN = re.compile(r"\b(UGH+|ARGH+|AAGH+|GAH+|KUH+|KEUK|CRAP)\b", re.IGNORECASE)


def guess(text):
    """Le ton probable d'une réplique (une clé de voices.EMOTIONS)."""
    t = text.strip()
    words = re.findall(r"[A-Za-z']+", t)
    short = len(words) <= 3
    if LAUGHS.search(t):
        return "mocking"
    if PAIN.search(t) and short:
        return "pain"
    if "?!" in t or "!?" in t:
        return "surprised"
    if "?" in t and short:
        return "surprised"
    if "!" in t and "?" not in t:
        return "shouting" if short else "excited"
    if (t.endswith("...") or t.endswith("…")) and "?" not in t and not short:
        return "thinking"
    return "neutral"
