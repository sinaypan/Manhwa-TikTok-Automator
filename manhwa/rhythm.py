"""Le rythme entre les répliques : pas le même petit blanc partout, comme un vrai dialogue.

    même personnage qui continue     un blanc court
    un autre répond                  un peu plus long ; une réponse à une question vient vite
    deux personnages en colère       le second coupe la parole (les voix se chevauchent un peu)
    après une réplique triste, « … » une vraie pause
    avant une longue réplique        une petite respiration

Les durées sont en secondes, avant l'accélération de la vidéo ([render] speed).
"""
import re

LOUD = {"shouting", "angry"}
SLOW = {"sad", "pain", "thinking", "whisper", "cold"}


def _words(seg):
    return len(re.findall(r"[A-Za-z']+", (seg or {}).get("text") or ""))


def _text(seg):
    return ((seg or {}).get("text") or "").strip()


def gap(prev, nxt):
    """Le blanc entre deux répliques d'une même case (négatif : la seconde coupe la parole)."""
    same = prev.get("speaker") == nxt.get("speaker")
    if same:
        g = 0.06 if _words(nxt) <= 2 else 0.12
    elif prev.get("emotion") in LOUD and nxt.get("emotion") in LOUD:
        return -0.06  # dispute : on se coupe la parole
    elif _text(prev).endswith("?"):
        g = 0.2
    else:
        g = 0.3
    if prev.get("emotion") in SLOW or _text(prev).endswith(("...", "…")):
        g += 0.18
    if _words(nxt) >= 14:
        g += 0.08  # on respire avant une longue réplique
    return g


def tail(last, following=None):
    """Le silence après la dernière réplique d'une case, avant la suivante."""
    if following and following.get("speaker") == last.get("speaker") and last.get("emotion") not in SLOW:
        t = 0.12  # il continue sur la case suivante
    else:
        t = 0.2
    if last.get("emotion") in LOUD | {"surprised", "scared"} or _text(last).endswith("!"):
        t = max(t, 0.32)  # on laisse le cri retomber
    if last.get("emotion") in SLOW or _text(last).endswith(("...", "…")):
        t = max(t, 0.42)
    return t
