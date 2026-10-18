"""Assemblage vidéo : chaque frame dure le temps de ses répliques, avec un peu de mouvement.

    - une case plus haute que l'écran défile de haut en bas, en pleine largeur (au lieu
      d'être réduite au milieu d'un fond flou) ;
    - les autres frames zooment très légèrement (avant, arrière, en alternance) ;
    - passage d'une frame à l'autre : la nouvelle pousse l'ancienne vers le haut, comme un
      webtoon qu'on fait défiler (ou un fondu : [render] transition = "fade") ;
    - les bruitages choisis (manhwa/sfx.py) partent au début de leur case, sous la voix ;
    - l'image réagit aux coups : elle tremble, un flash sur un coup violent (manhwa/motion.py) ;
    - relief : pendant le zoom, le premier plan avance un peu plus que le fond (motion.depth_map) ;
    - le lieu (places.py) : une ambiance de fond sous chaque scène, et des voix qui résonnent comme le lieu ;
    - à la fin, tout le son est remis au niveau des vidéos en ligne ([render] loudness, en LUFS) ;
    - le rythme du dialogue (rhythm.py) : qui répond, sur quel ton ([render] natural_rhythm) ;
    - une case longue (≥ 7 s, plusieurs bulles) : la caméra va voir la bulle de chaque réplique ([render] guide) ;
    - une musique de fond (fichier dans music/ ou [render] music) tourne en boucle et
      baisse pendant que les personnages parlent.
"""
import math
import os

from manhwa.config import ROOT
from manhwa.panels import STUDIO_DIR
from manhwa.project import fingerprint

GAP_SECONDS = 0.15     # blanc entre deux répliques d'une même frame
TALL = 16 / 9 * 1.08   # une case plus haute que ça (hauteur / largeur) défile au lieu d'être réduite
MUSIC_EXT = (".mp3", ".ogg", ".wav", ".m4a")


def music_file(cfg):
    """La musique de fond : [render] music, sinon le premier fichier de music/ (à la racine)."""
    chosen = (cfg["render"].get("music") or "").strip()
    if chosen:
        path = (ROOT / chosen) if not os.path.isabs(chosen) else chosen
        return str(path) if os.path.isfile(path) else None
    folder = ROOT / "music"
    if folder.is_dir():
        tracks = sorted(p for p in folder.iterdir() if p.suffix.lower() in MUSIC_EXT)
        if tracks:
            return str(tracks[0])
    return None


def render_key(chapter, data, cfg):
    from manhwa.motion import effects
    from manhwa.sfx import video_hits, video_sounds

    sounds = video_sounds(chapter, data, cfg)
    hits = video_hits(chapter, data, cfg) if cfg["render"].get("effects", True) else {}
    parts = []
    for frame in data["frames"]:
        img = chapter.frames_dir / frame["file"]
        stat = img.stat() if img.is_file() else None
        voices = [seg.get("audio_key") for seg in frame.get("segments") or []] or frame.get("audio_key")
        parts.append([frame["file"], frame.get("crop"), stat and stat.st_size, stat and stat.st_mtime_ns, voices,
                      [[os.path.basename(s), g] for s, g in sounds.get(frame["file"], [])],
                      effects(hits.get(frame["file"], []))])
    from manhwa.places import load_places

    music = music_file(cfg)
    if cfg["render"].get("ambience", True) or cfg["render"].get("voice_space", True):
        parts.append([[s.get("from"), s.get("space"), s.get("ambience")] for s in load_places(chapter).get("scenes") or []])
    mood = None
    if cfg["render"].get("music_moods", True) and not (cfg["render"].get("music") or "").strip():
        from manhwa import moods
        from manhwa.scene import load_scene

        scene = load_scene(chapter)
        mood = ([moods.frame_mood(f, scene) for f in data["frames"]],
                {m: os.path.getsize(p) for m, p in moods.tracks().items()})
    talking = None
    if cfg["render"].get("talk"):
        from manhwa.talk import load_parts

        talking = load_parts(chapter)
    return fingerprint(parts, cfg["render"], cfg["output"], music and os.path.getsize(music), mood, talking)


