"""Moteurs OCR interchangeables.

Chaque moteur prend une image BGR et renvoie des lignes de texte :
    [{"text": str, "conf": float | None (0→1), "box": [x, y, w, h]}]
dans l'ordre où il les trouve. Le regroupement en bulles et le tri SFX/dialogue se font
ensuite, pareil pour tous les moteurs (manhwa/bubbles.py).
"""
import asyncio
import os
import shutil

import cv2
import numpy as np

_cache = {}


# ---------- Tesseract (V1) ----------

def tesseract_lines(img, cfg):
    import pytesseract

    from manhwa.ocr import WINDOWS_TESSERACT

    if "tesseract" not in _cache:
        cmd = cfg["ocr"].get("tesseract_cmd") or shutil.which("tesseract")
        if not cmd and os.path.isfile(WINDOWS_TESSERACT):
            cmd = WINDOWS_TESSERACT
        pytesseract.pytesseract.tesseract_cmd = cmd
        _cache["tesseract"] = True
    data = pytesseract.image_to_data(
        cv2.cvtColor(img, cv2.COLOR_BGR2RGB), lang=cfg["ocr"]["lang"],
        config="--oem 1 --psm 11", output_type=pytesseract.Output.DICT,
    )
    lines = {}
    for i, raw in enumerate(data["text"]):
        word = (raw or "").strip()
        conf = float(data["conf"][i]) if str(data["conf"][i]) not in ("-1", "") else -1
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y, w, h = (data[k][i] for k in ("left", "top", "width", "height"))
        line = lines.setdefault(key, {"words": [], "confs": [], "x0": x, "y0": y, "x1": x + w, "y1": y + h})
        line["words"].append(word)
        line["confs"].append(conf / 100)
        line["x0"], line["y0"] = min(line["x0"], x), min(line["y0"], y)
        line["x1"], line["y1"] = max(line["x1"], x + w), max(line["y1"], y + h)
    return [{"text": " ".join(l["words"]), "conf": float(np.mean(l["confs"])),
             "box": [l["x0"], l["y0"], l["x1"] - l["x0"], l["y1"] - l["y0"]]} for l in lines.values()]


# ---------- OCR de Windows (celui de Win+Maj+T) ----------

def _windows_engine(lang):
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    key = f"windows:{lang}"
    if key not in _cache:
        engine = OcrEngine.try_create_from_language(Language(lang))
        if engine is None:
            raise RuntimeError(f"OCR Windows : langue {lang} non installée (Paramètres → Langue).")
        _cache[key] = engine
    return _cache[key]


async def _windows_recognize(engine, img):
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter

    bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    h, w = bgra.shape[:2]
    writer = DataWriter()
    writer.write_bytes(bgra.tobytes())
    # la variante à 4 paramètres : celle qui accepte aussi le mode alpha n'est pas exposée en Python
    bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8, w, h)
    return await engine.recognize_async(bitmap)


def windows_lines(img, cfg, lang="en-US"):
    from winrt.windows.media.ocr import OcrEngine

    engine = _windows_engine(lang)
    # le moteur limite la taille des images ; on agrandit un peu le petit texte (lu plus juste)
    scale = 1.0
    h, w = img.shape[:2]
    if w < 1200:
        scale = min(1200 / w, OcrEngine.max_image_dimension / h)
    big = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale > 1 else img
    if max(big.shape[:2]) > OcrEngine.max_image_dimension:
        s = OcrEngine.max_image_dimension / max(big.shape[:2])
        big = cv2.resize(big, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        scale *= s
    result = asyncio.run(_windows_recognize(engine, big))
    lines = []
    for line in result.lines:
        rects = [wd.bounding_rect for wd in line.words]
        if not rects:
            continue
        x0, y0 = min(r.x for r in rects), min(r.y for r in rects)
        x1, y1 = max(r.x + r.width for r in rects), max(r.y + r.height for r in rects)
        lines.append({"text": line.text, "conf": None,
                      "box": [round(x0 / scale), round(y0 / scale), round((x1 - x0) / scale), round((y1 - y0) / scale)]})
    return lines


# ---------- PaddleOCR ----------

def paddle_device(cfg=None):
    """« gpu:0 » si Paddle a été installé avec CUDA (paddlepaddle-gpu) et voit une carte, sinon « cpu ».

    [ocr] device = "auto" (défaut), "gpu" ou "cpu".
    """
    wanted = ((cfg or {}).get("ocr", {}).get("device") or "auto").lower()
    if wanted == "cpu":
        return "cpu"
    try:
        import paddle

        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            return "gpu:0"
    except Exception:
        pass
    return "cpu"


def _paddle(cfg=None):
    if "paddle" not in _cache:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR

        device = paddle_device(cfg)
        print(f"  PaddleOCR sur {'la carte graphique' if device.startswith('gpu') else 'le processeur'} ({device})")

        # modèles « mobile » : même précision que les « medium » sur nos bulles (banc d'essai
        # du chapitre 1), mais 2 à 4 s par case au lieu de 15 à 20 s sur processeur
        _cache["paddle"] = PaddleOCR(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="en_PP-OCRv5_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # oneDNN plante avec Paddle 3.3 sur processeur (ConvertPirAttribute2RuntimeAttribute)
            enable_mkldnn=False,
            device=device,
        )
    return _cache["paddle"]


def paddle_lines(img, cfg):
    result = _paddle(cfg).predict(img)
    if not result:
        return []
    r = result[0]
    lines = []
    for text, score, poly in zip(r["rec_texts"], r["rec_scores"], r["rec_polys"]):
        if not text.strip():
            continue
        xs, ys = np.asarray(poly)[:, 0], np.asarray(poly)[:, 1]
        lines.append({"text": text, "conf": float(score),
                      "box": [int(xs.min()), int(ys.min()), int(xs.max() - xs.min()), int(ys.max() - ys.min())]})
    return lines


ENGINES = {"tesseract": tesseract_lines, "windows": windows_lines, "paddle": paddle_lines}


def read_lines(img, cfg, engine=None):
    engine = engine or cfg["ocr"].get("engine", "windows")
    if engine not in ENGINES:
        raise RuntimeError(f"Moteur OCR inconnu : {engine} (choix : {', '.join(ENGINES)})")
    return ENGINES[engine](img, cfg)
