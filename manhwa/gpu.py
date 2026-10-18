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