def write_video(clip, path, fps, threads=1, audio_tmp=None, progress=None, loudness=None):
    """Écrit la vidéo : plusieurs images calculées en même temps (threads), envoyées dans l'ordre à ffmpeg.

    moviepy calcule les images une à une sur un seul cœur ; ici les calculs (OpenCV, numpy) de
    plusieurs images avancent ensemble. Pendant ce temps, le son s'écrit à part et prend son
    niveau final (loudness, LUFS) ; il est joint à la fin sans rien réencoder.
    """
    import subprocess
    import threading
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor

    import cv2
    import imageio_ffmpeg
    import numpy as np

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    sound, failed = {}, []

    def write_sound():  # en même temps que les images
        try:
            raw = str(audio_tmp) + ".raw.m4a"
            clip.audio.write_audiofile(raw, fps=44100, codec="aac", logger=None)
            if loudness:
                try:
                    subprocess.run([ffmpeg, "-v", "quiet", "-y", "-i", raw, "-af", f"loudnorm=I={loudness}:TP=-1.5:LRA=11",
                                    "-ar", "44100", "-c:a", "aac", "-b:a", "192k", str(audio_tmp)], check=True)
                    os.remove(raw)
                except Exception as e:  # le son d'avant reste
                    print(f"  [!] Niveau sonore non réglé ({e})")
                    os.replace(raw, audio_tmp)
            else:
                os.replace(raw, audio_tmp)
            sound["path"] = str(audio_tmp)
        except Exception as e:
            failed.append(e)

    worker = None
    if clip.audio is not None and audio_tmp:
        worker = threading.Thread(target=write_sound, daemon=True)
        worker.start()
    n = max(1, int(clip.duration * fps + 1e-6))
    w, h = clip.size
    silent = str(path) + ".video.mp4"
    out = imageio_ffmpeg.write_frames(silent, (w, h), fps=fps, codec="libx264", quality=None, macro_block_size=1,
                                      ffmpeg_log_level="error", output_params=["-preset", "ultrafast", "-crf", "23"])
    out.send(None)
    shot = lambda k: np.ascontiguousarray(clip.get_frame(k / fps), dtype=np.uint8)
    cv_threads = cv2.getNumThreads()
    if threads > 1:  # chaque image sur un cœur : mesuré 127 images/s à 8 contre 70 avec OpenCV seul sur 12 cœurs
        cv2.setNumThreads(1)
    try:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            ahead = deque()
            for k in range(n):
                ahead.append(pool.submit(shot, k))
                if len(ahead) >= 2 * threads:
                    out.send(ahead.popleft().result())
                    if progress and k % 24 == 0:
                        progress(k - len(ahead), n)
            while ahead:
                out.send(ahead.popleft().result())
    finally:
        cv2.setNumThreads(cv_threads)
        out.close()
    if worker:
        worker.join()
        if failed:
            raise failed[0]
    if sound:
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", silent, "-i", sound["path"], "-map", "0:v", "-map", "1:a",
                        "-c", "copy", "-shortest", str(path)], check=True)
        os.remove(silent)
        os.remove(sound["path"])
    else:
        os.replace(silent, path)
    if progress:
        progress(n, n)


def _load_audio(path):
    from moviepy import AudioFileClip

    if not os.path.isfile(path) or os.path.getsize(path) <= 100:
        return None
    try:
        return AudioFileClip(str(path))
    except Exception:
        print(f"  [!] Audio illisible ignoré : {os.path.basename(path)}")
        return None


def _silence(duration, like):
    """Un blanc du même format que `like` (les mp3 d'edge-tts sont lus en stéréo)."""
    import numpy as np
    from moviepy import AudioClip

    channels = getattr(like, "nchannels", 1) or 1

    def frame(t):
        n = len(t) if hasattr(t, "__len__") else 1
        out = np.zeros((n, channels))
        return out if hasattr(t, "__len__") else out[0]

    return AudioClip(frame, duration=duration, fps=like.fps)


