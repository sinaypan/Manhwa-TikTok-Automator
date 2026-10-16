"""Correction du texte lu, en local, sans GPT : seulement les mots que l'OCR a ratés.

On ne touche qu'aux mots absents du dictionnaire (fréquences de pyspellchecker) et jamais
aux noms de la série (personnages, wiki) ni aux mots qui reviennent dans le chapitre
(un terme du monde, comme « Murim », revient ; une erreur de lecture, rarement).

    sûr (appliqué d'office)        mots collés « IDON'T » → « I DON'T », « WASA » → « WAS A » ;
                                   lettres perdues en fin de bulle « ANYMORE. S E » ;
                                   casse d'une bulle en majuscules « BuT It » → « BUT IT »
    à valider (onglet Relecture)   un mot inconnu à une lettre près d'un mot courant :
                                   « AWAK » → « AWAKE », « TAS » → « WAS », « Colden » → « Golden »
                                   (un mot connu, même rare comme « HERB » ou « YIKES », est gardé)

Le charabia (« a A A 9 CAE A A ») est repéré aussi : la bulle passe en « pas du texte ».
Les corrections vont dans frame["review"] comme celles de GPT (by: "local") : elles se
voient, s'annulent et se changent dans l'onglet Relecture.
"""
import re
from collections import Counter

TEXTFIX_VERSION = 1
KNOWN = 50_000          # fréquence d'un mot « courant » (morceau d'un mot collé)
NEAR = 20_000           # fréquence minimale du mot proposé à une lettre près
SUFFIXES = {"s", "re", "ll", "ve", "d", "t", "m"}  # YOU'RE, IT'LL, WE'VE, HE'D, DON'T, I'M
SINGLE = {"I", "A"}     # les seules lettres seules qui sont des mots
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
END = re.compile(r"[.!?…]['\"”)]*$")

_FREQ = None


def _freq():
    global _FREQ
    if _FREQ is None:
        from spellchecker import SpellChecker

        _FREQ = SpellChecker().word_frequency
    return _FREQ


def frequency(word):
    """Fréquence d'un mot ; une contraction compte comme son mot (« YOU'RE » → « you »)."""
    w = word.lower()
    f = _freq()[w]
    if "'" not in w:
        return f
    base, _, suffix = w.partition("'")  # « you're » est rare dans le dictionnaire, « you » non
    return max(f, _freq()[base] if suffix in SUFFIXES else 0)


def protected_words(chapter=None, texts=()):
    """Les mots à ne jamais corriger : noms du casting et du wiki, mots qui reviennent."""
    out = set()
    if chapter is not None:
        from manhwa.cast import load_cast, series_dir
        from manhwa.ingest.wiki import load_wiki

        crew = load_cast(chapter)
        names = [c.get("name") or "" for c in crew["characters"]]
        wiki = load_wiki(series_dir(chapter)) or {}
        names += [p.get("title") or "" for p in wiki.get("characters") or []]
        names.append(chapter.root.parent.name)  # le titre de la série (« Myst Might Mayhem »)
        out |= {w.upper() for n in names for w in WORD.findall(n)}
    unknown = Counter(w.upper() for t in texts for w in WORD.findall(t) if not frequency(w))
    # un mot collé (« WASA » deux fois) reste une erreur de lecture, même s'il revient
    out |= {w for w, n in unknown.items() if n >= 2 and len(w) >= 3 and not _split(w)}
    return out


def _split(word):
    """« IDON'T » → ["I", "DON'T"] si le mot se coupe en mots courants, sinon None."""
    best, score = None, 0
    for i in range(1, len(word)):
        a, b = word[:i], word[i:]
        for parts in ([a, b], *([a, b[:j], b[j:]] for j in range(1, len(b)))):
            if any(p.startswith("'") or p.endswith("'") for p in parts):
                continue
            ok = all((p.upper() in SINGLE) if len(p) == 1 else frequency(p) >= KNOWN for p in parts)
            if ok:
                s = min(frequency(p) for p in parts) / len(parts)  # deux morceaux plutôt que trois
                if s > score:
                    best, score = parts, s
    return best


def _near(word, last=False):
    """Pour un mot inconnu : le mot courant à une lettre près.

    last : dernier mot de la bulle, qui a pu perdre sa dernière lettre au bord (« AWAK ») ;
    on préfère alors le mot qui le complète.
    """
    from spellchecker import SpellChecker

    w = word.lower()
    if frequency(w) or len(w) < 3:
        return None
    options = [c for c in SpellChecker(distance=1).edit_distance_1(w) if _freq()[c] >= NEAR]
    if not options:
        return None
    # une lettre perdue au bord de la bulle (« AWAK ») est plus fréquente qu'une lettre changée
    return max(options, key=lambda c: (last and c.startswith(w), _freq()[c]))


