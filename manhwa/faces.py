"""Visages des personnages : repérage dans chaque frame, puis regroupement par personnage.

Deux détecteurs qui se complètent :
    - YuNet (OpenCV) trouve les visages dessinés de façon réaliste (hommes, vieillards) ;
    - le détecteur « animeface » trouve les visages style anime (grands yeux).
Chaque tête (visage + cheveux) est ensuite décrite par DINOv2-small : deux têtes du même
personnage ont des descriptions proches, ce qui permet de les regrouper sans connaître
les noms. Mesuré sur Myst Might Mayhem ch. 1 : 71 visages, un groupe par personnage
principal, quelques erreurs à corriger d'un clic dans le Studio.

Les modèles (≈ 90 Mo) sont téléchargés au premier usage dans .cache/models/ et vérifiés
par leur empreinte SHA-256. Tout tourne en local, sur le processeur.
"""
import hashlib
import os

import numpy as np

from manhwa.config import ROOT
from manhwa.project import fingerprint

FACES_VERSION = 1  # à incrémenter quand le repérage change : les visages sont recherchés à nouveau
MATCH = 0.66       # similarité (cosinus DINOv2) à partir de laquelle deux têtes sont le même personnage
                   # (0.6 mélangeait des brigands au héros sur le ch. 1 ; 0.7 coupait le héros en trois)
NOT_FACE_MATCH = 0.8  # très proche d'une forme déjà écartée (fenêtre, poing…) : écartée aussi
MIN_FACE = 40      # px : en dessous, trop petit pour être reconnu
THUMB = 128

MODELS = {
    "yunet.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "animeface.xml": (
        "https://raw.githubusercontent.com/nagadomi/lbpcascade_animeface/master/lbpcascade_animeface.xml",
        "9376d30ac38db6bda2a68b88b3b76bbd7e6aa33af47f7f5c76bc88ca75f1ce30",
    ),
    "dinov2s.onnx": (
        "https://huggingface.co/onnx-community/dinov2-small/resolve/main/onnx/model.onnx",
        "f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a",
    ),
}


def models_dir():
    return ROOT / ".cache" / "models"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ensure_models():
    """Télécharge les modèles manquants ; refuse un fichier dont l'empreinte ne correspond pas."""
    import requests

    folder = models_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for name, (url, sha) in MODELS.items():
        path = folder / name
        if path.is_file() and _sha256(path) == sha:
            continue
        print(f"  Téléchargement du modèle {name}...")
        tmp = path.with_suffix(path.suffix + ".part")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for block in r.iter_content(1 << 20):
                    f.write(block)
        if _sha256(tmp) != sha:
            tmp.unlink()
            raise RuntimeError(f"Modèle {name} : empreinte inattendue, fichier refusé")
        os.replace(tmp, path)


_MODELS = {}


def _models():
    if not _MODELS:
        import cv2
        import onnxruntime as ort

        ensure_models()
        folder = models_dir()
        _MODELS["cascade"] = cv2.CascadeClassifier(str(folder / "animeface.xml"))
        _MODELS["yunet"] = cv2.FaceDetectorYN.create(str(folder / "yunet.onnx"), "", (320, 320), 0.6)
        _MODELS["dino"] = ort.InferenceSession(str(folder / "dinov2s.onnx"), providers=["CPUExecutionProvider"])
    return _MODELS


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / (aw * ah + bw * bh - inter) if inter else 0.0


def detect(crop):
    """Visages d'une case : [[x, y, w, h], ...] dans le repère de la case."""
    import cv2

    m = _models()
    h, w = crop.shape[:2]
    gray = cv2.equalizeHist(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
    boxes = [[int(v) for v in b] for b in m["cascade"].detectMultiScale(gray, 1.1, 5, minSize=(48, 48))]
    m["yunet"].setInputSize((w, h))
    _, found = m["yunet"].detect(crop)
    for row in found if found is not None else []:
        x, y, bw, bh = (int(v) for v in row[:4])
        x, y = max(0, x), max(0, y)
        bw, bh = min(bw, w - x), min(bh, h - y)
        box = [x, y, bw, bh]
        if min(bw, bh) >= MIN_FACE and all(_iou(box, b) < 0.3 for b in boxes):
            boxes.append(box)
    return [b for b in boxes if min(b[2], b[3]) >= MIN_FACE]


def head_box(box, width, height):
    """Le visage élargi aux cheveux (souvent ce qui distingue le mieux deux personnages)."""
    x, y, w, h = box
    x0, y0 = max(0, x - w // 4), max(0, y - h // 2)
    x1, y1 = min(width, x + w + w // 4), min(height, y + h)
    return [x0, y0, x1 - x0, y1 - y0]


_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


def embed(image):
    """Description DINOv2 d'une tête (vecteur de norme 1)."""
    import cv2

    sess = _models()["dino"]
    x = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), (224, 224)).astype(np.float32) / 255
    x = ((x - _MEAN) / _STD).transpose(2, 0, 1)[None]
    v = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    return v / (np.linalg.norm(v) + 1e-9)


def cluster(vecs, threshold=MATCH):
    """Regroupement hiérarchique (lien moyen) : listes d'indices, les plus grands groupes d'abord."""
    n = len(vecs)
    if not n:
        return []
    V = np.stack(vecs)
    sim = V @ V.T
    np.fill_diagonal(sim, -np.inf)
    groups = [[i] for i in range(n)]
    alive = np.ones(n, bool)
    while True:
        masked = np.where(alive[:, None] & alive[None, :], sim, -np.inf)
        a, b = np.unravel_index(np.argmax(masked), masked.shape)
        if masked[a, b] < threshold:
            break
        na, nb = len(groups[a]), len(groups[b])
        merged = (na * sim[a] + nb * sim[b]) / (na + nb)  # similarité moyenne du groupe fusionné
        sim[a], sim[:, a] = merged, merged
        sim[a, a] = -np.inf
        groups[a] += groups[b]
        groups[b] = []
        alive[b] = False
    return sorted((g for g in groups if g), key=len, reverse=True)


def faces_key(analysis, frames):
    return fingerprint(FACES_VERSION, analysis and analysis["key"], [(f["file"], f["crop"]) for f in frames])


def assign(faces, vecs, known, rejected, new_character):
    """Range chaque visage : personnage déjà connu, nouveau groupe, ou « autres visages ».

    known : {id de personnage: centre}, rejected : vecteurs des formes écartées.
    new_character() crée un personnage sans nom et renvoie son id.
    """
    rest = []
    for i, (face, v) in enumerate(zip(faces, vecs)):
        if rejected and max(float(v @ r) for r in rejected) >= NOT_FACE_MATCH:
            face.update(char=None, not_face=True)
            continue
        scores = {cid: float(v @ c) for cid, c in known.items()}
        best = max(scores, key=scores.get, default=None)
        if best is not None and scores[best] >= MATCH:
            face["char"] = best
        else:
            rest.append(i)
    for group in cluster([vecs[i] for i in rest]):
        cid = new_character() if len(group) >= 2 else None  # un visage seul : à ranger à la main
        for j in group:
            faces[rest[j]]["char"] = cid
    return faces
