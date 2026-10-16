"""Ce que montre chaque case (feu, lame, verre, bois…), pour proposer le bon bruitage.

CLIP (OpenAI, version ONNX allégée de Xenova) compare l'image à de courtes descriptions :
« des flammes », « une lame qui tranche »… Chaque description mène à une catégorie de
sons (manhwa/sfx.py) ; d'autres (« un visage en gros plan », « un paysage calme ») mènent
à « aucun son ». Une case haute est découpée en carrés : il suffit qu'un morceau montre
du feu pour proposer le feu.

Les modèles (≈ 150 Mo) sont téléchargés au premier usage dans .cache/models/ et vérifiés
par leur empreinte. Tout tourne en local, sans clé : ≈ 15 s pour un chapitre.
Résultat dans <chapitre>/.studio/scene.json (un cache : recalculé si la découpe change).
"""
import hashlib
import json

import numpy as np

from manhwa.panels import STUDIO_DIR

SCENE_VERSION = 1
_BASE = "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main"
MODELS = {
    "clip_vision_q.onnx": (f"{_BASE}/onnx/vision_model_quantized.onnx",
                           "583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299"),
    "clip_text_q.onnx": (f"{_BASE}/onnx/text_model_quantized.onnx",
                         "73baab855d406190da9faa498cfedf65f15cf309f4cc7385b7b032e6d08e5c3a"),
    "clip_tokenizer.json": (f"{_BASE}/tokenizer.json",
                            "f7f3b7af117d467b58374797691a6438d3e6b9e9cef800dfd5dced7f697a90cd"),
}

# (description donnée à CLIP, catégorie de son ou None = pas de son, ce qu'on affiche « je vois »)
CONCEPTS = [
    ("a sword slash with a sharp blade cutting", "slash", "une lame"),
    ("blood splatter and a bloody wound", "slash", "du sang"),
    ("a fist punching someone in the face", "punch", "un coup de poing"),
    ("a violent hit, a body thrown back by a strike", "impact", "un coup"),
    ("shattered glass shards flying", "glass", "du verre brisé"),
    ("wooden planks, a wooden building or trees", "wood", "du bois"),
    ("metal armor and weapons clashing with sparks", "metal", "du métal"),
    ("a huge explosion with smoke and debris", "explosion", "une explosion"),
    ("fire and burning flames", "fire", "du feu"),
    ("speed lines showing a very fast movement", "whoosh", "un mouvement rapide"),
    ("feet walking on the ground", "footsteps", "des pas"),
    ("a door opening or closing", "door", "une porte"),
    ("glowing magical energy and a bright aura", "magic", "de la magie"),
    ("a robe and clothes flapping in the wind", "cloth", "des vêtements au vent"),
    ("strong wind blowing leaves and dust", "wind", "du vent"),
    ("lightning striking in a stormy sky", "thunder", "un éclair"),
    ("a close-up portrait of a person's face", None, "un visage"),
    ("two people standing and talking calmly", None, "une discussion"),
    ("a calm landscape, a sky or a building", None, "un décor calme"),
    ("an empty black or white panel", None, "une case vide"),
    ("a speech bubble with text", None, "du texte"),
]
LOGIT_SCALE = 100.0  # celui de CLIP : rend les probabilités tranchées
SHOW = 0.12          # « je vois » : à partir de cette probabilité
SURE = 0.35          # le son est proposé d'office (en pointillés) à partir de celle-ci
NEVER_SURE = {"cloth"}  # des robes, il y en a dans toutes les cases : proposé, jamais mis d'office

MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32)

_MODELS = {}


def _models():
    if not _MODELS:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        from manhwa.faces import ensure_models, models_dir

        ensure_models(MODELS)
        folder = models_dir()
        opts = ["CPUExecutionProvider"]
        _MODELS["vision"] = ort.InferenceSession(str(folder / "clip_vision_q.onnx"), providers=opts)
        _MODELS["text"] = ort.InferenceSession(str(folder / "clip_text_q.onnx"), providers=opts)
        _MODELS["tok"] = Tokenizer.from_file(str(folder / "clip_tokenizer.json"))
    return _MODELS


def _normalize(v):
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


def text_vectors():
    """Les descriptions, une fois calculées puis gardées dans .cache/models/."""
    from manhwa.faces import models_dir

    prompts = [f"a manhwa panel showing {p}" for p, _, _ in CONCEPTS]
    tag = hashlib.sha1("\n".join(prompts).encode("utf-8")).hexdigest()[:12]
    path = models_dir() / f"clip_text_{tag}.npy"
    if path.is_file():
        return np.load(path)
    m = _models()
    out = []
    for p in prompts:  # une à une : pas de remplissage, donc pas de souci de fin de phrase
        ids = np.array([m["tok"].encode(p).ids[:77]], np.int64)
        out.append(m["text"].run(None, {"input_ids": ids})[0][0])
    vecs = _normalize(np.array(out, np.float32))
    np.save(path, vecs)
    return vecs