def _style(new, old, upper):
    if upper or old.isupper():
        return new.upper()
    if old[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


def fix_text(text, protected=frozenset()):
    """(texte corrigé, [{"from", "to", "sure"}]) ; texte inchangé si rien n'est sûr ni probable."""
    letters = [c for c in text if c.isalpha()]
    upper = bool(letters) and sum(c.isupper() for c in letters) >= 0.7 * len(letters)
    changes = []

    def one(m):
        word = m.group(0)
        if word.upper() in protected or frequency(word) or (len(word) == 1 and word.upper() in SINGLE):
            return word
        parts = _split(word)
        if parts:
            new = " ".join(_style(p, word, upper) for p in parts)
            changes.append({"from": word, "to": new, "sure": True})
            return new
        near = _near(word, last=not WORD.search(text, m.end()))
        if near:
            new = _style(near, word, upper)
            changes.append({"from": word, "to": new, "sure": False})
            return new
        return word

    out = WORD.sub(one, text)
    # lettres perdues après la fin de la phrase : « ANYMORE. S E »
    tail = re.match(r"^(.*?[.!?…]['\"”)]*)((?:\s+[A-Za-z])+)\s*$", out)
    if tail and all(t.upper() not in SINGLE for t in tail.group(2).split()):
        changes.append({"from": tail.group(2).strip(), "to": "", "sure": True})
        out = tail.group(1)
    if upper and out != out.upper():
        changes.append({"from": "casse", "to": "MAJUSCULES", "sure": True})
        out = out.upper()
    return out, changes


def is_gibberish(text):
    """Des lettres lues au hasard dans le dessin : « a A A 9 CAE A A », « AAA9CAEAAA »."""
    tokens = text.split()
    words = WORD.findall(text)
    long_real = [w for w in words if len(w) >= 3 and frequency(w) >= KNOWN]
    if long_real:
        return False
    singles = [t for t in tokens if len(t) == 1 and t.isalpha()]
    digits_in_letters = any(c.isdigit() for c in text) and any(c.isalpha() for c in text)
    repeated = any(n >= 3 for n in Counter(s.upper() for s in singles).values())
    mixed = any(re.search(r"[A-Za-z]\d|\d[A-Za-z]", t) for t in tokens)
    return len(text.replace(" ", "")) >= 4 and (repeated or mixed or (digits_in_letters and len(singles) >= 2))


# ---------- Le chapitre ----------

def local_fix(bubble, protected):
    """Ce que la couche locale ferait d'une bulle brute : (texte, type, changements)."""
    from manhwa.review import SPOKEN

    if bubble["kind"] not in SPOKEN:
        return bubble["text"], bubble["kind"], []
    if is_gibberish(bubble["text"]):
        return bubble["text"], "noise", [{"from": bubble["text"], "to": "pas du texte", "sure": True}]
    text, changes = fix_text(bubble["text"], protected)
    return text, bubble["kind"], changes


def run_textfix(chapter, cfg=None, progress=None):
    """Écrit les corrections locales dans frame["review"], sans écraser une décision déjà prise."""
    data = chapter.load()
    texts = [b["text"] for f in data["frames"] for b in f.get("bubbles") or []]
    protected = protected_words(chapter, texts)
    n = 0
    for frame in data["frames"]:
        reviews = frame.setdefault("review", {})
        for b in frame.get("bubbles") or []:
            r = reviews.get(b["text"])
            if r and (r.get("by") != "local" or r.get("checked")):
                continue  # GPT ou toi êtes passés par là : on n'y touche pas
            text, kind, changes = local_fix(b, protected)
            if not changes:
                if r:
                    del reviews[b["text"]]  # une ancienne correction locale qui n'a plus lieu d'être
                continue
            sure = all(c["sure"] for c in changes)
            state = dict((r or {}).get("state") or {})
            entry = {"text": text, "kind": kind, "speaker": None, "emotion": (r or {}).get("emotion"),
                     "by": "local", "changes": changes, "version": TEXTFIX_VERSION}
            for field, changed in (("text", text != b["text"]), ("kind", kind != b["kind"])):
                if changed and state.get(field) not in ("accepted", "rejected"):
                    state[field] = "accepted" if sure else "pending"
                elif not changed:
                    state.pop(field, None)
            entry["state"] = state
            reviews[b["text"]] = entry
            n += 1
    chapter.save(data)
    print(f"  Correction locale : {n} bulles retouchées.")
    return n
