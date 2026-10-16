"""Découpe en parties pour TikTok (60–90 s), avec un titre et des hashtags pour chacune.

On coupe entre deux cases, jamais au milieu d'une réplique, en préférant un moment de
suspense : une réplique qui finit par « ? », « ! » ou « … », ou juste avant une case
sans texte (un changement de scène). La meilleure suite de coupes est cherchée sur tout
le chapitre (programmation dynamique), chaque partie restant entre 60 et 90 s.
Chaque partie commence par « PART 2/5 » à l'écran. Le titre et les hashtags viennent de
GPT si la clé marche, sinon d'un modèle simple.

Fichiers : <chapitre>/parts/part-01.mp4… ; data["parts"] = [{"start", "end", "title", "hashtags"}].
"""
import json
import os
import re

PARTS_VERSION = 1
MIN, MAX, TARGET = 60.0, 90.0, 75.0


def boundaries(data):
    """[(instant, note)] : où l'on peut couper, et combien c'est un bon endroit (0 à 3)."""
    timeline = (data["steps"].get("render") or {}).get("timeline") or []
    frames = {f["file"]: f for f in data["frames"]}
    out = []
    for k in range(1, len(timeline)):
        prev = frames.get(timeline[k - 1][0]) or {}
        nxt = frames.get(timeline[k][0]) or {}
        last = ((prev.get("segments") or [{}])[-1].get("text") or "").strip()
        score = 0.0
        if re.search(r"(\?|!|\.\.\.|…)['\"”]*$", last):
            score += 2  # on s'arrête sur une question, un cri, un silence qui pèse
        if not nxt.get("segments"):
            score += 1  # la case suivante est muette : souvent une nouvelle scène
        out.append((timeline[k][1], score))
    return out, (timeline[-1][1] + timeline[-1][2] if timeline else 0.0)


def plan(data, lo=MIN, hi=MAX, target=TARGET):
    """[(début, fin)] des parties. Une vidéo de moins de `hi` secondes reste entière."""
    cuts, total = boundaries(data)
    if total <= hi:
        return [(0.0, total)] if total else []
    points = [(0.0, 0.0)] + cuts + [(total, 0.0)]
    best = {0: (0.0, None)}  # indice du point → (note, point précédent)
    for j in range(1, len(points)):
        t, s = points[j]
        cands = []
        for i, (score, _) in best.items():
            length = t - points[i][0]
            if lo <= length <= hi or (j == len(points) - 1 and length < lo and i == 0):
                cands.append((score + s - abs(length - target) / 30, i))
        if cands:
            best[j] = max(cands)
    last = len(points) - 1
    if last not in best:  # pas de découpe qui respecte 60–90 s : des morceaux de ~75 s
        out, start = [], 0.0
        for t, _ in cuts:
            if t - start >= target:
                out.append((start, t))
                start = t
        return out + [(start, total)]
    seq, j = [], last
    while j:
        i = best[j][1]
        seq.append((points[i][0], points[j][0]))
        j = i
    return list(reversed(seq))


def default_texts(chapter, k, n):
    from manhwa.cast import chapter_number

    series = chapter.root.parent.name
    number = chapter_number(chapter)
    tag = re.sub(r"[^A-Za-z0-9]", "", series)
    title = f"{series} — Episode {number or ''} (Part {k}/{n})".replace("Episode  ", "Episode ")
    return title, [f"#{tag}", "#manhwa", "#manhwarecap", "#webtoon", "#anime", "#fyp"]


def gpt_texts(chapter, data, parts):
    """Un titre accrocheur (sans spoiler de la fin) et des hashtags par partie, par GPT."""
    from manhwa.llm import chat

    texts = []
    for start, end in parts:
        said = [seg.get("text") for f, s, d in (data["steps"].get("render") or {}).get("timeline") or []
                if start <= s < end for fr in data["frames"] if fr["file"] == f for seg in fr.get("segments") or []]
        texts.append(" ".join(t for t in said if t)[:1500])
    prompt = {"task": ("Write a short catchy TikTok title (English, under 70 characters, no spoiler of the part's ending) "
                       "and 6 hashtags for each part of this manhwa recap. Answer JSON: "
                       "{\"parts\": [{\"title\", \"hashtags\": [\"#...\"]}]}"),
              "series": chapter.root.parent.name, "parts": texts}
    answer = chat([{"role": "system", "content": "You write TikTok captions. Answer only with JSON."},
                   {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}], max_tokens=2000)
    return answer.get("parts") or []


