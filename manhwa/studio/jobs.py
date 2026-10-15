"""Travaux en arrière-plan, un à la fois : la vidéo (frames → OCR → voix → rendu) ou les visages."""
import queue
import threading
import time
import traceback

STEP_LABELS = {"frames": "Frames", "ocr": "Lecture du texte", "tts": "Voix", "render": "Rendu vidéo",
               "faces": "Recherche des visages"}
# ce que l'on compte à chaque étape (« 6 210 / 12 960 images »)
STEP_UNITS = {"frames": "frames", "ocr": "frames lues", "tts": "voix", "render": "images", "faces": "frames"}


class Jobs:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        # id du chapitre → {"kind" ("make" ou "faces"), "step", "label", "status", "error",
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

    def submit(self, chapter_id, chapter, kind="make"):
        with self.lock:
            current = self.state.get(chapter_id)
            if current and current["status"] in ("queued", "running"):
                return dict(current)
            self.state[chapter_id] = {"kind": kind, "step": None, "label": "En attente", "status": "queued", "error": None,
                                      "progress": None, "done": None, "total": None, "unit": None,
                                      "step_started": None}
        self.queue.put((chapter_id, chapter, kind))
        return self.get(chapter_id)

    def _set(self, chapter_id, **changes):
        with self.lock:
            self.state[chapter_id].update(changes)

    def _worker(self):
        from manhwa.cast import run_faces
        from manhwa.ocr import run_ocr
        from manhwa.panels import build_frames
        from manhwa.render import run_render
        from manhwa.tts import run_tts

        kinds = {
            "make": [
                ("frames", lambda c, p: build_frames(c, self.cfg, progress=p)),
                ("ocr", lambda c, p: run_ocr(c, self.cfg, progress=p)),
                ("tts", lambda c, p: run_tts(c, self.cfg, progress=p)),
                ("render", lambda c, p: run_render(c, self.cfg, progress=p)),
            ],
            "faces": [("faces", lambda c, p: run_faces(c, self.cfg, progress=p))],
        }
        while True:
            chapter_id, chapter, kind = self.queue.get()
            try:
                for step, run in kinds[kind]:
                    self._set(chapter_id, step=step, label=STEP_LABELS[step], status="running", progress=None,
                              done=None, total=None, unit=STEP_UNITS[step], step_started=time.time())
                    run(chapter, lambda done, total, cid=chapter_id: self._set(
                        cid, progress=round(done / total, 4) if total else None, done=done, total=total))
                self._set(chapter_id, step=None, label="Terminé", status="done", progress=None, done=None, total=None)
            except Exception as e:
                traceback.print_exc()
                self._set(chapter_id, status="error", label="Erreur", error=str(e))
