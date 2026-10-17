"""Relecture par GPT-4.1 : texte corrigé, type de bulle, qui parle, émotion, catégorie de bruitage.

GPT ne touche à rien directement : ses propositions sont rangées dans frame["review"],
par texte d'origine de la bulle (elles survivent à une nouvelle découpe du même texte) :

    {"BUT THE MOTHER WASN'T": {
        "text": "…", "kind": "dialogue", "speaker": "c1" | "narrator" | None,
        "emotion": "sad", "sfx": "glass" | None,
        "state": {"text": "pending" | "accepted" | "rejected", "kind": …, "speaker": …}}}

L'émotion est appliquée tout de suite (elle ne change que le ton) ; le texte, le type et
le personnage attendent qu'on les valide dans le Studio (onglet Relecture).
"""
import json

from manhwa.emotion import guess
from manhwa.voices import EMOTIONS

SPOKEN = ("dialogue", "thought", "narration")      # lus par une voix
KINDS = SPOKEN + ("sfx", "noise")
SENT_KINDS = ("dialogue", "sfx", "noise")          # bulles envoyées à GPT (pas les filigranes, crédits…)
SFX_CATEGORIES = ("impact", "punch", "slash", "glass", "wood", "explosion", "whoosh", "footsteps", "door",
                  "magic", "scream", "groan", "laugh", "heartbeat", "thunder", "rain", "fire", "wind", "other")
FIELDS = ("text", "kind", "speaker")
CHUNK = 45     # répliques par appel
CONTEXT = 8    # répliques d'avant redonnées pour le contexte


def effective(frame):
    """Les bulles de la frame avec les corrections acceptées (texte, type) et l'émotion."""
    reviews = frame.get("review") or {}
    out = []
    for j, b in enumerate(frame.get("bubbles") or []):
        r = reviews.get(b["text"]) or {}
        state = r.get("state") or {}
        # le ton : celui de GPT ou le tien, sinon deviné sur la ponctuation (emotion.py)
        e = dict(b, orig=b["text"], index=j, emotion=r.get("emotion") or guess(b["text"]), sfx=r.get("sfx"))
        if state.get("text") == "accepted" and r.get("text"):
            e["text"] = r["text"]
        if state.get("kind") == "accepted" and r.get("kind") in KINDS:
            e["kind"] = r["kind"]
        out.append(e)
    return out


def is_spoken(bubble):
    return bubble["kind"] in SPOKEN


# ---------- Appel à GPT ----------

RULES = [
    "text: fix ONLY OCR mistakes (wrong or missing letters, odd case like 'sO...' -> 'SO...', merged or split words, "
    "stray characters). Keep the wording, punctuation and ALL CAPS style. If the line is fine, return it unchanged.",
    "kind: dialogue (spoken aloud), thought (inner monologue), narration (caption box, narrator), "
    "sfx (sound effect, onomatopoeia, grunt drawn in the art), noise (OCR garbage that is not real text).",
    "speaker: one label from the characters list, 'narrator', or 'unknown'. faces_in_panel lists who is drawn in that "
    "panel (a face is not always the speaker). Keep a confirmed speaker unless it is clearly wrong.",
    f"emotion: one of {list(EMOTIONS)}.",
    f"sfx: only for kind sfx, one of {list(SFX_CATEGORIES)}; otherwise null.",
    "Return every line id you were given, in the same order. Lines in context_before are only context: do not return them.",
]


