"""Avancement d'un chapitre : quelles étapes sont faites (partagé par la CLI et le Studio)."""

STEPS = ("pages", "découpe", "texte", "voix", "vidéo")


def chapter_progress(chapter, cfg):
    """{"done": n étapes faites sur 5, "next": prochaine étape, "pages", "frames", "texts"}.

    Une étape ne compte que si toutes les précédentes sont faites et à jour.
    """
    from manhwa.bubbles import BUBBLES_VERSION
    from manhwa.ocr import ocr_key
    from manhwa.render import render_key
    from manhwa.tts import tts_up_to_date

    data = chapter.load()
    frames = data["frames"]
    pages = len(chapter.pages())
    texts = [f for f in frames if f.get("text")]
    ocr_done = bool(frames) and all(
        f.get("ocr_key") == ocr_key(f, data, cfg) and "lines" in f and f.get("bubbles_version") == BUBBLES_VERSION
        for f in frames
    )
    tts_done = ocr_done and tts_up_to_date(chapter, data, cfg)
    video_done = (
        chapter.video_path.is_file()
        and data["steps"].get("render", {}).get("key") == render_key(chapter, data, cfg)
    )
    checks = [pages > 0, bool(frames), ocr_done, tts_done, video_done]
    done = next((i for i, ok in enumerate(checks) if not ok), len(checks))
    return {
        "done": done,
        "total": len(STEPS),
        "next": STEPS[done] if done < len(STEPS) else None,
        "pages": pages,
        "frames": len(frames),
        "texts": len(texts),
        "video": chapter.video_path.is_file(),
    }
