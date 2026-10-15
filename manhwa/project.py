"""Un chapitre = un dossier inbox/<série>/<chapitre>/ + son project.json.

Disposition d'un chapitre :
    pages/          images source (scraper) — ou directement à la racine (à la main)
    frames/         frames 9:16 découpées
    audio/          une voix par frame
    project.json    état de chaque étape (crops, textes, clés de cache)
    video.mp4       résultat
"""
import hashlib
import json
import os
from pathlib import Path

from manhwa.images import list_images, natural_key

PROJECT_VERSION = 1
PAGES_DIR = "pages"
FRAMES_DIR = "frames"
AUDIO_DIR = "audio"
PROJECT_FILE = "project.json"
VIDEO_FILE = "video.mp4"
_SKIP_DIRS = {PAGES_DIR, FRAMES_DIR, AUDIO_DIR, ".studio", ".git", ".venv", "__pycache__"}


def fingerprint(*parts):
    """Clé de cache courte : change dès qu'une des entrées change."""
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


class Chapter:
    def __init__(self, root):
        self.root = Path(root)

    @property
    def name(self):
        return f"{self.root.parent.name} / {self.root.name}"

    @property
    def pages_dir(self):
        pages = self.root / PAGES_DIR
        return pages if pages.is_dir() else self.root

    @property
    def frames_dir(self):
        return self.root / FRAMES_DIR

    @property
    def audio_dir(self):
        return self.root / AUDIO_DIR

    @property
    def project_path(self):
        return self.root / PROJECT_FILE

    @property
    def video_path(self):
        return self.root / VIDEO_FILE

    def pages(self):
        return list_images(self.pages_dir)

    def load(self):
        if self.project_path.is_file():
            with open(self.project_path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        data.setdefault("version", PROJECT_VERSION)
        data.setdefault("frames", [])
        data.setdefault("steps", {})
        return data

    def save(self, data):
        """Écriture atomique : un crash pendant la sauvegarde ne corrompt pas le fichier."""
        tmp = self.project_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.project_path)


def is_chapter_dir(path):
    path = Path(path)
    return bool(list_images(path) or list_images(path / PAGES_DIR))


def find_chapters(path):
    """Tous les chapitres sous `path` (un chapitre, une série ou tout l'inbox)."""
    path = Path(path)
    if not path.is_dir():
        return []
    if is_chapter_dir(path):
        return [Chapter(path)]
    found = []
    for dirpath, dirnames, _ in os.walk(path):
        dirnames[:] = sorted((d for d in dirnames if d not in _SKIP_DIRS), key=natural_key)
        if Path(dirpath) != path and is_chapter_dir(dirpath):
            found.append(Chapter(dirpath))
            dirnames[:] = []  # pas de chapitre dans un chapitre
    return sorted(found, key=lambda c: natural_key(str(c.root.relative_to(path))))