def _items(data, crew, labels):
    """Les bulles à relire, dans l'ordre du chapitre."""
    from manhwa.cast import chapter_faces, lines

    by_key = {l["key"]: l for l in lines(data, crew)}
    faces = {}
    for f in chapter_faces(data):
        if f.get("char") in labels and not f.get("not_face"):
            faces.setdefault(f["frame"], set()).add(labels[f["char"]])
    items = []
    for i, frame in enumerate(data["frames"]):
        for b in effective(frame):
            if b["kind"] not in SENT_KINDS + SPOKEN or (b["kind"] == "noise" and sum(c.isalpha() for c in b["orig"]) < 2):
                continue
            key = f"{frame['file']}#{b['index']}"
            line = by_key.get(key)
            speaker = line and (line["speaker"] or line["suggestion"])
            items.append({
                "id": key,
                "panel": i + 1,
                "text": b["orig"],
                "ocr_confidence": b.get("conf"),
                "kind": b["kind"],
                "speaker": labels.get(speaker) or ("narrator" if speaker == "narrator" else None),
                "speaker_confirmed": bool(line and line["speaker"]),
                "faces_in_panel": sorted(faces.get(frame["file"], ())),
            })
    return items


def character_sheet(crew, wiki):
    """Les personnages tels que GPT les voit : nom, genre, caractère (du wiki)."""
    pages = {w["id"]: w for w in (wiki or {}).get("characters", [])}
    sheet = []
    for i, c in enumerate(crew["characters"]):
        page = pages.get(c.get("wiki")) or {}
        sheet.append({
            "label": c["name"] or f"Perso {i + 1}",
            "gender": page.get("gender") or None,
            "about": (page.get("personality") or "")[:300] or ("unnamed" if not c["name"] else None),
            "never_speaks": bool(c.get("silent")) or None,
        })
    return sheet


def ask(items, context, sheet, series, chapter_no):
    from manhwa.llm import chat

    prompt = {"series": series, "chapter": chapter_no, "characters": sheet, "rules": RULES,
              "context_before": context, "lines": items,
              "answer_format": {"lines": [{"id": "…", "text": "…", "kind": "…", "speaker": "…", "emotion": "…", "sfx": None}]}}
    answer = chat([
        {"role": "system", "content": "You proofread OCR of an English manhwa scanlation and annotate each line for dubbing. Answer only with JSON."},
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ], max_tokens=8000)
    return {str(x.get("id")): x for x in answer.get("lines", []) if isinstance(x, dict)}


def run_review(chapter, cfg, progress=None, force=False):
    """Relit tout le chapitre avec GPT et range ses propositions (sans rien appliquer d'autre que l'émotion)."""
    from manhwa.cast import NARRATOR, chapter_number, load_cast, series_dir
    from manhwa.ingest.wiki import load_wiki

    data = chapter.load()
    crew = load_cast(chapter)
    labels = {c["id"]: c["name"] or f"Perso {i + 1}" for i, c in enumerate(crew["characters"])}
    by_label = {v.lower(): k for k, v in labels.items()}
    items = _items(data, crew, labels)
    if not items:
        print("  Rien à relire : crée d'abord la vidéo (lecture du texte).")
        return 0
    sheet = character_sheet(crew, load_wiki(series_dir(chapter)))
    answers = {}
    chunks = range(0, len(items), CHUNK)
    for n, start in enumerate(chunks, 1):
        part = items[start:start + CHUNK]
        context = [{"text": x["text"], "speaker": x["speaker"]} for x in items[max(0, start - CONTEXT):start]]
        answers.update(ask(part, context, sheet, series_dir(chapter).name, chapter_number(chapter)))
        if progress:
            progress(n, len(chunks))

    data = chapter.load()  # relu : on a pu valider des choses pendant l'appel
    frames = {f["file"]: f for f in data["frames"]}
    changed = 0
    for item in items:
        got = answers.get(item["id"])
        file, _, index = item["id"].partition("#")
        frame = frames.get(file)
        if not got or not frame or int(index) >= len(frame.get("bubbles") or []):
            continue
        orig = frame["bubbles"][int(index)]["text"]
        speaker = str(got.get("speaker") or "").strip().lower()
        proposal = {
            "text": " ".join(str(got.get("text") or orig).split()) or orig,
            "kind": got.get("kind") if got.get("kind") in KINDS else item["kind"],
            "speaker": NARRATOR if speaker == "narrator" else by_label.get(speaker),
            "emotion": got.get("emotion") if got.get("emotion") in EMOTIONS else "neutral",
            "sfx": got.get("sfx") if got.get("sfx") in SFX_CATEGORIES else None,
        }
        reviews = frame.setdefault("review", {})
        old = reviews.get(orig) or {}
        if old.get("checked"):  # vérifiée à la main (« Toutes les bulles ») : GPT ne la change plus
            reviews[orig] = {**old, "emotion": old.get("emotion") or proposal["emotion"],
                             "sfx": old.get("sfx") or proposal["sfx"]}
            changed += 1
            continue
        state = {}
        current = {"text": orig, "kind": frame["bubbles"][int(index)]["kind"],
                   "speaker": (frame.get("speakers") or {}).get(orig)}
        spoken = proposal["kind"] in SPOKEN or current["kind"] in SPOKEN
        for field in FIELDS:
            if proposal[field] in (None, current[field]) or (field == "kind" and {proposal[field], current[field]} <= {"dialogue"}):
                continue
            if field != "kind" and not spoken:
                continue  # « MAth » → « MATH » sur un SFX coréen illisible : sans intérêt, il n'est pas lu
            # même proposition qu'avant : on garde ce que l'utilisateur en a décidé
            same = old.get(field) == proposal[field]
            state[field] = (old.get("state") or {}).get(field, "pending") if same and not force else "pending"
        if old.get("emotion_by") == "user":
            proposal["emotion"], proposal["emotion_by"] = old["emotion"], "user"
        if old.get("mine"):  # ta propre version (texte, type) reste, acceptée
            for field in ("text", "kind"):
                if (old.get("state") or {}).get(field) == "accepted" and not force:
                    proposal[field], state[field] = old[field], "accepted"
            proposal["mine"] = True
        reviews[orig] = {**proposal, "state": state}
        changed += 1
    chapter.save(data)
    print(f"  Relecture : {changed} bulles annotées, {sum(len(r['state']) for f in data['frames'] for r in (f.get('review') or {}).values())} propositions.")
    return changed


