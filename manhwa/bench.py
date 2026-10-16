"""Banc de mesure : ce que la machine décide seule, comparé à ce que tu as validé.

    python -m manhwa bench <chapitre> --freeze   fige tes décisions comme référence
    python -m manhwa bench <chapitre>            note chaque étape et garde l'historique

La référence (<chapitre>/.studio/gold.json) contient le texte de l'œuvre : comme
ocr_gold.json, elle n'est jamais commitée. Elle prend ce que le Studio sait de tes choix :
le type et le texte des bulles après relecture, qui parle, les groupes de visages, le ton
et les sons choisis. Chaque mesure compare la proposition automatique (sans tes
corrections) à cette référence ; un module du PLAN_V3 n'entre que s'il fait mieux.

Une étape peut recevoir sa propre fonction de prédiction (predict=…) : c'est ainsi qu'un
nouveau module se compare à l'actuel sans toucher au chapitre.
"""
import difflib
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime

from manhwa.config import ROOT
from manhwa.ocr_bench import words
from manhwa.panels import STUDIO_DIR

GOLD_FILE = "gold.json"
HISTORY_FILE = "bench_history.json"
DETAILS_FILE = "bench_details.json"
STEPS = ("kinds", "text", "speakers", "faces", "emotion", "sounds")
STEP_LABELS = {"kinds": "Type de bulle", "text": "Texte", "speakers": "Qui parle", "faces": "Visages",
               "emotion": "Ton", "sounds": "Sons"}
THRESHOLDS = (0.1, 0.2, 0.3, 0.5)  # confiance à partir de laquelle on validerait d'office


def _path(chapter, name):
    return chapter.root / STUDIO_DIR / name


def load_gold(chapter):
    path = _path(chapter, GOLD_FILE)
    if not path.is_file():
        raise RuntimeError(f"Pas de référence : lance d'abord « bench {chapter.root.name} --freeze ».")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- La référence ----------

def freeze(chapter):
    """Fige tes décisions actuelles comme référence. Renvoie ce qui a été gardé, par étape."""
    from manhwa import sfx
    from manhwa.cast import chapter_faces
    from manhwa.review import effective

    data = chapter.load()
    bubbles = {}
    for frame in data["frames"]:
        reviews = frame.get("review") or {}
        speakers = frame.get("speakers") or {}
        for b in effective(frame):  # après la relecture : ce que tu as accepté ou gardé
            r = reviews.get(b["orig"]) or {}
            bubbles[f"{frame['file']}#{b['index']}"] = {
                "orig": b["orig"], "kind": b["kind"], "text": b["text"], "speaker": speakers.get(b["orig"]),
                "emotion": r.get("emotion"), "emotion_by": "user" if r.get("emotion_by") == "user" else ("gpt" if r.get("emotion") else None),
            }
    faces = {f["id"]: ("not_face" if f.get("not_face") else f.get("char")) for f in chapter_faces(data)}
    sounds = {s["key"]: s["sound"] for s in sfx.spots(data) + sfx.silent_frames(data) if s["chosen"]}
    gold = {"frozen": datetime.now().isoformat(timespec="seconds"), "frames": len(data["frames"]),
            "bubbles": bubbles, "faces": faces, "sounds": sounds}
    path = _path(chapter, GOLD_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"bulles": len(bubbles), "qui parle": sum(1 for b in bubbles.values() if b["speaker"]),
            "visages": sum(1 for v in faces.values() if v), "tons": sum(1 for b in bubbles.values() if b["emotion"]),
            "sons": len(sounds)}


def _pairs(data, gold):
    """(clé, frame, bulle brute, référence) des bulles dont le texte lu n'a pas changé depuis."""
    for frame in data["frames"]:
        for j, b in enumerate(frame.get("bubbles") or []):
            g = gold["bubbles"].get(f"{frame['file']}#{j}")
            if g and g["orig"] == b["text"]:
                yield f"{frame['file']}#{j}", frame, b, g


def _pct(ok, n):
    return round(ok / n, 3) if n else None


# ---------- Les mesures ----------

def _local(data, chapter=None):
    """La correction locale (textfix.py) telle que la chaîne l'applique, bulle par bulle."""
    from manhwa.textfix import local_fix, protected_words

    texts = [b["text"] for f in data["frames"] for b in f.get("bubbles") or []]
    protected = protected_words(chapter, texts)
    return lambda b: local_fix(b, protected)


def score_kinds(data, gold, predict=None, chapter=None):
    """Type de bulle : règles de lecture (bubbles.py) + charabia repéré (textfix.py), sans relecture."""
    from manhwa.review import SPOKEN

    if predict is None:
        fix = _local(data, chapter)
        predict = lambda frame, b: fix(b)[1]
    rows = [(key, predict(frame, b), g["kind"], b["text"]) for key, frame, b, g in _pairs(data, gold)]
    wrong = [r for r in rows if r[1] != r[2]]
    heard = [r for r in wrong if (r[1] in SPOKEN) != (r[2] in SPOKEN)]  # lu alors qu'il ne faut pas, ou l'inverse
    confusion = Counter(f"{p} → {g}" for _, p, g, _ in wrong)
    return ({"justes": _pct(len(rows) - len(wrong), len(rows)), "bulles": len(rows), "erreurs": len(wrong),
             "erreurs qui s'entendent": len(heard), "confusions": dict(confusion.most_common(6))},
            [{"bulle": k, "proposé": p, "attendu": g, "texte": t} for k, p, g, t in wrong])


