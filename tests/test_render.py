import wave

import numpy as np

from manhwa import render, sfx
from manhwa.config import load_config
from manhwa.images import write_jpeg
from manhwa.project import Chapter


def tone(path, seconds, freq=440, channels=1):
    rate = 22050
    t = np.arange(int(seconds * rate)) / rate
    pcm = (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    if channels == 2:
        pcm = np.repeat(pcm[:, None], 2, axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def test_zoom_and_pan_clips_keep_the_frame_size():
    img = np.random.default_rng(0).integers(0, 255, (192, 108, 3), dtype=np.uint8)
    z = render.zoom_clip(img, 2.0, 0.1)
    assert z.get_frame(0).shape == z.get_frame(1.9).shape == (192, 108, 3)
    assert not np.array_equal(z.get_frame(0), z.get_frame(1.9))
    tall = np.arange(400 * 108 * 3, dtype=np.uint32).reshape(400, 108, 3).astype(np.uint8)
    p = render.pan_clip(tall, 192, 3.0)
    assert p.get_frame(0).shape == (192, 108, 3)
    assert np.array_equal(p.get_frame(0), tall[:192]) and np.array_equal(p.get_frame(3.0), tall[-192:])


def test_render_with_voices_sfx_pan_and_music(tmp_path, monkeypatch):
    cfg = load_config()
    cfg["output"].update(width=108, height=192)
    cfg["render"].update(fps=6, speed=1.0, music=str(tmp_path / "music.wav"))
    tone(tmp_path / "music.wav", 1.0, 220, channels=2)
    ch = Chapter(tmp_path / "Série" / "chapter-001")
    pages = ch.root / "pages"
    pages.mkdir(parents=True)
    strip = np.random.default_rng(1).integers(0, 255, (900, 300, 3), dtype=np.uint8)
    write_jpeg(pages / "001.jpg", strip, 95)
    ch.frames_dir.mkdir()
    for name in ("frame_0001.jpg", "frame_0002.jpg"):
        write_jpeg(ch.frames_dir / name, np.full((192, 108, 3), 90, np.uint8))
    tone(ch.audio_dir / "a.wav", 0.6, 300, channels=2)
    tone(ch.audio_dir / "b.wav", 0.4, 500, channels=2)
    tone(tmp_path / "boom.wav", 0.3, 80)
    data = ch.load()
    data["frames"] = [
        # une case haute (700 px pour 300 de large) : elle défile ; deux répliques de deux voix
        {"file": "frame_0001.jpg", "crop": [0, 0, 300, 700], "bubbles": [],
         "segments": [{"audio": "audio/a.wav", "audio_key": "a"}, {"audio": "audio/b.wav", "audio_key": "b"}]},
        # une case sans texte mais avec un bruitage
        {"file": "frame_0002.jpg", "crop": [0, 700, 300, 200],
         "bubbles": [{"text": "KRAK", "kind": "sfx", "box": [0, 0, 50, 50]}], "sounds": {"KRAK": "wood"}},
    ]
    ch.save(data)
    monkeypatch.setattr(sfx, "ensure_library", lambda: tmp_path)
    monkeypatch.setattr(sfx, "pick", lambda cat, text, query=None: tmp_path / "boom.wav")

    assert render.run_render(ch, cfg)
    from moviepy import VideoFileClip

    v = VideoFileClip(str(ch.video_path))
    assert v.size == [108, 192] and v.audio is not None
    assert 1.0 + 2.0 - 0.3 < v.duration < 1.6 + 2.6
    v.close()
    assert ch.load()["steps"]["render"]["key"] == render.render_key(ch, ch.load(), cfg)
    assert not render.run_render(ch, cfg)  # déjà à jour
    data = ch.load()
    data["frames"][1]["sounds"] = {"KRAK": "none"}  # le bruitage retiré : la vidéo est à refaire
    ch.save(data)
    assert render.render_key(ch, ch.load(), cfg) != ch.load()["steps"]["render"]["key"]


def test_sound_spots_follow_gpt_unless_chosen():
    data = {"frames": [{"file": "f1", "crop": [0, 0, 10, 10], "bubbles": [
        {"text": "KRAK", "kind": "sfx", "box": [0, 0, 1, 1]}, {"text": "BAM", "kind": "sfx", "box": [0, 0, 1, 1]},
        {"text": "HI", "kind": "dialogue", "box": [0, 0, 1, 1]}],
        "review": {"KRAK": {"sfx": "wood", "state": {}}, "BAM": {"sfx": "impact", "state": {}}}}]}
    spots = {s["text"]: s for s in sfx.spots(data)}
    assert set(spots) == {"KRAK", "BAM"}
    assert spots["KRAK"]["sound"] == "wood" and spots["BAM"]["sound"] == sfx.NONE  # « impact » : trop vague
    sfx.set_sounds(data, [{"key": "f1#1", "sound": "punch"}, {"key": "f1#0", "sound": "none"}])
    spots = {s["text"]: s for s in sfx.spots(data)}
    assert spots["BAM"]["sound"] == "punch" and spots["KRAK"]["sound"] == sfx.NONE
    sfx.set_sounds(data, [{"key": "f1#0", "sound": None}])
    assert {s["text"]: s for s in sfx.spots(data)}["KRAK"]["sound"] == "wood"


def test_slide_transition_pushes_the_previous_frame_up():
    from moviepy import ColorClip

    a = ColorClip((10, 20), color=(255, 0, 0), duration=1.0)
    b = ColorClip((10, 20), color=(0, 0, 255), duration=1.0)
    video, starts = render.timeline([a, b], [1.0, 1.0], "slide", 0.3)
    assert starts == [0.0, 1.0] and video.duration == 2.0
    assert video.get_frame(0.5)[0, 0].tolist() == [255, 0, 0]
    mid = video.get_frame(1.15)  # en pleine transition : rouge en haut, bleu qui arrive en bas
    assert mid[0, 0].tolist() == [255, 0, 0] and mid[-1, 0].tolist() == [0, 0, 255]
    assert video.get_frame(1.5)[0, 0].tolist() == [0, 0, 255]
    fade, _ = render.timeline([a, b], [1.0, 1.0], "fade", 0.3)
    assert 0 < fade.get_frame(1.15)[0, 0, 0] < 255


def test_dialogue_rhythm_follows_who_answers_and_how():
    from manhwa import rhythm

    a = {"speaker": "c1", "emotion": "neutral", "text": "WE SHOULD GO NOW."}
    same = {"speaker": "c1", "emotion": "neutral", "text": "BEFORE THEY COME BACK."}
    other = {"speaker": "c2", "emotion": "neutral", "text": "WHY?"}
    assert rhythm.gap(a, same) < rhythm.gap(a, other)  # il continue : plus court qu'une réponse
    assert rhythm.gap(other, a) < rhythm.gap(a, other)  # une réponse à une question vient vite
    angry1, angry2 = dict(a, emotion="angry"), dict(other, emotion="shouting")
    assert rhythm.gap(angry1, angry2) < 0  # dispute : on se coupe la parole
    sad = dict(a, emotion="sad", text="SHE IS GONE...")
    assert rhythm.gap(sad, other) > rhythm.gap(a, other) and rhythm.tail(sad) > rhythm.tail(a)
    assert rhythm.tail(dict(a, text="RUN!")) > rhythm.tail(a)  # on laisse le cri retomber
    assert rhythm.tail(a, same) < rhythm.tail(a)  # il continue sur la case suivante


def test_long_cases_follow_the_bubbles():
    import numpy as np

    from manhwa import motion

    keys = motion.guide_keys((100, 200, 800, 600), 400, [(0.0, (0, 0, 40, 40)), (4.0, (300, 250, 60, 40))], 9.0)
    assert keys[0][1:3] == (100 + 20 * 2, 200 + 20 * 2) and keys[1][0] == 3.75 and keys[-1][0] == 9.0
    img = np.zeros((400, 300, 3), np.uint8)
    img[:, 150:] = 255
    clip = motion.guided_clip(img, 9.0, motion.guide_keys((0, 0, 300, 400), 300, [(0.0, (0, 0, 40, 40)), (4.0, (260, 360, 40, 40))], 9.0))
    assert clip.get_frame(0.0).shape == img.shape and clip.get_frame(8.0).mean() > clip.get_frame(0.5).mean()  # vers la droite, blanche
    tall = np.repeat((np.arange(1000) % 256).astype(np.uint8)[:, None, None], 10, axis=1).repeat(3, axis=2)
    pan = motion.guided_pan_clip(tall, 200, 9.0, [(0.5, 150.0), (4.0, 900.0)])
    assert pan.get_frame(0.0).shape[0] == 200 and pan.get_frame(8.5)[0, 0, 0] == 800 % 256  # au bout : la seconde bulle
