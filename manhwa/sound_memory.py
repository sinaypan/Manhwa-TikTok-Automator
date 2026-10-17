"""Les sons appris de tes choix : une case qui ressemble à celles où tu as mis du sang aura du sang.

SigLIP 2 (Google, Apache 2.0, version ONNX allégée) résume chaque case en un vecteur. Pour une
case à sonoriser, on cherche les cases les plus proches parmi celles où tu as déjà choisi un son
(tous les épisodes de inbox/), et on propose le son qu'elles ont eu le plus souvent : plus tu
valides d'épisodes, plus la proposition te ressemble.

Les vecteurs des cases sont gardés dans <chapitre>/.studio/siglip.npz (refaits si la découpe change).
"""
import hashlib

import numpy as np

from manhwa.panels import STUDIO_DIR

MODEL = {"siglip2_vision_fp16.onnx": (
    "https://huggingface.co/onnx-community/siglip2-base-patch16-224-ONNX/resolve/main/onnx/vision_model_fp16.onnx",
    "a1959f7bd3993a607e48839f6d01e25b876fe76afda301b028b78eef68aabd95")}
K = 7          # les 7 cases les plus proches votent
NEIGHBOURS = 2  # à l'essai, on ne regarde pas les cases voisines (même scène : trop facile)
_S = {}


def _session():
    if "s" not in _S:
        import onnxruntime as ort

        from manhwa.faces import ensure_models, models_dir
        from manhwa.gpu import onnx_providers

        ensure_models(MODEL)
        _S["s"] = ort.InferenceSession(str(models_dir() / next(iter(MODEL))), providers=onnx_providers())
    return _S["s"]


def _pixels(img):
    import cv2

    rgb = cv2.cvtColor(cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    return ((rgb.astype(np.float32) / 255 - 0.5) / 0.5).transpose(2, 0, 1)


def embed(crop):
    """Le vecteur d'une case (moyenne de ses morceaux carrés, comme scene.tiles), normalisé."""
    from manhwa.scene import tiles

    s = _session()
    inp = s.get_inputs()[0]
    batch = np.stack([_pixels(t) for t in tiles(crop)]).astype(np.float16 if "16" in inp.type else np.float32)
    outs = s.run(None, {inp.name: batch})
    names = [o.name for o in s.get_outputs()]
    v = outs[names.index("pooler_output")] if "pooler_output" in names else outs[-1]
    v = v.astype(np.float32)
    if v.ndim == 3:
        v = v.mean(axis=1)
    v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
    m = v.mean(axis=0)
    return m / (np.linalg.norm(m) + 1e-9)


def _key(frame):
    return hashlib.sha1(str(frame["crop"]).encode()).hexdigest()[:10]


def frame_vectors(chapter, cfg=None, progress=None):
    """{fichier: vecteur} de chaque case du chapitre (gardés ; seulement les nouvelles sont calculées)."""
    from manhwa.config import load_config
    from manhwa.images import load_strip

    path = chapter.root / STUDIO_DIR / "siglip.npz"
    data = chapter.load()
    old = {}
    if path.is_file():
        with np.load(path) as z:
            old = {k: z[k] for k in z.files}
    want = {f"{f['file']}|{_key(f)}": f for f in data["frames"]}
    todo = [k for k in want if k not in old]
    if todo:
        cfg = cfg or load_config()
        strip, _ = load_strip(chapter.pages(), cfg["slicer"]["max_src_width"])
        for i, k in enumerate(todo):
            x, y, w, h = want[k]["crop"]
            old[k] = embed(strip[y:y + h, x:x + w])
            if progress:
                progress(i + 1, len(todo))
        keep = {k: v for k, v in old.items() if k in want}
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **keep)
        old = keep
    return {k.split("|")[0]: v for k, v in old.items() if k in want}


def examples(chapters, cfg=None):
    """Tes choix de sons (tous les chapitres) : [(chapitre, index de case, vecteur, son, bulle ?)]."""
    from manhwa import sfx

    out = []
    for ch in chapters:
        data = ch.load()
        if not any(f.get("sounds") or (f.get("action_sound") or {}).get("chosen") for f in data["frames"]):
            continue
        vecs = frame_vectors(ch, cfg)
        index = {f["file"]: i for i, f in enumerate(data["frames"])}
        for s in sfx.spots(data) + sfx.silent_frames(data):
            if s["chosen"] and s["frame"] in vecs:
                first = (sfx.layers(s["sound"]) or [sfx.NONE])[0]
                out.append((str(ch.root), index[s["frame"]], vecs[s["frame"]], first, bool(s.get("text"))))
    return out