def score_text(data, gold, predict=None, chapter=None, propose=None):
    """Texte des répliques lues : OCR + corrections locales sûres, comparé au texte validé.

    propose : ce qui serait corrigé si tu acceptes aussi les propositions (à valider).
    """
    from manhwa.review import SPOKEN

    if predict is None:
        fix = _local(data, chapter)
        sure = lambda b: (lambda t, k, ch: t if all(c["sure"] for c in ch) else b["text"])(*fix(b))
        predict = lambda frame, b: sure(b)
        propose = propose or (lambda frame, b: fix(b)[0])
    exact, hit, total, todo, fixed, broken, errors = 0, 0, 0, 0, 0, 0, []
    for key, frame, b, g in _pairs(data, gold):
        if g["kind"] not in SPOKEN:
            continue
        want, got = words(g["text"]), words(predict(frame, b))
        same = want == got
        exact += same
        total += len(want)
        hit += sum(m.size for m in difflib.SequenceMatcher(None, want, got, autojunk=False).get_matching_blocks())
        needs = words(b["text"]) != want  # l'OCR seul se trompait ici
        todo += needs
        fixed += needs and same
        broken += (not needs) and not same  # une bonne phrase abîmée par la correction
        if not same:
            errors.append({"bulle": key, "lu": predict(frame, b), "attendu": g["text"]})
    n = exact + len(errors)
    report = {"répliques exactes": _pct(exact, n), "mots justes": _pct(hit, total), "répliques": n,
              "à corriger": todo, "corrigées": fixed, "abîmées": broken}
    if propose:
        both = [(words(g["text"]), words(propose(frame, b)), words(b["text"]))
                for _, frame, b, g in _pairs(data, gold) if g["kind"] in SPOKEN]
        report["corrigées si tu acceptes les propositions"] = sum(w == p != r for w, p, r in both)
        report["abîmées si tu acceptes"] = sum(w == r != p for w, p, r in both)
    return report, errors


def score_speakers(data, gold, crew, predict=None):
    """Qui parle : la proposition (visage le plus proche…), avec tes visages rangés."""
    from manhwa.cast import lines

    by_key = {l["key"]: l for l in lines(data, crew)}
    predict = predict or (lambda line: (line["suggestion"], line.get("confidence")))
    rows = []
    for key, _, _, g in _pairs(data, gold):
        line = by_key.get(key)
        if not line or not g["speaker"]:
            continue
        guess, conf = predict(line)
        rows.append((key, guess, g["speaker"], conf, g["speaker"] in line["candidates"], line["kind"], line["text"]))
    ok = [r for r in rows if r[1] == r[2]]
    by_kind = defaultdict(lambda: [0, 0])
    for r in rows:
        by_kind[r[5]][0] += r[1] == r[2]
        by_kind[r[5]][1] += 1
    auto = {}
    for t in THRESHOLDS:  # ce que le pilote validerait seul, et combien de fois il aurait raison
        sure = [r for r in rows if r[3] is not None and r[3] >= t]
        auto[f"≥ {t}"] = {"part": _pct(len(sure), len(rows)), "justes": _pct(sum(r[1] == r[2] for r in sure), len(sure))}
    return ({"justes": _pct(len(ok), len(rows)), "répliques": len(rows),
             "dans les 4 proposés": _pct(sum(r[4] for r in rows), len(rows)),
             "par type": {k: _pct(a, b) for k, (a, b) in by_kind.items()}, "validé d'office si confiance": auto},
            [{"bulle": k, "proposé": p, "attendu": g, "confiance": c, "texte": t} for k, p, g, c, _, _, t in rows if p != g])


