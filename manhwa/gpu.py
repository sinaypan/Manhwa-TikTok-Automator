"""La carte graphique pour les modèles locaux (Whisper, détecteurs ONNX).

paddlepaddle-gpu installe les bibliothèques CUDA 12 (cuBLAS, cuDNN…) dans
.venv/Lib/site-packages/nvidia/*/bin ; CTranslate2 (Whisper) et onnxruntime-gpu en ont
besoin aussi, mais ne les trouvent pas seuls sous Windows : on les leur montre ici.
Sans carte graphique (ou sans ces bibliothèques), tout tourne sur le processeur.
"""
import os
import sys
from pathlib import Path

_DONE = []


def enable_cuda_dlls():
    """Rend visibles les DLL CUDA installées avec paddlepaddle-gpu. Renvoie les dossiers ajoutés."""
    if _DONE:
        return _DONE[0]
    folders = []
    for base in map(Path, sys.path):
        nvidia = base / "nvidia"
        if nvidia.is_dir():
            folders += [p for p in nvidia.glob("*/bin") if p.is_dir()]
    for f in folders:
        try:
            os.add_dll_directory(str(f))
        except (OSError, AttributeError):
            pass
    if folders:
        os.environ["PATH"] = os.pathsep.join([str(f) for f in folders] + [os.environ.get("PATH", "")])
    _DONE.append(folders)
    return folders


def onnx_providers():
    """Les fournisseurs onnxruntime à essayer : la carte graphique d'abord si elle est là."""
    import onnxruntime as ort

    enable_cuda_dlls()
    available = ort.get_available_providers()
    return [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in available]


def before_paddle():
    """À appeler avant d'importer Paddle : charge d'abord CTranslate2 (Whisper).

    Paddle chargé en premier dans le programme, CTranslate2 ne se charge plus ensuite (WinError 127,
    une DLL CUDA déjà prise dans une autre version) : « Tout faire » s'arrêtait aux voix, quand
    Whisper réécoute les répliques. Dans cet ordre-ci, les deux marchent.
    """
    enable_cuda_dlls()
    try:
        import ctranslate2  # noqa: F401
    except Exception:
        pass


# les petits modèles chargés dans le programme du Studio (lecture du texte, visages, relief, CLIP…)
KEPT = (("manhwa.ocr_engines", "_cache"), ("manhwa.motion", "_DEPTH"), ("manhwa.faces", "_MODELS"),
        ("manhwa.scene", "_MODELS"), ("manhwa.sound_memory", "_S"), ("manhwa.listen", "_MODEL"),
        ("manhwa.kokoro_tts", "_ENGINE"), ("manhwa.watermark", "_SESSION"))


def release_models():
    """Rend la carte graphique avant un gros modèle lancé à part (description, dessins, voix).

    Les petits modèles du Studio y gardent ≈ 1 Go (mesuré : lecture du texte 0,4, relief 0,3,
    visages 0,3) : avec un gros modèle de 5 Go à côté, la carte de 6 Go déborde dans la mémoire
    du PC et tout ralentit (jusqu'à 4 fois). Ils se rechargent d'eux-mêmes au besoin.
    """
    import gc

    for module, name in KEPT:
        m = sys.modules.get(module)
        if m is not None and isinstance(getattr(m, name, None), dict):
            getattr(m, name).clear()
    gc.collect()
    paddle = sys.modules.get("paddle")
    if paddle is not None:
        try:
            paddle.device.cuda.empty_cache()
        except Exception:
            pass
