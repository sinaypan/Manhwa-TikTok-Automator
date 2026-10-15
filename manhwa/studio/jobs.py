"""Travaux en arrière-plan : frames → OCR → voix → vidéo, un chapitre à la fois."""
import queue
import threading
import traceback

STEP_LABELS = {"frames": "Frames", "ocr": "Lecture du texte", "tts": "Voix", "render": "Rendu vidéo"}


class Jobs:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.state = {}  # id du chapitre → {"step", "label", "status", "error"}
        self.queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def snapshot(self):
        with self.lock:
            return {k: dict(v) for k, v in self.state.items()}

    def get(self, chapter_id):
        with self.lock:
            job = self.state.get(chapter_id)
            return dict(job) if job else None

    def submit(self, chapter_id, chapter):
        with self.lock:
            current = self.state.get(chapter_id)
            if current and current["status"] in ("queued", "running"):
                return dict(current)
            self.state[chapter_id] = {"step": None, "label": "En attente", "status": "queued", "error": None}
        self.queue.put((chapter_id, chapter))
        return self.get(chapter_id)

    def _set(self, chapter_id, **changes):
        with self.lock:
            self.state[chapter_id].update(changes)

    def _worker(self):
        from manhwa.ocr import run_ocr
        from manhwa.panels import build_frames
        from manhwa.render import run_render
        from manhwa.tts import run_tts

        steps = [
            ("frames", lambda c: build_frames(c, self.cfg)),
            ("ocr", lambda c: run_ocr(c, self.cfg)),
            ("tts", lambda c: run_tts(c, self.cfg)),
            ("render", lambda c: run_render(c, self.cfg)),
        ]
        while True:
            chapter_id, chapter = self.queue.get()
            try:
                for step, run in steps:
                    self._set(chapter_id, step=step, label=STEP_LABELS[step], status="running")
                    run(chapter)
                self._set(chapter_id, step=None, label="Terminé", status="done")
            except Exception as e:
                traceback.print_exc()
                self._set(chapter_id, status="error", label="Erreur", error=str(e))