def score_faces(chapter, data, gold, embed=None, threshold=None):
    """Visages : regroupés de zéro (sans tes corrections), comparés à tes groupes.

    embed(chemin de la vignette) → vecteur : pour essayer un autre modèle sur les mêmes têtes.
    """
    import numpy as np

    from manhwa.cast import _load_vectors, chapter_faces, faces_dir
    from manhwa.faces import MATCH, cluster

    labels = {fid: lab for fid, lab in gold["faces"].items() if lab}  # visages rangés ou écartés
    if embed:
        vecs = {}
        for fid in labels:
            path = faces_dir(chapter) / f"{fid}.jpg"
            if path.is_file():
                v = np.asarray(embed(path), np.float32)
                vecs[fid] = v / (np.linalg.norm(v) + 1e-9)
    else:
        vecs = _load_vectors(chapter)
    ids = [f["id"] for f in chapter_faces(data) if f["id"] in labels and f["id"] in vecs]
    groups = cluster([vecs[i] for i in ids], threshold or MATCH)
    moves, errors, majority = 0, [], {}
    for g in groups:
        names = Counter(labels[ids[k]] for k in g)
        top = names.most_common(1)[0][0] if len(g) >= 2 else None  # un visage seul reste à ranger
        for k in g:
            if labels[ids[k]] != top and labels[ids[k]] != "not_face":
                moves += 1
                errors.append({"visage": ids[k], "groupe": top, "attendu": labels[ids[k]]})
        if top and top != "not_face":
            majority.setdefault(top, []).append(len(g))
    rejects = sum(1 for g in groups if len(g) >= 2 for k in g if labels[ids[k]] == "not_face")
    same_auto = {(a, b) for g in groups for a in g for b in g if a < b}
    real = [(a, b) for a in range(len(ids)) for b in range(a + 1, len(ids))
            if labels[ids[a]] == labels[ids[b]] != "not_face"]
    tp = sum(1 for p in real if p in same_auto)
    auto_pairs = [p for p in same_auto if labels[ids[p[0]]] != "not_face"]
    return ({"visages": len(ids), "à déplacer": moves, "formes à écarter": rejects,
             "groupes à fusionner": sum(len(v) - 1 for v in majority.values()),
             "paires retrouvées": _pct(tp, len(real)), "paires justes": _pct(tp, len(auto_pairs))}, errors)


def score_emotion(data, gold, predict=None):
    """Ton deviné sans GPT (ponctuation, emotion.py) ; la référence est le ton de GPT, ou le tien."""
    from manhwa.emotion import guess
    from manhwa.review import SPOKEN

    predict = predict or (lambda frame, b, g: guess(b["text"]))
    rows = [(key, predict(frame, b, g), g["emotion"], g["emotion_by"], g["text"])
            for key, frame, b, g in _pairs(data, gold) if g["kind"] in SPOKEN and g["emotion"]]
    mine = [r for r in rows if r[3] == "user"]
    return ({"justes": _pct(sum(r[1] == r[2] for r in rows), len(rows)), "répliques": len(rows),
             "dont choisis par toi": len(mine), "justes sur les tiens": _pct(sum(r[1] == r[2] for r in mine), len(mine)),
             "répartition": dict(Counter(r[2] for r in rows).most_common(6))},
            [{"bulle": k, "proposé": p, "attendu": g, "texte": t} for k, p, g, _, t in rows if p != g])


def score_sounds(chapter, data, gold):
    """Sons : la proposition d'après l'image (et GPT), comparée aux sons que tu as choisis."""
    from manhwa import sfx
    from manhwa.scene import load_scene

    seen = load_scene(chapter)
    items = {s["key"]: s for s in sfx.spots(data, seen) + sfx.silent_frames(data, seen)}
    rows = [(k, items[k]["proposed"], want, want in items[k]["recs"] or (want == sfx.NONE))
            for k, want in gold["sounds"].items() if k in items]
    with_sound = [r for r in rows if r[2] != sfx.NONE]
    return ({"choisis": len(rows), "même son proposé (dans la vidéo sans toi)": _pct(sum(r[1] == r[2] for r in rows), len(rows)),
             "dans les 3 proposés": _pct(sum(r[3] for r in rows), len(rows)), "avec un son": len(with_sound)},
            [{"son": k, "proposé": p, "attendu": w} for k, p, w, _ in rows if p != w])


# ---------- Tout le banc ----------

def _commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _versions():
    from manhwa.bubbles import BUBBLES_VERSION
    from manhwa.faces import FACES_VERSION
    from manhwa.scene import SCENE_VERSION
    from manhwa.textfix import TEXTFIX_VERSION

    return {"bubbles": BUBBLES_VERSION, "faces": FACES_VERSION, "scene": SCENE_VERSION, "textfix": TEXTFIX_VERSION}


def run_bench(chapter, steps=None, save=True):
    """{étape: mesures}, et le détail des erreurs dans .studio/bench_details.json."""
    from manhwa.cast import load_cast

    gold = load_gold(chapter)
    data = chapter.load()
    crew = load_cast(chapter)
    steps = steps or STEPS
    runs = {
        "kinds": lambda: score_kinds(data, gold, chapter=chapter),
        "text": lambda: score_text(data, gold, chapter=chapter),
        "speakers": lambda: score_speakers(data, gold, crew),
        "faces": lambda: score_faces(chapter, data, gold),
        "emotion": lambda: score_emotion(data, gold),
        "sounds": lambda: score_sounds(chapter, data, gold),
    }
    report, details = {}, {}
    for step in steps:
        report[step], details[step] = runs[step]()
    if save:
        _path(chapter, DETAILS_FILE).write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
        history = previous_runs(chapter)
        history.append({"date": datetime.now().isoformat(timespec="seconds"), "commit": _commit(),
                        "versions": _versions(), "gold": gold["frozen"], "report": report})
        _path(chapter, HISTORY_FILE).write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def previous_runs(chapter):
    path = _path(chapter, HISTORY_FILE)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