# ---------- Mouvement ----------

def _ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def zoom_clip(image, duration, amount, zoom_in=True, anim=None):
    """La frame qui grossit (ou rapetisse) de `amount` (0.04 = 4 %) sur sa durée (anim(t) : l'image qui bouge)."""
    import cv2
    from moviepy import VideoClip

    h, w = image.shape[:2]

    def frame(t):
        p = _ease(t / duration) if duration else 0
        s = 1 + amount * (p if zoom_in else 1 - p)
        ch, cw = round(h / s), round(w / s)
        y0, x0 = (h - ch) // 2, (w - cw) // 2
        src = anim(t) if anim else image
        return cv2.resize(src[y0:y0 + ch, x0:x0 + cw], (w, h), interpolation=cv2.INTER_LINEAR)

    return VideoClip(frame, duration=duration)


def pan_clip(tall, out_h, duration, anim=None):
    """Une case haute, en pleine largeur, qui défile du haut vers le bas (pause au début et à la fin)."""
    from moviepy import VideoClip

    travel = tall.shape[0] - out_h

    def frame(t):
        p = _ease((t / duration - 0.12) / 0.76) if duration else 0
        y = round(travel * p)
        return (anim(t) if anim else tall)[y:y + out_h]

    return VideoClip(frame, duration=duration)


def timeline(clips, durations, kind="slide", seconds=0.3):
    """Les frames bout à bout, avec une transition au début de chacune (sans allonger la vidéo).

    On ne passe pas par concatenate_videoclips : chaque image se calcule à la demande,
    la transition mélange la dernière image de la frame d'avant et le début de la suivante.
    """
    import bisect

    import numpy as np
    from moviepy import VideoClip

    starts = [0.0]
    for d in durations[:-1]:
        starts.append(starts[-1] + d)
    total = starts[-1] + durations[-1]
    last = {}

    def end_of(i):
        if i not in last:
            last[i] = clips[i].get_frame(max(0.0, durations[i] - 1e-3))
        return last[i]

    def frame(t):
        i = min(len(clips) - 1, max(0, bisect.bisect_right(starts, t) - 1))
        local = t - starts[i]
        cur = clips[i].get_frame(min(local, durations[i] - 1e-3))
        span = min(seconds, 0.4 * durations[i])
        if kind == "none" or i == 0 or local >= span:
            return cur
        p = _ease(local / span)
        prev = end_of(i - 1)
        if kind == "fade":
            return (prev * (1 - p) + cur * p).astype(np.uint8)
        cut = round(p * cur.shape[0])  # « slide » : l'ancienne monte, la nouvelle arrive par le bas
        return np.vstack([prev[cut:], cur[:cut]]) if cut else prev

    return VideoClip(frame, duration=total), starts


