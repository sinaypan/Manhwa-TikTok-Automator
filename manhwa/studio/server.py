"""Serveur du Studio (FastAPI). Écoute sur 127.0.0.1 : rien n'est accessible de l'extérieur.

Un chapitre est désigné par son chemin relatif à l'inbox (« Série/chapter-001 »).
"""
import threading
from pathlib import Path

import cv2
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from manhwa.config import inbox_dir
from manhwa.panels import ensure_cuts, find_gutters, panels_from_cuts
from manhwa.progress import chapter_progress
from manhwa.project import Chapter, find_chapters, is_chapter_dir
from manhwa.studio import tiles
from manhwa.studio.jobs import Jobs

STATIC = Path(__file__).parent / "static"


def create_app(cfg):
    inbox = inbox_dir(cfg).resolve()
    jobs = Jobs(cfg)
    locks = {}
    locks_guard = threading.Lock()
    app = FastAPI(title="Manhwa Studio", docs_url=None, redoc_url=None)

    def lock_for(chapter_id):
        with locks_guard:
            return locks.setdefault(chapter_id, threading.Lock())

    def chapter_of(chapter_id):
        path = (inbox / chapter_id).resolve()
        if not path.is_relative_to(inbox) or not path.is_dir() or not is_chapter_dir(path):
            raise HTTPException(404, "Chapitre introuvable")
        return Chapter(path)

    def id_of(chapter):
        return chapter.root.resolve().relative_to(inbox).as_posix()

    def prepared(chapter_id):
        chapter = chapter_of(chapter_id)
        with lock_for(chapter_id):
            analysis, meta = tiles.prepare(chapter, cfg)
            if analysis is None:
                raise HTTPException(422, "Aucune image lisible dans ce chapitre")
            data, _ = ensure_cuts(chapter, cfg, analysis=analysis)
        return chapter, analysis, meta, data

    def describe_panels(cut_ys, analysis):
        screen = analysis["width"] * 16 / 9
        return [{"y0": a, "y1": b, "screens": round((b - a) / screen, 2)}
                for a, b in panels_from_cuts(cut_ys, analysis["std"])]

    # ---------- Bibliothèque ----------

    @app.get("/api/library")
    def library():
        running = jobs.snapshot()
        series = {}
        for chapter in find_chapters(inbox):
            cid = id_of(chapter)
            name = cid.split("/")[0] if "/" in cid else "Sans série"
            series.setdefault(name, []).append({
                "id": cid,
                "name": chapter.root.name,
                "progress": chapter_progress(chapter, cfg),
                "job": running.get(cid),
            })
        out = []
        for name, chapters in series.items():
            done = sum(c["progress"]["done"] for c in chapters)
            total = sum(c["progress"]["total"] for c in chapters)
            out.append({"name": name, "chapters": chapters, "done": done, "total": total})
        return {"series": out, "inbox": str(inbox)}

    # ---------- Découpe ----------

    @app.get("/api/chapter")
    def chapter_detail(id: str = Query(...)):
        chapter, analysis, meta, data = prepared(id)
        cut = data["cut"]
        # frames de l'ancienne fenêtre de découpe : elles n'ont pas de numéro de case
        manual = bool(data["frames"]) and not any("panel" in f for f in data["frames"])
        stale = bool(data["frames"]) and not manual and not cut.get("validated")
        return {
            "id": id,
            "series": id.split("/")[0],
            "name": chapter.root.name,
            "width": analysis["width"],
            "height": analysis["height"],
            "screen": round(analysis["width"] * 16 / 9),
            "tiles": meta,
            "cuts": cut["cuts"],
            "gutters": find_gutters(analysis["std"], analysis["mean"], analysis["width"]),
            "panels": describe_panels([c["y"] for c in cut["cuts"]], analysis),
            "edited": cut.get("edited", False),
            "reviewed": cut.get("reviewed", False),
            "checked": cut.get("checked", []),
            "validated": cut.get("validated", False),
            "manual_frames": len(data["frames"]) if manual else 0,
            "stale_frames": stale,
            "progress": chapter_progress(chapter, cfg),
            "job": jobs.get(id),
        }

    @app.get("/api/tile")
    def tile(id: str = Query(...), i: int = Query(..., ge=0)):
        chapter = chapter_of(id)
        path = tiles.tiles_dir(chapter) / f"{i:04d}.jpg"
        if not path.is_file():
            raise HTTPException(404, "Vignette introuvable")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    @app.put("/api/cuts")
    def save_cuts(id: str = Query(...), payload: dict = Body(...)):
        chapter, analysis, _, data = prepared(id)
        H = analysis["height"]
        cuts = []
        for c in payload.get("cuts", []):
            y = int(c["y"])
            if 0 < y < H:
                cuts.append({"y": y, "sure": bool(c.get("sure", True))})
        cuts.sort(key=lambda c: c["y"])
        with lock_for(id):
            data = chapter.load()
            data["cut"].update({"cuts": cuts, "edited": True, "validated": False,
                                "reviewed": bool(payload.get("reviewed", False)),
                                "checked": [int(y) for y in payload.get("checked", [])][:500]})
            chapter.save(data)
        return {"cuts": cuts, "panels": describe_panels([c["y"] for c in cuts], analysis)}

    @app.post("/api/cuts/reset")
    def reset_cuts(id: str = Query(...)):
        chapter = chapter_of(id)
        with lock_for(id):
            data = chapter.load()
            data.pop("cut", None)
            chapter.save(data)
        return chapter_detail(id)

    @app.get("/api/panel")
    def panel_frames(id: str = Query(...), y0: int = Query(..., ge=0), y1: int = Query(..., gt=0)):
        """Les frames que la vidéo fera pour une case (pour un aperçu fidèle)."""
        chapter, analysis, meta, _ = prepared(id)
        frames = tiles.panel_frames(chapter, meta, analysis, y0, min(y1, analysis["height"]))
        if frames is None:
            raise HTTPException(404, "Case introuvable")
        return frames

    @app.get("/api/preview")
    def panel_preview(id: str = Query(...), y0: int = Query(..., ge=0), y1: int = Query(..., gt=0),
                      x0: int | None = Query(None, ge=0), x1: int | None = Query(None, gt=0)):
        chapter, analysis, meta, _ = prepared(id)
        img = tiles.preview(chapter, meta, analysis, y0, min(y1, analysis["height"]), x0, x1,
                            bg_mode=cfg["slicer"]["bg_mode"])  # même fond que les frames
        if img is None:
            raise HTTPException(404, "Aperçu impossible")
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return Response(buf.tobytes(), media_type="image/jpeg")

    # ---------- Vidéo ----------

    @app.post("/api/make")
    def make(id: str = Query(...)):
        chapter = chapter_of(id)
        return jobs.submit(id, chapter)

    @app.get("/api/video")
    def video(id: str = Query(...)):
        chapter = chapter_of(id)
        if not chapter.video_path.is_file():
            raise HTTPException(404, "Pas encore de vidéo")
        return FileResponse(chapter.video_path, media_type="video/mp4")

    @app.get("/api/jobs")
    def all_jobs():
        return jobs.snapshot()

    # ---------- Page ----------

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def serve(cfg, host="127.0.0.1", port=8765, open_browser=True):
    import webbrowser

    import uvicorn

    url = f"http://{host}:{port}/"
    print(f"Studio : {url}  (Ctrl+C pour arrêter)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(cfg), host=host, port=port, log_level="warning")