def clean_tags(tags, limit=8):
    """« # manhwaTrends », « manhwa » → « #manhwaTrends », « #manhwa » ; sans doublons."""
    out = []
    for tag in tags:
        word = re.sub(r"[^\w]", "", str(tag))
        if word and f"#{word}".lower() not in {x.lower() for x in out}:
            out.append(f"#{word}")
    return out[:limit]


def parts_dir(chapter):
    return chapter.root / "parts"


def _title_card(text, width, cfg, size=72):
    """« PART 2/5 » sur une étiquette sombre arrondie (lisible sur n'importe quel dessin)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    from manhwa.captions import font_path

    path = font_path(cfg)
    font = ImageFont.truetype(path, size) if path else ImageFont.load_default()
    left, top, right, bottom = font.getbbox(text)
    pad_x, pad_y = size // 2, size // 4
    w, h = right - left + 2 * pad_x, bottom - top + 2 * pad_y
    img = Image.new("RGBA", (width, h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0 = (width - w) // 2
    d.rounded_rectangle((x0, 4, x0 + w, 4 + h), radius=h // 2, fill=(10, 10, 14, 200))
    d.text((x0 + pad_x - left, 4 + pad_y - top), text, font=font, fill=(255, 255, 255))
    return np.array(img)


def run_parts(chapter, cfg, progress=None):
    """Coupe la vidéo du chapitre en parties (et leur donne un titre).

    ffmpeg coupe et incruste « PART 2/5 » en un seul passage (bien plus rapide que de
    décoder la vidéo image par image en Python).
    """
    import subprocess

    import imageio_ffmpeg
    from PIL import Image

    data = chapter.load()
    if not chapter.video_path.is_file() or not (data["steps"].get("render") or {}).get("timeline"):
        raise RuntimeError("Crée d'abord la vidéo")
    spans = plan(data)
    n = len(spans)
    texts = []
    try:
        texts = gpt_texts(chapter, data, spans)
    except Exception as e:  # pas de clé, ou clé expirée : un titre simple
        print(f"  Titres sans GPT ({e})")
    folder = parts_dir(chapter)
    folder.mkdir(exist_ok=True)
    for old in list(folder.glob("part-*.mp4")) + list(folder.glob("part-*.m4a")) + list(folder.glob("card-*.png")):
        old.unlink()
    width = int(cfg["output"]["width"])
    top = int(int(cfg["output"]["height"]) * 0.08)
    out = []
    for k, (a, b) in enumerate(spans, 1):
        title, tags = default_texts(chapter, k, n)
        got = texts[k - 1] if k - 1 < len(texts) and isinstance(texts[k - 1], dict) else {}
        title = str(got.get("title") or title)[:100]
        tags = clean_tags(got.get("hashtags") or tags)
        path = folder / f"part-{k:02d}.mp4"
        tmp = path.with_suffix(".part.mp4")
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}",
               "-i", str(chapter.video_path)]
        card = folder / f"card-{k:02d}.png"
        if n > 1:
            Image.fromarray(_title_card(f"PART {k}/{n}", width, cfg)).save(card)
            cmd += ["-i", str(card), "-filter_complex", f"[0:v][1:v]overlay=0:{top}:enable='lt(t,2)'"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", str(tmp)]
        subprocess.run(cmd, check=True)
        os.replace(tmp, path)
        if card.is_file():
            card.unlink()
        out.append({"file": path.name, "start": round(a, 2), "end": round(b, 2), "title": title, "hashtags": tags})
        if progress:
            progress(k, n)
    data = chapter.load()
    data["parts"] = out
    chapter.save(data)
    print(f"  {n} parties : " + ", ".join(f"{p['end'] - p['start']:.0f} s" for p in out))
    return n