def _scroll(chapter, strip, reading, durations, out_w, out_h, r, face_parts, faces_of, places=None):
    """La planche entière qui défile de case en case (scroll.py), avec le relief et les visages qui parlent."""
    import cv2

    from manhwa import motion, scroll

    k = out_w / strip.shape[1]
    big = cv2.cvtColor(cv2.resize(strip, (out_w, round(strip.shape[0] * k)), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    starts, panels, t = [], [], 0.0
    for (frame, i, duration, times, lines, fx), d in zip(reading, durations):
        p = scroll.Panel(frame["crop"], k, t, d, fx=fx)
        p.bubbles = [(s, p.y + (b[1] + b[3] / 2) * k) for s, b in times]
        sides = [(p.x + b["box"][0] * k, p.x + (b["box"][0] + b["box"][2]) * k) for b in frame.get("bubbles") or [] if b.get("box")]
        p.span = (max(0, min([p.x] + [a for a, _ in sides])), min(out_w, max([p.x + p.w] + [b for _, b in sides])))
        image = big[p.y:p.y + p.h, p.x:p.x + p.w]
        if r.get("depth", True) and float(r.get("zoom", 0.04)) > 0 and p.h >= 16 and p.w >= 16:
            try:
                boxes = [b["box"] for b in frame.get("bubbles") or []]  # les bulles bougent d'un bloc
                p.depth = motion.cached_depth(chapter.root / STUDIO_DIR / "depth", image, frame["crop"], boxes)
            except Exception as e:
                print(f"  [!] Relief indisponible ({e})")
        if lines and faces_of and frame["file"] in faces_of:
            from manhwa import talk

            try:
                p.anim = talk.animator(chapter, image, k, (0, 0), faces_of[frame["file"]], face_parts, lines, seed=i)
            except Exception as e:
                print(f"  [!] Visage qui parle ignoré ({frame['file']} : {e})")
        panels.append(p)
        starts.append(t)
        t += d
    if r.get("smart_transitions", True):  # coupe nette sur un coup, fondu vers un autre lieu
        for p, how in zip(panels, scroll.enter_rules([p.fx for p in panels], places or [None] * len(panels))):
            p.enter = how
    return scroll.scroll_clip(big, panels, out_w, out_h, t, fit=bool(r.get("scroll_fit", True))), starts


def _tall_image(strip, crop, out_w):
    """La case découpée dans le chapitre, mise à la largeur de la vidéo (None si elle n'est pas haute)."""
    import cv2

    x, y, w, h = crop
    if strip is None or w <= 0 or h / w <= TALL:
        return None
    part = strip[y:y + h, x:x + w]
    new_h = round(h * out_w / w)
    return cv2.cvtColor(cv2.resize(part, (out_w, new_h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)


# ---------- Son ----------

def _duck(track, durations, voiced, r):
    """Plus fort sur les cases sans voix, plus bas sous les voix."""
    import numpy as np

    ends = np.cumsum(durations)
    loud = float(r.get("music_volume", 0.16))
    quiet = loud * float(r.get("music_duck", 0.4))
    levels = np.array([quiet if v else loud for v in voiced])

    def envelope(t):
        k = np.minimum(np.searchsorted(ends, t, side="right"), len(levels) - 1)
        return levels[k]

    def duck(get_frame, t):
        out = get_frame(t)
        env = envelope(np.atleast_1d(t))
        return out * (env[:, None] if np.ndim(out) == 2 else env[0])

    return track.transform(duck, keep_duration=True)


def _music_track(path, durations, voiced, r):
    """La musique en boucle, plus forte sur les cases sans voix, plus basse sous les voix."""
    from moviepy.audio.fx import AudioFadeIn, AudioFadeOut, AudioLoop

    music = _load_audio(path)
    if music is None:
        return None
    track = _duck(music.with_effects([AudioLoop(duration=sum(durations))]), durations, voiced, r)
    return track.with_effects([AudioFadeIn(1.5), AudioFadeOut(2.5)])


def _mood_track(secs, paths, durations, voiced, r, opened, fade=1.5):
    """Une musique par ambiance (moods.py), fondu enchaîné d'une ambiance à l'autre."""
    from moviepy import CompositeAudioClip
    from moviepy.audio.fx import AudioFadeIn, AudioFadeOut, AudioLoop

    total = sum(durations)
    layers = []
    for mood, a, b in secs:
        src = _load_audio(paths[mood])
        if src is None:
            continue
        opened.append(src)
        start, end = max(0.0, a - fade / 2), min(total, b + fade / 2)
        layers.append(src.with_effects([AudioLoop(duration=end - start), AudioFadeIn(fade), AudioFadeOut(fade)])
                      .with_start(start))
    if not layers:
        return None
    return _duck(CompositeAudioClip(layers).with_duration(total), durations, voiced, r)


def run_render(chapter, cfg, force=False, progress=None):
    data = chapter.load()
    if not data["frames"]:
        print("  Aucune frame à assembler.")
        return False

    key = render_key(chapter, data, cfg)
    talking = None
    if cfg["render"].get("talk"):
        from manhwa import talk as talking

        face_parts = talking.load_parts(chapter)
        faces_of = {}
        for f in (data.get("faces") or {}).get("list") or []:
            if f["id"] in face_parts and not f.get("not_face"):
                faces_of.setdefault(f["frame"], []).append(f)
    if not force and chapter.video_path.is_file() and data["steps"].get("render", {}).get("key") == key:
        print(f"  Vidéo déjà à jour : {chapter.video_path.name}")
        return False

    import cv2
    from moviepy import CompositeAudioClip

    from manhwa.images import load_strip, read_image
    from manhwa.sfx import VOLUME, ensure_library, video_sounds

    r = cfg["render"]
    out_w, out_h = cfg["output"]["width"], cfg["output"]["height"]
    speed = float(r.get("speed", 1.0))  # la voix est déjà accélérée (tts) : on raccourcit les blancs
    zoom = float(r.get("zoom", 0.04))
    pan = bool(r.get("pan", True))
    from manhwa import motion
    from manhwa.sfx import video_hits

    sounds, reacts = {}, {}
    try:
        ensure_library()
        sounds = video_sounds(chapter, data, cfg)
        reacts = video_hits(chapter, data, cfg) if r.get("effects", True) else {}
    except Exception as e:
        print(f"  [!] Bruitages indisponibles ({e}) : vidéo sans bruitages")
    scrolling = r.get("layout", "cases") == "scroll"  # la planche qui défile (scroll.py) au lieu d'une case par image
    strip = None
    if scrolling or (pan and any(f["crop"][3] / max(1, f["crop"][2]) > TALL for f in data["frames"])):
        strip, _ = load_strip(chapter.pages(), cfg["slicer"]["max_src_width"])
    reading = []  # défilement : ce qu'il faut savoir de chaque case

    from manhwa import places as places_mod
    from manhwa import rhythm

    natural = bool(r.get("natural_rhythm", True))

    where = places_mod.frame_places(chapter, data)
    clips, audios, opened, durations, voiced, files, spoken = [], [], [], [], [], [], []
    for i, frame in enumerate(data["frames"]):
        img_path = chapter.frames_dir / frame["file"]
        image = read_image(img_path)
        if image is None:
            print(f"  [!] Frame manquante ignorée : {frame['file']}")
            continue
        # les répliques de la frame l'une après l'autre (une voix par personnage), un court blanc entre deux
        space = (where[i] or {}).get("space") if r.get("voice_space", True) else None

        def voice_file(seg):
            path = chapter.root / seg["audio"]
            if space and path.is_file():
                try:
                    return places_mod.voice_in_space(chapter, path, space)  # chaleur et résonance du lieu
                except Exception:
                    pass
            return path

        loaded = [(seg, _load_audio(voice_file(seg))) for seg in frame.get("segments") or []]
        loaded = [(seg, a) for seg, a in loaded if a]
        pieces = [a for _, a in loaded]
        t_in, said, starts_in = 0.0, [], []  # où commence chaque réplique dans la frame (sous-titres)
        for k, (seg, a) in enumerate(loaded):
            if k:  # le rythme du dialogue (rhythm.py) : qui répond, sur quel ton
                t_in = max(starts_in[-1] + 0.3 * loaded[k - 1][1].duration,
                           t_in + (rhythm.gap(loaded[k - 1][0], seg) if natural else GAP_SECONDS) / speed)
            starts_in.append(t_in)
            said.append((seg.get("text") or "", t_in, a.duration, seg.get("words")))
            t_in += a.duration
        if not pieces and frame.get("audio"):  # frame d'avant les voix par personnage
            pieces = [a for a in [_load_audio(chapter.root / frame["audio"])] if a]
            starts_in = [0.0]
        opened += pieces
        voice = None
        if pieces:
            end = max(t + a.duration for t, a in zip(starts_in, pieces))
            voice = (CompositeAudioClip([a.with_start(t) for t, a in zip(starts_in, pieces)]).with_duration(end)
                     if len(pieces) > 1 else pieces[0])
        following = next(iter((data["frames"][i + 1].get("segments") or [None]) if i + 1 < len(data["frames"]) else [None]))
        pad = rhythm.tail(loaded[-1][0], following) if natural and loaded else r["padding_seconds"]
        duration = voice.duration + pad / speed if voice else r["silent_frame_seconds"] / speed

        hits = [(a, g) for a, g in ((_load_audio(p), g) for p, g in sounds.get(frame["file"], [])) if a]
        opened += [a for a, _ in hits]
        if hits and not voice:
            duration = max(duration, min(3.0, max(h.duration for h, _ in hits) + 0.2))
        layers = ([voice] if voice else []) + [h.with_start(0.05 + 0.25 * k).with_volume_scaled(VOLUME * g)
                                               for k, (h, g) in enumerate(hits)]
        audio = CompositeAudioClip(layers).with_duration(duration) if layers else None

        tall = _tall_image(strip, frame["crop"], out_w) if pan else None
        lines = []
        if talking and frame["file"] in faces_of:  # la bouche de celui qui parle suit sa voix (talk.py)
            lines = [(seg.get("speaker"), t, talking.envelope(a, a.duration)) for (seg, a), t in zip(loaded, starts_in)]

        def talker(img, scale, offset):
            if not lines:
                return None
            try:
                return talking.animator(chapter, img, scale, offset, faces_of[frame["file"]], face_parts, lines, seed=i)
            except Exception as e:  # un dessin abîmé : la case reste immobile, la vidéo se fait quand même
                print(f"  [!] Visage qui parle ignoré ({frame['file']} : {e})")
                return None
        def bubble_times():
            from manhwa.review import effective

            where_box = {b["text"]: b["box"] for b in effective(frame) if b.get("box")}
            return [(start, where_box[text]) for text, start, _, _ in said if text in where_box]

        guided = duration >= motion.LONG_CASE and len(said) >= 2 and r.get("guide", True)
        if scrolling:  # la vidéo se fait d'un bloc après la boucle (scroll.scroll_clip)
            reading.append((frame, i, duration, bubble_times(), lines, motion.effects(reacts.get(frame["file"], []))))
            clip = None
        elif tall is not None and tall.shape[0] > out_h:
            times = bubble_times() if guided else []
            if len(times) >= 2:  # case haute et longue : elle défile jusqu'à la bulle de chaque réplique
                f = tall.shape[1] / frame["crop"][2]
                clip = motion.guided_pan_clip(tall, out_h, duration, [(max(0.0, s - 0.3), (b[1] + b[3] / 2) * f) for s, b in times],
                                              anim=talker(tall, f, (0, 0)))
            else:
                clip = pan_clip(tall, out_h, duration, anim=talker(tall, tall.shape[1] / frame["crop"][2], (0, 0)))
        else:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            depth = None
            if zoom > 0 and r.get("depth", True):
                try:
                    boxes = [b["box"] for b in frame.get("bubbles") or []]  # les bulles bougent d'un bloc
                    depth = motion.cached_depth(chapter.root / STUDIO_DIR / "depth", rgb, frame["crop"], boxes)
                except Exception as e:  # sans le modèle : le zoom simple
                    print(f"  [!] Relief indisponible ({e})")
                    r = {**r, "depth": False}
            guide = []
            if guided:  # case longue : la caméra va voir la bulle de chaque réplique (motion.guided_clip)
                times = bubble_times()
                if len(times) >= 2:
                    guide = motion.guide_keys(motion.panel_rect(rgb, frame["crop"][2:4]), frame["crop"][2], times, duration)
            rect = motion.panel_rect(rgb, frame["crop"][2:4])
            anim = talker(rgb, rect[2] / frame["crop"][2], rect[:2])
            if guide:
                clip = motion.guided_clip(rgb, duration, guide, anim=anim)
            elif depth is not None:
                clip = motion.depth_zoom_clip(rgb, depth, duration, zoom, zoom_in=i % 2 == 0, anim=anim)
            else:
                clip = zoom_clip(rgb, duration, max(zoom, 0), zoom_in=i % 2 == 0, anim=anim)
        if clip is not None:
            clip = motion.apply(clip, motion.effects(reacts.get(frame["file"], [])))  # tremblement, flash sur les coups
        clips.append(clip)
        audios.append(audio)
        durations.append(duration)
        voiced.append(bool(voice))
        files.append(frame["file"])
        spoken.append(said)

    if not clips:
        print("  Rien à assembler.")
        return False

    tmp = chapter.root / "video.part.mp4"
    print(f"  Rendu de {len(clips)} frames ({sum(durations) / 60:.1f} min)...")
    try:
        if scrolling:
            kept = {f for f in files}
            final, starts = _scroll(chapter, strip, reading, durations, out_w, out_h, r, talking and face_parts, talking and faces_of,
                                    [w for w, f in zip(where, data["frames"]) if f["file"] in kept])
        else:
            final, starts = timeline(clips, durations, r.get("transition", "slide"), float(r.get("transition_seconds", 0.3)))
        path = music_file(cfg)
        music = None
        if r.get("music_moods", True) and not (r.get("music") or "").strip():
            from manhwa import moods

            music = _mood_track(moods.plan(chapter, data, durations, files), moods.tracks(), durations, voiced, r, opened)
        elif path:
            music = _music_track(path, durations, voiced, r)
        if music is not None:
            opened.append(music)
        ambience = None
        if r.get("ambience", True):
            from manhwa.soundbank import ambience_file

            secs = places_mod.sections([w for w, f in zip(where, data["frames"]) if f["file"] in set(files)], durations)
            paths = {a: str(ambience_file(a)) for a, _, _ in secs if ambience_file(a)}
            secs = [s for s in secs if s[0] in paths]
            if secs:
                amb_r = {**r, "music_volume": float(r.get("ambience_volume", 0.13)), "music_duck": 0.6}
                ambience = _mood_track(secs, paths, durations, voiced, amb_r, opened, fade=2.0)
        layers = ([a.with_start(t) for a, t in zip(audios, starts) if a is not None] + ([music] if music is not None else [])
                  + ([ambience] if ambience is not None else []))
        if r.get("captions", True):
            from manhwa.captions import burn, events

            lines = [(text, start + t, d, words) for said, start in zip(spoken, starts) for text, t, d, words in said]
            evts = events(lines, int(r.get("captions_words", 4)))
            if evts:
                final = burn(final, evts, cfg, int(out_h * 0.7))
        if layers:
            final = final.with_audio(CompositeAudioClip(layers).with_duration(final.duration))
        # le son temporaire dans le dossier du chapitre : deux rendus en même temps ne se gênent pas
        threads = int(r.get("threads", 0)) or max(1, min(8, (os.cpu_count() or 2) - 2))
        write_video(final, tmp, r["fps"], threads, chapter.root / "video.part.audio.m4a", progress,
                    loudness=float(r["loudness"]) if r.get("loudness") else None)
        final.close()
    finally:
        for c in clips + opened:
            try:
                c.close()
            except Exception:
                pass
    os.replace(tmp, chapter.video_path)

    data = chapter.load()  # relu : on a pu valider des choses dans le Studio pendant le rendu
    # où commence chaque frame dans la vidéo (onglet Vidéo : signaler un passage)
    data["steps"]["render"] = {"key": key, "timeline": [[f, round(t, 3), round(d, 3)] for f, t, d in zip(files, starts, durations)]}
    chapter.save(data)
    print(f"  Vidéo : {chapter.video_path}")
    return True
