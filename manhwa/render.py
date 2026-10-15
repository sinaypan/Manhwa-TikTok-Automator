"""Assemblage vidéo (V1) : chaque frame dure le temps de sa voix.

Temporaire : remplacé par le rendu ffmpeg (défilement, sous-titres, musique) en phase 5.
"""
import os

from manhwa.project import fingerprint


def render_key(chapter, data, cfg):
    parts = []
    for frame in data["frames"]:
        img = chapter.frames_dir / frame["file"]
        stat = img.stat() if img.is_file() else None
        parts.append([frame["file"], stat and stat.st_size, stat and stat.st_mtime_ns, frame.get("audio_key")])
    return fingerprint(parts, cfg["render"], cfg["output"])


def _load_audio(path):
    from moviepy import AudioFileClip

    if not path.is_file() or path.stat().st_size <= 100:
        return None
    try:
        return AudioFileClip(str(path))
    except Exception:
        print(f"  [!] Audio illisible ignoré : {path.name}")
        return None


def run_render(chapter, cfg, force=False):
    data = chapter.load()
    if not data["frames"]:
        print("  Aucune frame à assembler.")
        return False

    key = render_key(chapter, data, cfg)
    if not force and chapter.video_path.is_file() and data["steps"].get("render", {}).get("key") == key:
        print(f"  Vidéo déjà à jour : {chapter.video_path.name}")
        return False

    from moviepy import ImageClip, concatenate_videoclips

    r = cfg["render"]
    clips, audios = [], []
    for frame in data["frames"]:
        img = chapter.frames_dir / frame["file"]
        if not img.is_file():
            print(f"  [!] Frame manquante ignorée : {frame['file']}")
            continue
        audio = _load_audio(chapter.root / frame["audio"]) if frame.get("audio") else None
        if audio:
            audios.append(audio)
            clip = ImageClip(str(img)).with_duration(audio.duration + r["padding_seconds"]).with_audio(audio)
        else:
            clip = ImageClip(str(img)).with_duration(r["silent_frame_seconds"])
        clips.append(clip)

    if not clips:
        print("  Rien à assembler.")
        return False

    tmp = chapter.root / "video.part.mp4"
    print(f"  Rendu de {len(clips)} frames...")
    try:
        final = concatenate_videoclips(clips, method="compose")
        final.write_videofile(str(tmp), fps=r["fps"], codec="libx264", audio_codec="aac",
                              preset="ultrafast", threads=4)
        final.close()
    finally:
        for c in clips + audios:
            c.close()
    os.replace(tmp, chapter.video_path)

    data["steps"]["render"] = {"key": key}
    chapter.save(data)
    print(f"  Vidéo : {chapter.video_path}")
    return True
