"""Lecture de config.toml (valeurs par défaut + surcharges) et du fichier .env."""
import copy
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "inbox": "inbox",
    "slicer": {
        "max_src_width": 1200,
        "bg_mode": "blur",
        "blur_ksize": 61,
        "move_step": 20,
        "resize_step": 20,
        "jpeg_quality": 92,
    },
    "output": {"width": 1080, "height": 1920},
    "ocr": {"tesseract_cmd": "", "lang": "eng", "psm": 6},
    "tts": {
        "voice": "en-US-ChristopherNeural",
        "rate": "+0%",
        "volume": "+0%",
        "concurrency": 4,
    },
    "render": {"fps": 24, "padding_seconds": 0.2, "silent_frame_seconds": 2.0},
    "scraper": {
        "headless": False,
        "workers": 5,
        "timeout_seconds": 20,
        "sites": {
            "default": {
                "domains": [],
                "title": "span.text-xl.font-bold",
                "chapter_links": "a[href*='chapter']",
                "image_min_width": 300,
                "image_extensions": [".webp"],
            }
        },
    },
}


def _merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path=None):
    """Renvoie la config complète : DEFAULTS surchargés par config.toml s'il existe."""
    cfg = copy.deepcopy(DEFAULTS)
    path = Path(path or os.environ.get("MANHWA_CONFIG") or ROOT / "config.toml")
    if path.is_file():
        with open(path, "rb") as f:
            _merge(cfg, tomllib.load(f))
    return cfg


def inbox_dir(cfg):
    inbox = Path(cfg["inbox"])
    return inbox if inbox.is_absolute() else ROOT / inbox


def load_env(path=None):
    """Charge .env dans os.environ, sans écraser les variables déjà définies."""
    path = Path(path or ROOT / ".env")
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