def vote(vec, memory, is_spot, skip=None):
    """Le son des cases les plus proches : (son, part des voix) ou (None, 0). skip(ex) écarte un exemple."""
    pool = [m for m in memory if m[4] == is_spot and not (skip and skip(m))]
    if len(pool) < K:
        return None, 0.0
    sims = np.array([float(vec @ m[2]) for m in pool])
    top = np.argsort(-sims)[:K]
    score = {}
    for k in top:
        score[pool[k][3]] = score.get(pool[k][3], 0.0) + max(sims[k], 0.0)
    best = max(score, key=score.get)
    return best, score[best] / (sum(score.values()) or 1)


def measure(memory, baseline, thresholds=(0.5, 0.6, 0.7, 0.8)):
    """Essai honnête sur tes choix : chaque case devinée par les autres (sans ses voisines).

    baseline : {(chapitre, index, bulle ?): son proposé sans la mémoire}. Renvoie (seuil, gain en points)
    du meilleur mélange « la mémoire quand elle est sûre, sinon la proposition d'avant », ou (None, 0).
    """
    rows = []
    for m in memory:
        guess, share = vote(m[2], memory, m[4], skip=lambda o, m=m: o[0] == m[0] and abs(o[1] - m[1]) <= NEIGHBOURS)
        rows.append((m[3], baseline.get((m[0], m[1], m[4])), guess, share))
    if len(rows) < 3 * K:
        return None, 0.0
    base = sum(p == w for w, p, _, _ in rows)
    best, gain = None, 0.0
    for th in thresholds:
        mixed = sum((g if g and s >= th else p) == w for w, p, g, s in rows)
        points = 100 * (mixed - base) / len(rows)
        if points > gain:
            best, gain = th, points
    return (best, round(gain, 1)) if gain >= 2 else (None, round(gain, 1))


def run_memory(chapter, cfg=None, progress=None):
    """Les sons appris de tes choix, pour ce chapitre, s'ils font mieux que la proposition d'avant (scene.json)."""
    import json

    from manhwa import sfx
    from manhwa.config import inbox_dir, load_config
    from manhwa.project import find_chapters
    from manhwa.scene import load_scene, scene_path

    cfg = cfg or load_config()
    others = find_chapters(inbox_dir(cfg))
    memory = examples(others, cfg)
    baseline = {}
    for ch in others:
        data = ch.load()
        seen = load_scene(ch)
        plain = {f: {k: v for k, v in e.items() if k not in ("ai", "memory")} for f, e in seen.items()}
        index = {f["file"]: i for i, f in enumerate(data["frames"])}
        for s in sfx.spots(data, plain) + sfx.silent_frames(data, plain):
            baseline[(str(ch.root), index[s["frame"]], bool(s.get("text")))] = (sfx.layers(s["proposed"]) or [sfx.NONE])[0]
    threshold, gain = measure(memory, baseline)
    print(f"  Mémoire des sons : {len(memory)} choix ; mélange {'+' if gain >= 0 else ''}{gain} points"
          f" → {'utilisée' if threshold else 'pas encore utilisée'}")
    seen = load_scene(chapter)
    for e in seen.values():
        e.pop("memory", None)
    if threshold:
        data = chapter.load()
        vecs = frame_vectors(chapter, cfg, progress)
        index = {f["file"]: i for i, f in enumerate(data["frames"])}
        root = str(chapter.root)
        for s in sfx.spots(data) + sfx.silent_frames(data):
            if s["frame"] not in vecs or s["frame"] not in seen:
                continue
            guess, share = vote(vecs[s["frame"]], memory, bool(s.get("text")),
                                skip=lambda m, i=index[s["frame"]]: m[0] == root and abs(m[1] - i) <= NEIGHBOURS)
            if guess and share >= threshold:
                seen[s["frame"]].setdefault("memory", {})[s["key"]] = {"sound": guess, "share": round(share, 2)}
    scene_path(chapter).write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")
    return threshold is not None