# ---------- Décisions ----------

def proposals(data, crew):
    """Les propositions de GPT à valider : [{"key", "frame", "field", "old", "new", "state", "box", "crop"}]."""
    from manhwa.cast import EXTRAS, NARRATOR

    labels = {c["id"]: c["name"] or f"Perso {i + 1}" for i, c in enumerate(crew["characters"])}
    labels[NARRATOR] = "Narrateur"
    labels.update({k: v[0] for k, v in EXTRAS.items()})
    out = []
    for frame in data["frames"]:
        reviews = frame.get("review") or {}
        for j, b in enumerate(frame.get("bubbles") or []):
            r = reviews.get(b["text"])
            if not r:
                continue
            for field, state in (r.get("state") or {}).items():
                old = {"text": b["text"], "kind": b["kind"], "speaker": (frame.get("speakers") or {}).get(b["text"])}[field]
                new = r.get(field)
                if state == "pending" and new == old:
                    continue  # déjà ainsi (tu as choisi la même chose entre-temps) : rien à décider
                out.append({
                    "key": f"{frame['file']}#{j}", "frame": frame["file"], "field": field, "state": state,
                    "by": r.get("by") or ("mine" if r.get("mine") else "gpt"),
                    "auto": field in (r.get("auto") or []),
                    "old": labels.get(old, old) if field == "speaker" else old,
                    "new": labels.get(new, new) if field == "speaker" else new,
                    "text": b["text"], "box": b["box"], "crop": frame["crop"],
                })
    return out


