"""Ce qui se passe dans chaque case (« il est projeté contre un mur, du sang gicle »), pour le bon bruitage.

CLIP (scene.py) reconnaît des choses (du feu, une lame) mais pas l'action. Ici un modèle qui
voit décrit chaque case en une ou deux phrases, puis GPT (sfx.suggest_sounds) lit ces
descriptions dans l'ordre de l'histoire, avec les répliques autour, et choisit les sons.

    vision = "local"   Qwen3.5-2B (Apache 2.0), dans .venv-tts : ≈ 2 s par case (6 à la fois), ≈ 5 Go de carte
                       graphique, sans clé (le modèle, ≈ 4,6 Go, se télécharge une fois)
    vision = "gpt"     GPT-4.1 regarde l'image (plus juste sur quelques essais, mais chaque case part au proxy)

Réglé dans config.toml, [sounds] vision ; sans .venv-tts, GPT. Résultat dans scene.json
(« desc » de chaque case), gardé tant que la découpe ne change pas.

Installation, en plus de Chatterbox (voir chatterbox_tts.py) :
    uv pip install --python .venv-tts/Scripts/python.exe torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
    uv pip install --python .venv-tts/Scripts/python.exe accelerate

Mesuré sur l'épisode 1 (78 sons que tu avais choisis) : la proposition d'avant (CLIP) retrouve
ton choix 83 fois sur 100, celle d'après la description 50 (même famille de son). Mais tu avais
choisi parmi les 3 sons que CLIP te montrait (88 %) : la comparaison l'avantage. GPT qui regarde
lui-même l'image fait moins bien (35). À refaire sur un épisode choisi avec le nouvel onglet.
"""
import base64
import io
import json
import os
import subprocess
import tempfile
import threading

from manhwa.config import ROOT

PROMPT = ("This is one panel of a manhwa (Korean webtoon). In one or two short sentences, describe the ACTION happening: "
          "who does what, any impact, weapon, blood, fall, fire, door, footsteps, magic. Then on a new line write "
          "'SOUNDS:' followed by up to 3 sound effects you would hear, most important first, or 'none' if it is a calm "
          "talking scene.")
BATCH = 6  # cases décrites ensemble : 1,9 s par case au lieu de 5,3 (8 : 1,7 s, mais 5,5 Go de carte)
_WORKER = {}
_LOCK = threading.Lock()


def backend(cfg):
    from manhwa import chatterbox_tts

    wanted = str(((cfg or {}).get("sounds") or {}).get("vision", "local")).lower()
    if wanted == "local" and chatterbox_tts.available():
        return "local"
    return "gpt"


def _worker():
    w = _WORKER.get("p")
    if w and w.poll() is None:
        return w
    from manhwa import chatterbox_tts

    chatterbox_tts.close()  # les deux ne tiennent pas ensemble dans 6 Go
    from manhwa.gpu import release_models

    release_models()
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vision_worker.py")
    p = subprocess.Popen([str(chatterbox_tts.python()), "-u", worker], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8", cwd=str(ROOT))
    if not chatterbox_tts._answer(p).get("ready"):
        p.kill()
        raise RuntimeError("Le modèle qui regarde les cases n'a pas démarré (environnement .venv-tts ?)")
    _WORKER["p"] = p
    return p


def close():
    """Arrête le modèle : la carte graphique est libérée."""
    p = _WORKER.pop("p", None)
    if p and p.poll() is None:
        try:
            p.stdin.close()
            p.wait(timeout=20)
        except Exception:
            p.kill()


def _local_many(paths):
    """Plusieurs cases d'un coup : le modèle écrit pour toutes en même temps (BATCH cases ≈ le temps d'une)."""
    from manhwa.chatterbox_tts import _answer

    with _LOCK:
        p = _worker()
        p.stdin.write(json.dumps({"batch": [{"image": str(x), "prompt": PROMPT} for x in paths]}) + "\n")
        p.stdin.flush()
        answer = _answer(p)
    if "error" in answer:
        raise RuntimeError(answer["error"])
    return answer["texts"]


def _gpt(path):
    from PIL import Image

    from manhwa.llm import chat

    img = Image.open(path).convert("RGB")
    img.thumbnail((768, 768))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return chat([{"role": "user", "content": [{"type": "text", "text": PROMPT},
                                              {"type": "image_url", "image_url": {"url": url, "detail": "low"}}]}],
                json_mode=False, temperature=0, max_tokens=120).strip()


def parse(text):
    """« action… SOUNDS: a, b » → (action, [sons entendus])."""
    action, _, sounds = (text or "").partition("SOUNDS:")
    heard = [s.strip(" -*•\"'!.").lower() for s in sounds.replace("\n", ",").split(",")]
    heard = [s for s in heard if s and s != "none"][:3]
    return " ".join(action.split())[:400], heard


def describe_done(chapter, data):
    from manhwa.scene import _frame_key, load_scene

    got = load_scene(chapter)
    return bool(data["frames"]) and all((got.get(f["file"]) or {}).get("key") == _frame_key(f) and "desc" in got[f["file"]]
                                        for f in data["frames"])


def run_describe(chapter, cfg, progress=None):
    """Décrit chaque case (après scene.run_scene, qui prépare scene.json) ; celles déjà décrites sont gardées."""
    import cv2

    from manhwa.images import load_strip
    from manhwa.scene import _frame_key, load_scene, run_scene, scene_path

    run_scene(chapter, cfg)
    data = chapter.load()
    got = load_scene(chapter)
    todo = [f for f in data["frames"] if (got.get(f["file"]) or {}).get("key") == _frame_key(f) and "desc" not in got[f["file"]]]
    if not todo:
        return 0
    local = backend(cfg) == "local"
    size = BATCH if local else 1
    strip, _ = load_strip(chapter.pages(), cfg["slicer"]["max_src_width"])
    path = scene_path(chapter)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for start in range(0, len(todo), size):
                group = todo[start:start + size]
                imgs = []
                for k, frame in enumerate(group):
                    x, y, w, h = frame["crop"]
                    imgs.append(os.path.join(tmp, f"case{k}.jpg"))
                    cv2.imwrite(imgs[-1], strip[y:y + h, x:x + w], [cv2.IMWRITE_JPEG_QUALITY, 90])
                texts = _local_many(imgs) if local else [_gpt(imgs[0])]
                for frame, text in zip(group, texts):
                    action, heard = parse(text)
                    got[frame["file"]]["desc"] = action
                    got[frame["file"]]["heard"] = heard
                done = start + len(group)
                if progress:
                    progress(done, len(todo))
                if done % 12 < size or done == len(todo):  # gardé en route : une coupure ne fait pas tout refaire
                    path.write_text(json.dumps(got, ensure_ascii=False), encoding="utf-8")
    finally:
        close()
    return len(todo)
