"""Serveur du Studio (FastAPI). Écoute sur 127.0.0.1 : rien n'est accessible de l'extérieur.

Un chapitre est désigné par son chemin relatif à l'inbox (« Série/chapter-001 »).
"""
import threading
from pathlib import Path

import cv2
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from manhwa import cast, llm, review, sfx, voices
from manhwa.config import inbox_dir
from manhwa.images import read_image
from manhwa.ingest import wiki
from manhwa.panels import ensure_cuts, find_gutters, load_analysis, panels_from_cuts
from manhwa.progress import chapter_progress
from manhwa.project import Chapter, find_chapters, is_chapter_dir
from manhwa.studio import tiles
from manhwa.studio.jobs import IMPORT_ID, Jobs
from manhwa.tts import narrator_voice

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
        return {"series": out, "inbox": str(inbox), "import": running.get(IMPORT_ID)}

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
        chapter, analysis, meta, data = prepared(id)
        frames = tiles.panel_frames(chapter, meta, analysis, y0, min(y1, analysis["height"]))
        if frames is None:
            raise HTTPException(404, "Case introuvable")
        # ce que l'OCR a déjà lu sur les frames de cette case (si la vidéo a été créée)
        read = [f for f in data["frames"] if y0 <= f["crop"][1] < y1 and "bubbles" in f]
        frames["bubbles"] = [{"text": b["text"], "kind": b["kind"]} for f in read for b in f["bubbles"]]
        frames["ocr_done"] = bool(read)
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

    # ---------- Personnages ----------

    def cast_lock(chapter):
        return lock_for(f"cast:{cast.series_dir(chapter)}")  # les personnages sont partagés par la série

    def cast_detail(id):
        from manhwa.faces import faces_key

        chapter = chapter_of(id)
        data = chapter.load()
        crew = cast.load_cast(chapter)
        faces = cast.chapter_faces(data)
        if "faces" not in data:
            status = "missing"
        elif data["faces"]["key"] != faces_key(load_analysis(chapter, cfg, compute=False), data["frames"]):
            status = "stale"  # la découpe a changé depuis
        else:
            status = "ready"
        series = cast.series_dir(chapter)
        wiki_data = wiki.load_wiki(series)
        suggest = cast.wiki_suggestions(chapter, data, crew, wiki_data, wiki.wiki_vectors(series)) if status != "missing" else {}
        characters = [{"id": c["id"], "name": c["name"], "cover": c.get("cover"), "wiki": c.get("wiki"),
                       "silent": bool(c.get("silent")), "suggest": suggest.get(c["id"], []),
                       "voice": c.get("voice"), "voice_ok": bool(c.get("voice_ok")),
                       "faces": [f["id"] for f in faces if f.get("char") == c["id"] and not f.get("not_face")]}
                      for c in crew["characters"]]
        number = cast.chapter_number(chapter)
        people = []
        for w in (wiki_data or {}).get("characters", []):
            people.append({k: w.get(k) for k in ("id", "title", "name", "gender", "hair", "debut", "personality")}
                          | {"url": wiki_data["base"] + w["url"], "image": (w.get("files") or [None])[0],
                             "thumb": wiki.thumb_path(series, w["id"]).is_file(),
                             "later": bool(w.get("debut") and number and w["debut"] > number)})
        return {
            "wiki": {"sitename": wiki_data["sitename"], "fetched": wiki_data["fetched"],
                     "images": sum(len(w.get("files", [])) for w in wiki_data["characters"]),
                     "listed": sum(len(w.get("images", [])) for w in wiki_data["characters"])} if wiki_data else None,
            "people": people,
            "face_views": cast.face_views(data),
            "status": status,
            "frames": len(data["frames"]),
            "ocr_done": any("bubbles" in f for f in data["frames"]),
            "characters": characters,
            "unsorted": [f["id"] for f in faces if not f.get("char") and not f.get("not_face")],
            "rejected": [f["id"] for f in faces if f.get("not_face")],
            "lines": cast.lines(data, crew) if status != "missing" else [],
            "narrator": cast.NARRATOR,
            "extras": {k: {"label": v[0], "voice": cast.extra_voice(crew, k, cfg)} for k, v in cast.EXTRAS.items()},
            "narrator_voice": narrator_voice(cfg, crew),
            "voices": voice_list(),
            "emotions": voices.EMOTION_LABELS,
            "gpt": llm.public_settings(),
            "job": jobs.get(id),
        }

    @app.get("/api/cast")
    def cast_get(id: str = Query(...)):
        return cast_detail(id)

    @app.post("/api/cast/analyze")
    def cast_analyze(id: str = Query(...), force: bool = Query(False)):
        chapter = chapter_of(id)
        with lock_for(id):
            data = chapter.load()
            if not data["frames"]:
                raise HTTPException(422, "Crée d'abord la vidéo : les visages se cherchent dans ses frames")
            if force and data.get("faces"):
                data["faces"]["key"] = None  # chercher à nouveau ; les visages déjà rangés servent de modèles
                chapter.save(data)
        return jobs.submit(id, chapter, kind="faces")

    @app.post("/api/cast/move")
    def cast_move(id: str = Query(...), payload: dict = Body(...)):
        chapter = chapter_of(id)
        with cast_lock(chapter), lock_for(id):
            data = chapter.load()
            crew = cast.load_cast(chapter)
            try:
                target = cast.move_faces(chapter, data, crew, [str(f) for f in payload.get("faces", [])][:2000],
                                         str(payload.get("to", "")))
            except ValueError as e:
                raise HTTPException(422, str(e))
            chapter.save(data)
            cast.prune(chapter, crew)
            cast.save_cast(chapter, crew)
        return {**cast_detail(id), "moved_to": target}

    @app.put("/api/cast/character")
    def cast_character(id: str = Query(...), payload: dict = Body(...)):
        """Nom, fiche du wiki liée, « ne parle pas »."""
        chapter = chapter_of(id)
        changes = {k: payload[k] for k in ("name", "wiki", "silent", "voice", "voice_ok") if k in payload}
        with cast_lock(chapter):
            crew = cast.load_cast(chapter)
            try:
                cast.update_character(crew, str(payload.get("char", "")), changes, wiki.load_wiki(cast.series_dir(chapter)))
            except ValueError as e:
                raise HTTPException(422, str(e))
            cast.save_cast(chapter, crew)
        return cast_detail(id)

    @app.post("/api/cast/new")
    def cast_new(id: str = Query(...), payload: dict = Body(...)):
        """Un personnage secondaire (sans visage), créé depuis une réplique, qui la dit tout de suite."""
        chapter = chapter_of(id)
        with cast_lock(chapter), lock_for(id):
            crew = cast.load_cast(chapter)
            try:
                cid = cast.add_character(crew, payload.get("name"))
            except ValueError as e:
                raise HTTPException(422, str(e))
            cast.save_cast(chapter, crew)
            if payload.get("key"):
                data = chapter.load()
                cast.set_speakers(data, [{"key": payload["key"], "char": cid}])
                chapter.save(data)
        return {**cast_detail(id), "created": cid}

    @app.put("/api/cast/extra")
    def cast_extra(id: str = Query(...), payload: dict = Body(...)):
        chapter = chapter_of(id)
        extra = payload.get("extra")
        if extra not in cast.EXTRAS:
            raise HTTPException(422, "Figurant inconnu")
        with cast_lock(chapter):
            crew = cast.load_cast(chapter)
            try:
                crew.setdefault("extras", {}).setdefault(extra, {})["voice"] = cast.clean_voice(payload.get("voice"))
            except ValueError as e:
                raise HTTPException(422, str(e))
            cast.save_cast(chapter, crew)
        return cast_detail(id)

    @app.post("/api/cast/wiki")
    def cast_wiki(id: str = Query(...), images: bool = Query(False)):
        """Lire le wiki de la série ; images=1 : télécharger aussi ses images (vérification à la main)."""
        chapter = chapter_of(id)
        return jobs.submit(id, chapter, kind="wiki_images" if images else "wiki")

    @app.get("/api/wiki_thumb")
    def wiki_thumb(id: str = Query(...), w: str = Query(..., pattern=r"^w\d+$")):
        """La tête d'un personnage du wiki (pour la liste des noms)."""
        path = wiki.thumb_path(cast.series_dir(chapter_of(id)), w)
        if not path.is_file():
            raise HTTPException(404, "Pas d'image")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/wiki_image")
    def wiki_image(id: str = Query(...), f: str = Query(..., pattern=r"^w\d+-\d+\.img$")):
        chapter = chapter_of(id)
        img = read_image(wiki.wiki_dir(cast.series_dir(chapter)) / f)
        if img is None:
            raise HTTPException(404, "Image introuvable")
        h, w = img.shape[:2]
        img = cv2.resize(img, (240, max(1, round(h * 240 / w))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    @app.post("/api/cast/speakers")
    def cast_speakers(id: str = Query(...), payload: dict = Body(...)):
        chapter = chapter_of(id)
        with lock_for(id):
            data = chapter.load()
            changed = cast.set_speakers(data, list(payload.get("choices", []))[:5000])
            chapter.save(data)
        return {**cast_detail(id), "changed": changed}

    @app.get("/api/face")
    def face_image(id: str = Query(...), f: str = Query(..., pattern=r"^([\w .-]+/)?f\d{4}$")):
        chapter = chapter_of(id)
        if "/" in f:  # visage d'un autre épisode de la série (couverture d'un personnage)
            other, f = f.split("/")
            folder = (cast.series_dir(chapter) / other).resolve()
            if not folder.is_relative_to(inbox) or not is_chapter_dir(folder):
                raise HTTPException(404, "Visage introuvable")
            chapter = Chapter(folder)
        path = cast.faces_dir(chapter) / f"{f}.jpg"
        if not path.is_file():
            raise HTTPException(404, "Visage introuvable")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=600"})

    @app.get("/api/crop")
    def frame_region(id: str = Query(...), frame: str = Query(...), y: int = Query(0, ge=0), h: int = Query(..., gt=0),
                     w: int = Query(360, ge=120, le=720)):
        """Un morceau de case (la bulle et les visages autour), pour l'écran Personnages."""
        chapter, analysis, meta, data = prepared(id)
        match = next((f for f in data["frames"] if f["file"] == frame), None)
        if not match:
            raise HTTPException(404, "Frame introuvable")
        cx, cy, cw, ch = match["crop"]
        img = tiles.region(chapter, meta, analysis, cx, cy + y, cw, min(h, ch - y), out_w=w)
        if img is None:
            raise HTTPException(404, "Aperçu impossible")
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "max-age=600"})

    @app.get("/api/strip")
    def strip_region(id: str = Query(...), y: int = Query(0, ge=0), h: int = Query(..., gt=0), w: int = Query(480, ge=120, le=720)):
        """Un morceau du chapitre sur toute sa largeur : le contexte d'une réplique ou d'un visage."""
        chapter, analysis, meta, _ = prepared(id)
        img = tiles.region(chapter, meta, analysis, 0, y, analysis["width"], min(h, analysis["height"] - y), out_w=w)
        if img is None:
            raise HTTPException(404, "Aperçu impossible")
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "max-age=600"})

    # ---------- Vidéo ----------

    @app.post("/api/make")
    def make(id: str = Query(...)):
        chapter = chapter_of(id)
        return jobs.submit(id, chapter)

    @app.post("/api/import")
    def import_chapters(payload: dict = Body(...)):
        """Tout en un clic : télécharge depuis le lien de la série, puis fait toute la vidéo."""
        url = str(payload.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(422, "Colle le lien de la page de la série (https://…)")
        chapters = str(payload.get("chapters") or "").strip()
        try:
            from manhwa.ingest.scraper import parse_selection

            parse_selection(chapters, [1.0])  # vérifie la forme (12, 1-5, latest…) avant de lancer
        except ValueError as e:
            raise HTTPException(422, str(e))
        return jobs.submit(IMPORT_ID, None, "import", {"url": url, "chapters": chapters, "auto": bool(payload.get("auto", True))})

    @app.post("/api/auto")
    def auto(id: str = Query(...)):
        """Toutes les étapes d'un coup sur un chapitre déjà là."""
        return jobs.submit(id, chapter_of(id), kind="auto")

    @app.get("/api/video")
    def video(id: str = Query(...)):
        chapter = chapter_of(id)
        if not chapter.video_path.is_file():
            raise HTTPException(404, "Pas encore de vidéo")
        return FileResponse(chapter.video_path, media_type="video/mp4")

    @app.get("/api/jobs")
    def all_jobs():
        return jobs.snapshot()

    # ---------- Voix ----------

    def voice_list():
        try:
            return [dict(v, label=voices.short_name(v["name"])) for v in voices.list_voices()]
        except Exception:
            return []

    @app.post("/api/cast/voices")
    def cast_voices(id: str = Query(...)):
        """GPT propose une voix pour chaque personnage dont la voix n'est pas validée."""
        if not llm.public_settings()["configured"]:
            raise HTTPException(422, "Colle d'abord la clé GPT (Réglages)")
        return jobs.submit(id, chapter_of(id), kind="voices")

    @app.put("/api/cast/narrator")
    def cast_narrator(id: str = Query(...), payload: dict = Body(...)):
        chapter = chapter_of(id)
        with cast_lock(chapter):
            crew = cast.load_cast(chapter)
            try:
                crew.setdefault("narrator", {})["voice"] = cast.clean_voice(payload.get("voice"))
            except ValueError as e:
                raise HTTPException(422, str(e))
            cast.save_cast(chapter, crew)
        return cast_detail(id)

    @app.get("/api/voice_sample")
    def voice_sample(id: str = Query(...), char: str = Query(...), name: str | None = Query(None),
                     pitch: str | None = Query(None), rate: str | None = Query(None)):
        """Un extrait de la voix : une réplique du personnage (ou une phrase type), avec ses réglages."""
        chapter = chapter_of(id)
        crew = cast.load_cast(chapter)
        if char == cast.NARRATOR:
            voice = narrator_voice(cfg, crew)
        elif char in cast.EXTRAS:
            voice = cast.extra_voice(crew, char, cfg)
        else:
            c = cast.character(crew, char)
            if not c:
                raise HTTPException(404, "Personnage inconnu")
            voice = c.get("voice") or narrator_voice(cfg, crew)
        if name:  # essai d'une autre voix avant de la choisir
            voice = {"name": name, "pitch": pitch or "+0Hz", "rate": rate or "+0%"}
        if voice["name"] not in {v["name"] for v in voice_list()}:
            raise HTTPException(422, "Voix inconnue")
        data = chapter.load()
        said = [l["text"] for l in cast.lines(data, crew) if (l["speaker"] or l["suggestion"]) == char]
        # une réplique de 40 à 120 lettres : assez pour juger la voix, vite fabriquée
        fitting = [t for t in said if 40 <= len(t) <= 120] or said
        text = (fitting[0] if fitting else "") or "I have walked this road for a long time, and I am not done yet."
        try:
            path = voices.sample(voices.prosody(cfg, voice), text[:140])
        except Exception as e:
            raise HTTPException(502, f"Extrait impossible : {e}")
        return FileResponse(path, media_type="audio/mpeg")

    # ---------- Relecture GPT ----------

    def review_detail(id):
        chapter = chapter_of(id)
        data = chapter.load()
        crew = cast.load_cast(chapter)
        items = review.proposals(data, crew)
        return {
            "gpt": llm.public_settings(),
            "done": any(f.get("review") for f in data["frames"]),
            "ocr_done": any("bubbles" in f for f in data["frames"]),
            "items": items,
            "kinds": {"dialogue": "réplique", "thought": "pensée", "narration": "narration", "sfx": "bruitage",
                      "noise": "pas du texte"},
            "job": jobs.get(id),
        }

    @app.get("/api/review")
    def review_get(id: str = Query(...)):
        return review_detail(id)

    @app.post("/api/review/run")
    def review_run(id: str = Query(...)):
        if not llm.public_settings()["configured"]:
            raise HTTPException(422, "Colle d'abord la clé GPT (Réglages)")
        chapter = chapter_of(id)
        if not any("bubbles" in f for f in chapter.load()["frames"]):
            raise HTTPException(422, "Crée d'abord la vidéo : le texte doit être lu")
        return jobs.submit(id, chapter, kind="review")

    @app.post("/api/review/decide")
    def review_decide(id: str = Query(...), payload: dict = Body(...)):
        chapter = chapter_of(id)
        with lock_for(id):
            data = chapter.load()
            n = review.decide(data, list(payload.get("decisions", []))[:5000])
            chapter.save(data)
        return {**review_detail(id), "changed": n}

    @app.put("/api/review/emotion")
    def review_emotion(id: str = Query(...), payload: dict = Body(...)):
        chapter = chapter_of(id)
        with lock_for(id):
            data = chapter.load()
            try:
                review.set_emotion(data, payload.get("key"), payload.get("emotion"))
            except ValueError as e:
                raise HTTPException(422, str(e))
            chapter.save(data)
        return cast_detail(id)

    # ---------- Bruitages et musique ----------

    def sounds_detail(id):
        from manhwa.render import music_file

        chapter = chapter_of(id)
        data = chapter.load()
        try:
            sfx.ensure_library()
            ready = True
        except Exception:
            ready = False
        music = music_file(cfg)
        return {"spots": sfx.spots(data), "actions": sfx.silent_frames(data), "categories": sfx.labels(),
                "gpt": llm.public_settings(), "none": sfx.NONE, "library": ready,
                "music": Path(music).name if music else None, "ocr_done": any("bubbles" in f for f in data["frames"]),
                "job": jobs.get(id)}

    @app.get("/api/sounds")
    def sounds_get(id: str = Query(...)):
        return sounds_detail(id)

    @app.post("/api/sounds")
    def sounds_set(id: str = Query(...), payload: dict = Body(...)):
        chapter = chapter_of(id)
        with lock_for(id):
            data = chapter.load()
            try:
                sfx.set_sounds(data, list(payload.get("choices", []))[:2000])
            except ValueError as e:
                raise HTTPException(422, str(e))
            chapter.save(data)
        return sounds_detail(id)

    @app.post("/api/sounds/suggest")
    def sounds_suggest(id: str = Query(...)):
        """GPT propose un son pour les cases sans texte."""
        if not llm.public_settings()["configured"]:
            raise HTTPException(422, "Colle d'abord la clé GPT (Réglages)")
        return jobs.submit(id, chapter_of(id), kind="sounds")

    @app.get("/api/sfx_sample")
    def sfx_sample(cat: str = Query(...), text: str = Query("")):
        if cat not in sfx.CATEGORIES:
            raise HTTPException(404, "Catégorie inconnue")
        sfx.ensure_library()
        path = sfx.pick(cat, text)
        if not path:
            raise HTTPException(404, "Aucun son dans cette catégorie")
        kind = {".ogg": "audio/ogg", ".wav": "audio/wav", ".mp3": "audio/mpeg"}.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=kind, headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/music")
    def music():
        from manhwa.render import music_file

        path = music_file(cfg)
        if not path:
            raise HTTPException(404, "Pas de musique")
        return FileResponse(path)

    # ---------- Vidéo : regarder et signaler un passage ----------

    FLAG_REASONS = {"voice": "Mauvaise voix", "text": "Texte faux", "sound": "Mauvais son", "cut": "Découpe",
                    "other": "Autre"}

    def video_detail(id):
        chapter = chapter_of(id)
        data = chapter.load()
        crew = cast.load_cast(chapter)
        labels = {c["id"]: c["name"] or f"Perso {i + 1}" for i, c in enumerate(crew["characters"])}
        labels[cast.NARRATOR] = "Narrateur"
        labels.update({k: v[0] for k, v in cast.EXTRAS.items()})
        frames = {f["file"]: f for f in data["frames"]}
        sounds = sfx.frame_sounds(data)
        timeline = []
        for k, (file, start, duration) in enumerate((data["steps"].get("render") or {}).get("timeline") or []):
            frame = frames.get(file) or {}
            timeline.append({
                "frame": file, "index": k, "start": start, "duration": duration, "crop": frame.get("crop"),
                "lines": [{"text": seg["text"], "speaker": labels.get(seg.get("speaker"), "?"),
                           "voice": voices.short_name(seg.get("voice")), "emotion": voices.EMOTION_LABELS.get(seg.get("emotion"), "")}
                          for seg in frame.get("segments") or []],
                "sounds": [Path(x).parent.name for x in sounds.get(file, [])],
            })
        return {"video": chapter.video_path.is_file(), "timeline": timeline, "flags": data.get("flags", []),
                "reasons": FLAG_REASONS, "job": jobs.get(id)}

    @app.get("/api/video_info")
    def video_info(id: str = Query(...)):
        return video_detail(id)

    @app.post("/api/flags")
    def flag_add(id: str = Query(...), payload: dict = Body(...)):
        chapter = chapter_of(id)
        reason = payload.get("reason")
        if reason not in FLAG_REASONS:
            raise HTTPException(422, "Raison inconnue")
        with lock_for(id):
            data = chapter.load()
            if not any(f["file"] == payload.get("frame") for f in data["frames"]):
                raise HTTPException(422, "Frame inconnue")
            flags = data.setdefault("flags", [])
            flags.append({"id": max((f["id"] for f in flags), default=0) + 1, "frame": payload["frame"],
                          "t": round(float(payload.get("t") or 0), 2), "reason": reason,
                          "note": str(payload.get("note") or "")[:200], "done": False})
            chapter.save(data)
        return video_detail(id)

    @app.put("/api/flags/{flag_id}")
    def flag_update(flag_id: int, id: str = Query(...), payload: dict = Body(...)):
        chapter = chapter_of(id)
        with lock_for(id):
            data = chapter.load()
            flag = next((f for f in data.get("flags", []) if f["id"] == flag_id), None)
            if not flag:
                raise HTTPException(404, "Signalement introuvable")
            if payload.get("delete"):
                data["flags"].remove(flag)
            else:
                flag["done"] = bool(payload.get("done"))
            chapter.save(data)
        return video_detail(id)

    # ---------- Réglages (clé GPT) ----------

    @app.get("/api/settings")
    def settings_get():
        return {"gpt": llm.public_settings()}

    @app.put("/api/settings/gpt")
    def settings_gpt(payload: dict = Body(...)):
        """Enregistre l'adresse, le modèle et la clé dans .env (jamais renvoyée au navigateur)."""
        key = str(payload.get("key") or "").strip()
        if key and (len(key) > 400 or any(ch.isspace() for ch in key)):
            raise HTTPException(422, "Clé illisible")
        base = str(payload.get("base") or "").strip()
        if base and not base.startswith(("http://", "https://")):
            raise HTTPException(422, "L'adresse doit commencer par https://")
        llm.save_settings(base=base or None, model=str(payload.get("model") or "").strip() or None, key=key or None)
        return {"gpt": llm.public_settings()}

    @app.post("/api/settings/gpt/test")
    def settings_test():
        try:
            ok = llm.ping()
        except llm.LLMError as e:
            raise HTTPException(422, str(e))
        return {"ok": ok}

    # ---------- Page ----------

    @app.get("/")
    def index():
        # app.js et app.css appelés avec leur date de modification : après une mise à jour du
        # Studio, le navigateur ne peut pas garder l'ancienne version en cache
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for name in ("app.js", "app.css"):
            version = int((STATIC / name).stat().st_mtime)
            html = html.replace(f"/static/{name}", f"/static/{name}?v={version}")
        return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})

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
