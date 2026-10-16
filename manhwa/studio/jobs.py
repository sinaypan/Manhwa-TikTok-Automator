"""Travaux en arrière-plan, un à la fois.

    make     la vidéo : frames → OCR → voix → rendu
    auto     tout d'un coup : frames → OCR → visages → wiki → relecture GPT → voix GPT → sons GPT
             → voix → rendu (les étapes GPT et wiki sont sautées si elles échouent : pas de clé…)
    import   télécharge des chapitres depuis un lien, puis lance « auto » sur chacun
    faces, wiki, wiki_images, review, voices, sounds : une seule étape, depuis le Studio
"""
import queue
import threading
import time
import traceback

STEP_LABELS = {"frames": "Frames", "ocr": "Lecture du texte", "tts": "Voix", "render": "Rendu vidéo",
               "faces": "Recherche des visages", "wiki": "Lecture du wiki", "wiki_images": "Images du wiki",
               "wiki_faces": "Visages du wiki", "review": "Relecture GPT", "voices": "Choix des voix",
               "sounds": "Sons des cases sans texte", "scene": "Ce que montrent les cases",
               "textfix": "Correction du texte", "listen": "Réécoute de la voix",
               "download": "Téléchargement"}
# ce que l'on compte à chaque étape (« 6 210 / 12 960 images »)
STEP_UNITS = {"frames": "frames", "ocr": "frames lues", "tts": "voix", "render": "images", "faces": "frames", "wiki": "",
              "wiki_images": "images", "wiki_faces": "images", "review": "lots", "voices": "", "sounds": "",
              "scene": "cases", "textfix": "", "listen": "répliques", "download": ""}
IMPORT_ID = "import"  # l'import n'a pas encore de chapitre : il a sa propre ligne


class Jobs:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        # id du chapitre → {"kind", "step", "label", "status", "error", "warnings",
        #                   "progress" (0→1 ou None), "done", "total", "unit", "step_started"}
        self.state = {}
        self.queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def snapshot(self):
        with self.lock:
            return {k: dict(v) for k, v in self.state.items()}

    def get(self, chapter_id):
        with self.lock:
            job = self.state.get(chapter_id)
            return dict(job) if job else None

    def submit(self, chapter_id, chapter, kind="make", params=None):
        with self.lock:
            current = self.state.get(chapter_id)
            if current and current["status"] in ("queued", "running"):
                return dict(current)
            self.state[chapter_id] = {"kind": kind, "step": None, "label": "En attente", "status": "queued", "error": None,
                                      "warnings": [], "progress": None, "done": None, "total": None, "unit": None,
                                      "step_started": None, "params": params}
        self.queue.put((chapter_id, chapter, kind, params or {}))
        return self.get(chapter_id)

    def _set(self, chapter_id, **changes):
        with self.lock:
            self.state[chapter_id].update(changes)

    def _steps(self, kind, params):
        """[(étape, fonction(chapitre, progression), facultative)]."""
        from manhwa.cast import run_faces, series_dir
        from manhwa.ingest import wiki
        from manhwa.ocr import run_ocr
        from manhwa.panels import build_frames
        from manhwa.render import run_render
        from manhwa.review import run_review
        from manhwa.scene import run_scene
        from manhwa.listen import run_listen
        from manhwa.textfix import run_textfix
        from manhwa.sfx import suggest_actions
        from manhwa.tts import run_tts
        from manhwa.voices import propose as propose_voices

        cfg = self.cfg
        one = {
            "frames": lambda c, p: build_frames(c, cfg, progress=p),
            "ocr": lambda c, p: run_ocr(c, cfg, progress=p),
            "faces": lambda c, p: run_faces(c, cfg, progress=p),
            "wiki": lambda c, p: wiki.load_wiki(series_dir(c)) or wiki.fetch(series_dir(c)),
            "review": lambda c, p: run_review(c, cfg, progress=p),
            "voices": lambda c, p: propose_voices(c, cfg, progress=p),
            "sounds": lambda c, p: suggest_actions(c, cfg, progress=p),
            "scene": lambda c, p: run_scene(c, cfg, progress=p),
            "textfix": lambda c, p: run_textfix(c, cfg, progress=p),
            "listen": lambda c, p: run_listen(c, cfg, progress=p),
            "tts": lambda c, p: run_tts(c, cfg, progress=p),
            "render": lambda c, p: run_render(c, cfg, progress=p),
            "wiki_images": lambda c, p: wiki.fetch_images(series_dir(c), progress=p),
            "wiki_faces": lambda c, p: wiki.embed_wiki_faces(series_dir(c), progress=p),
        }
        plans = {
            "make": ["frames", "ocr", "textfix", "tts", "render", "listen?"],
            "auto": ["frames", "ocr", "textfix", "faces", "scene?", "wiki?", "review?", "voices?", "sounds?", "tts", "render",
                     "listen?"],
            "wiki_images": ["wiki_images", "wiki_faces"],
        }
        if kind == "import":
            return [("download", lambda c, p: self._import(params), False)]
        if kind == "wiki":
            return [("wiki", lambda c, p: wiki.fetch(series_dir(c)), False)]
        names = plans.get(kind, [kind])
        return [(n.rstrip("?"), one[n.rstrip("?")], n.endswith("?")) for n in names]

    def _import(self, params):
        """Télécharge les chapitres demandés, puis lance « auto » (ou « make ») sur chacun."""
        from manhwa.config import inbox_dir
        from manhwa.ingest.scraper import download_series
        from manhwa.project import Chapter

        dirs = download_series(params["url"], self.cfg, selection=params.get("chapters") or "")
        if not dirs:
            raise RuntimeError("Aucun chapitre téléchargé : vérifie le lien (page de la série) et la vérification du site")
        inbox = inbox_dir(self.cfg).resolve()
        for d in dirs:
            cid = d.resolve().relative_to(inbox).as_posix()
            self.submit(cid, Chapter(d), "auto" if params.get("auto", True) else "make")
        with self.lock:
            self.state[IMPORT_ID]["chapters"] = [d.resolve().relative_to(inbox).as_posix() for d in dirs]

    def _worker(self):
        while True:
            chapter_id, chapter, kind, params = self.queue.get()
            try:
                for step, run, optional in self._steps(kind, params):
                    self._set(chapter_id, step=step, label=STEP_LABELS[step], status="running", progress=None,
                              done=None, total=None, unit=STEP_UNITS[step], step_started=time.time())
                    try:
                        run(chapter, lambda done, total, cid=chapter_id: self._set(
                            cid, progress=round(done / total, 4) if total else None, done=done, total=total))
                    except Exception as e:
                        if not optional:
                            raise
                        # étape facultative (GPT, wiki) : on continue sans elle
                        print(f"  [!] {STEP_LABELS[step]} sautée : {e}")
                        with self.lock:
                            self.state[chapter_id]["warnings"].append(f"{STEP_LABELS[step]} : {e}")
                self._set(chapter_id, step=None, label="Terminé", status="done", progress=None, done=None, total=None)
            except Exception as e:
                traceback.print_exc()
                self._set(chapter_id, status="error", label="Erreur", error=str(e))