def tiles(crop):
    """La case en carrés qui se chevauchent (au plus 6) : une case haute n'est pas écrasée."""
    h, w = crop.shape[:2]
    side = min(h, w)
    if max(h, w) < 1.3 * side:
        return [crop]
    length = max(h, w)
    n = min(6, int(np.ceil((length - side) / (0.75 * side))) + 1)
    starts = np.linspace(0, length - side, n).astype(int)
    return [crop[s:s + side] if h > w else crop[:, s:s + side] for s in starts]


def _pixels(img):
    import cv2

    rgb = cv2.cvtColor(cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    x = (rgb.astype(np.float32) / 255 - MEAN) / STD
    return x.transpose(2, 0, 1)


def classify(crop, texts=None):
    """{catégorie ou "none": probabilité}, le maximum sur les morceaux de la case."""
    texts = text_vectors() if texts is None else texts
    batch = np.stack([_pixels(t) for t in tiles(crop)])
    img = _normalize(_models()["vision"].run(None, {"pixel_values": batch})[0])
    logits = LOGIT_SCALE * img @ texts.T
    probs = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs /= probs.sum(axis=1, keepdims=True)
    out = {}
    for k, (_, cat, _) in enumerate(CONCEPTS):
        out.setdefault(cat or "none", np.zeros(len(batch)))
        out[cat or "none"] = out[cat or "none"] + probs[:, k]
    seen = {}
    for k, (_, cat, label) in enumerate(CONCEPTS):
        if cat and probs[:, k].max() >= SHOW:
            seen[label] = max(seen.get(label, 0), float(probs[:, k].max()))
    best = {c: float(v.max()) for c, v in out.items()}
    return best, seen


# ---------- Le chapitre ----------

def scene_path(chapter):
    return chapter.root / STUDIO_DIR / "scene.json"


def _frame_key(frame):
    return f"{SCENE_VERSION}:{frame['crop']}"


def load_scene(chapter):
    try:
        return json.loads(scene_path(chapter).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def scene_done(chapter, data):
    got = load_scene(chapter)
    return bool(data["frames"]) and all((got.get(f["file"]) or {}).get("key") == _frame_key(f) for f in data["frames"])


def run_scene(chapter, cfg, progress=None):
    """Regarde chaque case du chapitre (celles déjà vues avec la même découpe sont gardées)."""
    from manhwa.images import load_strip

    data = chapter.load()
    got = load_scene(chapter)
    todo = [f for f in data["frames"] if (got.get(f["file"]) or {}).get("key") != _frame_key(f)]
    if not todo:
        return 0
    texts = text_vectors()
    strip, _ = load_strip(chapter.pages(), cfg["slicer"]["max_src_width"])
    for i, frame in enumerate(todo):
        x, y, w, h = frame["crop"]
        cats, seen = classify(strip[y:y + h, x:x + w], texts)
        got[frame["file"]] = {"key": _frame_key(frame),
                              "cats": {c: round(p, 3) for c, p in cats.items() if p >= 0.03},
                              "seen": {k: round(p, 3) for k, p in sorted(seen.items(), key=lambda kv: -kv[1])}}
        if progress:
            progress(i + 1, len(todo))
    keep = {f["file"] for f in data["frames"]}
    got = {k: v for k, v in got.items() if k in keep}
    path = scene_path(chapter)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(got, ensure_ascii=False), encoding="utf-8")
    return len(todo)


def recommend(scene, gpt=None, limit=3):
    """Les sons à proposer pour une case : [catégorie], et celle à mettre d'office (ou None).

    scene : {"cats", "seen"} de la case ; gpt : la catégorie que GPT a proposée (s'il y en a).
    """
    cats = dict((scene or {}).get("cats") or {})
    none = cats.pop("none", 0)
    ranked = [c for c, p in sorted(cats.items(), key=lambda kv: -kv[1]) if p >= 0.05]
    recs = ([gpt] if gpt else []) + [c for c in ranked if c != gpt]
    sure = [c for c in ranked if c not in NEVER_SURE]
    best = gpt or (sure[0] if sure and cats[sure[0]] >= SURE and cats[sure[0]] > none else None)
    return recs[:limit], best