def decide(data, decisions):
    """decisions : [{"key", "field", "state": "accepted" | "rejected" | "pending", "value"?}].

    value (avec "accepted") : ta propre version au lieu de celle de GPT (un texte, ou un type de bulle).
    """
    frames = {f["file"]: f for f in data["frames"]}
    n = 0
    for d in decisions:
        file, _, index = str(d.get("key", "")).partition("#")
        frame = frames.get(file)
        if not frame or not index.isdigit() or int(index) >= len(frame.get("bubbles") or []):
            continue
        orig = frame["bubbles"][int(index)]["text"]
        r = (frame.get("review") or {}).get(orig)
        field, state = d.get("field"), d.get("state")
        if not r or field not in (r.get("state") or {}) or state not in ("accepted", "rejected", "pending"):
            continue
        value = d.get("value")
        if state == "accepted" and value is not None:
            if field == "text" and isinstance(value, str) and value.strip() and len(value) <= 500:
                r["text"] = " ".join(value.split())
                r["mine"] = True  # ta version : une nouvelle relecture ne l'écrase pas
            elif field == "kind" and value in KINDS:
                r["kind"] = value
                r["mine"] = True
            else:
                continue
        r["state"][field] = state
        if field in (r.get("auto") or []) and not d.get("_auto"):
            r["auto"].remove(field)  # ta décision remplace celle du pilote
        if field == "speaker":
            speakers = frame.setdefault("speakers", {})
            if state == "accepted" and r.get("speaker"):
                speakers[orig] = r["speaker"]
        n += 1
    return n


# ---------- Toutes les bulles, vérifiées à la main ----------

def _locate(data, key):
    file, _, index = str(key).partition("#")
    frame = next((f for f in data["frames"] if f["file"] == file), None)
    if not frame or not index.isdigit() or int(index) >= len(frame.get("bubbles") or []):
        raise ValueError("Bulle introuvable")
    return frame, frame["bubbles"][int(index)]


def all_bubbles(data):
    """Chaque bulle du chapitre, telle que la voix la traitera : texte, type, vérifiée ou non."""
    out = []
    for frame in data["frames"]:
        reviews = frame.get("review") or {}
        for b in effective(frame):
            r = reviews.get(b["orig"]) or {}
            out.append({"key": f"{frame['file']}#{b['index']}", "frame": frame["file"], "orig": b["orig"],
                        "text": b["text"], "kind": b["kind"], "box": b["box"], "crop": frame["crop"],
                        "checked": bool(r.get("checked"))})
    return out


def check_bubble(data, key, text=None, kind=None, checked=None):
    """Ta vérification d'une bulle : son vrai texte, son vrai type, et « c'est bon »."""
    frame, bubble = _locate(data, key)
    orig = bubble["text"]
    r = frame.setdefault("review", {}).setdefault(orig, {"state": {}})
    state = r.setdefault("state", {})
    if r.get("by") == "local":
        r["by"] = "mine"  # une correction locale que tu as revue devient la tienne
    if text is not None:
        text = " ".join(str(text).split())
        if not text or len(text) > 500:
            raise ValueError("Texte vide ou trop long")
        if text != orig:
            r["text"], state["text"], r["mine"] = text, "accepted", True
        elif "text" in state:
            state["text"] = "rejected"  # le texte lu était le bon : la correction proposée est refusée
    if kind is not None:
        if kind not in KINDS:
            raise ValueError("Type de bulle inconnu")
        if kind != bubble["kind"]:
            r["kind"], state["kind"], r["mine"] = kind, "accepted", True
        elif "kind" in state:
            state["kind"] = "rejected"
        if kind not in SPOKEN:  # plus lue : ses propositions de texte et de « qui parle » n'ont plus lieu d'être
            for field in ("text", "speaker"):
                if state.get(field) == "pending":
                    state[field] = "rejected"
    if checked is not None:
        r["checked"] = bool(checked)


def set_emotion(data, key, emotion):
    if emotion not in EMOTIONS:
        raise ValueError("Émotion inconnue")
    file, _, index = str(key).partition("#")
    frame = next((f for f in data["frames"] if f["file"] == file), None)
    if not frame or not index.isdigit() or int(index) >= len(frame.get("bubbles") or []):
        raise ValueError("Réplique introuvable")
    orig = frame["bubbles"][int(index)]["text"]
    r = frame.setdefault("review", {}).setdefault(orig, {"state": {}})
    r["emotion"], r["emotion_by"] = emotion, "user"
