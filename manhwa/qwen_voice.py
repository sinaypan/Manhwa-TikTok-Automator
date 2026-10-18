"""Des voix humaines qui jouent l'émotion : Qwen3-TTS (Apache 2.0), puis le timbre fixe du personnage.

Qwen3-TTS fabrique une voix d'après une description (« middle-aged merchant, slightly nasal,
theatrical ») et la joue avec l'émotion de la réplique (« shouting furiously »). Seul, il change
un peu de voix d'une réplique à l'autre : chaque réplique passe donc ensuite par le convertisseur
de voix de Chatterbox (MIT), qui lui remet le timbre du personnage en gardant le jeu.

    1. GPT décrit la voix de chaque personnage, en anglais, d'après sa fiche (une fois, gardé
       dans characters.json, « designs »).
    2. Qwen enregistre une phrase neutre avec cette voix : la référence du personnage
       (<série>/voices/, gardée pour toute la série).
    3. Chaque réplique : Qwen avec l'émotion, puis conversion vers la référence, puis vitesse et volume.
    4. Whisper réécoute : une réplique mal dite est refaite (deux fois au plus), puis dite par la
       voix de secours (Chatterbox, sinon la voix de base).

Mesuré sur l'extrait de l'épisode 1 : ressemblance entre deux répliques d'un même personnage
0,77 (0,62 sans la conversion), ≈ 6 s par réplique sur une RTX 3050, 4,8 Go de carte graphique.

Installation (≈ 7 Go, une fois) :
    uv venv --python 3.12 .venv-qwen
    uv pip install --python .venv-qwen/Scripts/python.exe torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
    uv pip install --python .venv-qwen/Scripts/python.exe qwen-tts
Réglé dans config.toml : [tts] engine = "qwen".
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import zlib

from manhwa.config import ROOT

REF_TEXT = ("I have walked this road for a long time, and I am not done yet. "
            "Every step brings me closer to the truth, whatever it costs me.")
# l'émotion de la réplique, dite à Qwen
EMOTION = {"neutral": "natural conversational tone", "calm": "calm and composed", "happy": "warm and happy",
           "excited": "excited and energetic", "mocking": "mocking, with a sneer", "angry": "angry, through gritted teeth",
           "shouting": "shouting furiously at the top of his lungs", "cold": "cold and menacing, very controlled",
           "sad": "sad and quiet, close to tears", "scared": "scared and trembling", "surprised": "startled and surprised",
           "pain": "in pain, gasping", "whisper": "whispering", "thinking": "thoughtful inner voice, quiet"}
DEFAULT_DESIGNS = {"narrator": "Deep warm male narrator, cinematic storytelling, calm and immersive, natural and human",
                   "extra_m": "Ordinary adult man, natural everyday voice, human",
                   "extra_f": "Ordinary adult woman, natural everyday voice, human"}
# sans GPT : des voix bien différentes, dans l'ordre (redemandées à GPT dès que la clé est là)
FALLBACK = {
    "m": ["Man in his thirties, low and calm voice, slightly raspy", "Young man in his twenties, bright and lively voice",
          "Middle-aged man, nasal and theatrical voice", "Old man, deep, slow and gravelly voice",
          "Man in his forties, gruff and loud voice", "Soft-spoken young man, gentle and clear voice",
          "Big man, booming bass voice", "Wiry man, sharp and fast voice"],
    "f": ["Young woman, clear and confident voice", "Woman in her thirties, warm and low voice",
          "Teenage girl, bright and quick voice", "Older woman, calm and dignified voice",
          "Woman, cold and sharp voice", "Soft-spoken young woman, gentle voice"],
}
# répliques dites ensemble par Qwen. Mesuré sur 28 répliques (RTX 3050) : 4 → 88 s, 5 → 64 s, 6 → 53 s,
# 7 → 43 s (5,4 Go) ; au-delà, pas mieux et la carte approche de ses 6 Go. Un paquet garde moins de
# BATCH_CHARS lettres : les longues narrations vont par plus petits paquets.
BATCH = 7
BATCH_CHARS = 600


def groups(segs):
    """Les répliques en paquets, de longueur voisine (une courte n'attend pas une longue)."""
    out, cur = [], []
    for s in sorted(segs, key=lambda s: len(s["text"])):
        if cur and (len(cur) >= BATCH or sum(len(x["text"]) for x in cur) + len(s["text"]) > BATCH_CHARS):
            out.append(cur)
            cur = []
        cur.append(s)
    return out + ([cur] if cur else [])
_WORKERS = {}
_BUSY = threading.Lock()  # un seul usage à la fois (création de la vidéo, ou extrait dans le Studio)


class Busy(RuntimeError):
    pass


def python():
    exe = ROOT / ".venv-qwen" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return exe if exe.is_file() else None


def available():
    from manhwa import chatterbox_tts

    return python() is not None and chatterbox_tts.available()


def sentence_case(text):
    """« YOU PARASITE! » → « You parasite! » : en majuscules, la voix croit lire des sigles."""
    if not text.isupper():
        return text
    t = re.sub(r"(^|[.!?…]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text.lower())
    return re.sub(r"\bi\b", "I", t)


# ---------- Les deux programmes (Qwen dans .venv-qwen, la conversion dans .venv-tts) ----------

def _start(name):
    from manhwa import chatterbox_tts

    w = _WORKERS.get(name)
    if w and w.poll() is None:
        return w
    close()  # un seul gros modèle à la fois sur la carte graphique
    chatterbox_tts.close()
    here = os.path.dirname(os.path.abspath(__file__))
    cmd = ([str(python()), "-u", os.path.join(here, "qwen_worker.py")] if name == "qwen"
           else [str(chatterbox_tts.python()), "-u", os.path.join(here, "chatterbox_worker.py"), "--vc"])
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                         encoding="utf-8", cwd=str(ROOT))
    if not chatterbox_tts._answer(p).get("ready"):
        p.kill()
        raise RuntimeError(f"{'Qwen3-TTS' if name == 'qwen' else 'Le convertisseur de voix'} n'a pas démarré")
    _WORKERS[name] = p
    return p


def _ask(name, job):
    from manhwa.chatterbox_tts import _answer

    p = _start(name)
    p.stdin.write(json.dumps(job) + "\n")
    p.stdin.flush()
    answer = _answer(p)
    if "error" in answer:
        raise RuntimeError(answer["error"])


def close():
    for name in list(_WORKERS):
        p = _WORKERS.pop(name)
        if p.poll() is None:
            try:
                p.stdin.close()
                p.wait(timeout=20)
            except Exception:
                p.kill()


# ---------- La voix de chaque personnage ----------

def ensure_designs(chapter, crew, avoid=None):
    """GPT décrit (en anglais) la voix des personnages qui n'en ont pas encore. Renvoie True si changé.

    avoid : {id: ancienne description} : une autre voix est demandée (« Autre voix » dans le Studio).
    """
    from manhwa.cast import EXTRAS, NARRATOR, lines, series_dir
    from manhwa.ingest.wiki import load_wiki

    designs = crew.setdefault("designs", {})
    auto = crew.setdefault("designs_auto", [])  # décrites sans GPT : redemandées dès que possible
    changed = False
    for key, text in DEFAULT_DESIGNS.items():
        who = NARRATOR if key == "narrator" else key
        if who not in designs and (key == "narrator" or key in EXTRAS):
            designs[who] = text
            changed = True
    todo = [c for c in crew["characters"] if (c["id"] not in designs or c["id"] in auto) and not c.get("silent")]
    if not todo:
        return changed
    pages = {w["id"]: w for w in (load_wiki(series_dir(chapter)) or {}).get("characters", [])}
    said = {}
    for line in lines(chapter.load(), crew):
        said.setdefault(line["speaker"] or line["suggestion"], []).append(line["text"])
    people = []
    for c in todo:
        page = pages.get(c.get("wiki")) or {}
        people.append({"id": c["id"], "name": c.get("name") or None, "gender": page.get("gender") or None,
                       "personality": (page.get("personality") or "")[:400] or None,
                       "appearance": (page.get("appearance") or "")[:200] or None,
                       "current_voice_note": (c.get("voice") or {}).get("reason") or None, "lines": said.get(c["id"], [])[:5],
                       "must_differ_from": (avoid or {}).get(c["id"])})
    try:
        from manhwa.llm import chat

        answer = chat([{"role": "system", "content": "You are a voice casting director. Answer only with JSON."},
                       {"role": "user", "content": json.dumps({
                           "task": ("Describe the speaking voice of each character of this Korean manhwa, for a voice "
                                    "actor, in English, under 25 words: gender, age, timbre (deep, raspy, nasal, bright…), "
                                    "personality in the voice, and end with 'natural and human'. Two characters must not "
                                    "sound alike. Answer JSON: {\"voices\": [{\"id\", \"voice\"}]}"),
                           "characters": people}, ensure_ascii=False)}], max_tokens=3000)
        got = {x.get("id"): str(x.get("voice") or "")[:240] for x in answer.get("voices", []) if isinstance(x, dict)}
    except Exception as e:  # sans GPT : des voix différentes, d'après le genre
        print(f"  [!] Voix décrites sans GPT ({e}) : redemandées à la prochaine création")
        got = {}
    for c in todo:
        if got.get(c["id"]):
            designs[c["id"]] = got[c["id"]]
            if c["id"] in auto:
                auto.remove(c["id"])
        elif c["id"] not in designs:
            page = pages.get(c.get("wiki")) or {}
            female = ((page.get("gender") or "").lower().startswith("f")
                      or (c.get("voice") or {}).get("name", "") in {v["name"] for v in _female_voices()})
            pool = FALLBACK["f" if female else "m"]
            used = set(designs.values())
            pick = next((d for d in pool if f"{d}, natural and human" not in used), pool[len(designs) % len(pool)])
            designs[c["id"]] = f"{pick}, natural and human"
            auto.append(c["id"])
    return True


def _female_voices():
    try:
        from manhwa.voices import list_voices

        return [v for v in list_voices() if v.get("gender") == "Female"]
    except Exception:
        return []


def voices_dir(chapter):
    from manhwa.cast import series_dir

    return series_dir(chapter) / "voices"


def reference(chapter, design):
    """La voix du personnage : une phrase neutre enregistrée par Qwen (une fois pour la série)."""
    path = voices_dir(chapter) / f"{hashlib.sha1(design.encode('utf-8')).hexdigest()[:12]}.wav"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        _ask("qwen", {"text": REF_TEXT, "instruct": f"{design}. Calm, natural conversational tone",
                      "out": str(path), "seed": zlib.crc32(design.encode("utf-8"))})
    return path


# ---------- Les répliques ----------

def _finish(raw, path, params):
    """Vitesse et volume de la réplique (comme les autres voix), en MP3."""
    import imageio_ffmpeg

    from manhwa.chatterbox_tts import _number

    speed = max(0.5, min(2.0, 1 + _number(params.get("rate")) / 100))
    gain = 1 + _number(params.get("volume")) / 100
    tmp = path.with_suffix(".part.mp3")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "quiet", "-y", "-i", str(raw), "-filter:a",
                    f"atempo={speed:.3f},volume={gain:.3f}", "-codec:a", "libmp3lame", "-b:a", "128k", str(tmp)], check=True)
    os.replace(tmp, path)


def _wrong(chapter, data, segs):
    """Les répliques que Whisper n'entend pas comme écrites (plus strict sur les très courtes)."""
    import difflib

    from manhwa.listen import FLAG, flagged, pcm, transcribe, words
    from manhwa.textfix import protected_words

    names = protected_words(chapter, [b["text"] for f in data["frames"] for b in f.get("bubbles") or []])
    heard = transcribe([pcm(chapter.root / s["audio"]) for s in segs])
    out = []
    for s, h in zip(segs, heard):
        if len(words(s["text"])) > 2:
            bad = flagged({"text": s["text"], "heard": h}, names)
        else:
            a = [w.replace("'", "") for w in words(s["text"]) if w not in names]
            b = [w.replace("'", "") for w in words(h)]
            same = sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
            bad = bool(a) and 1 - same / len(a) >= FLAG
        if bad:
            out.append(s)
    return out


CODEC_HZ = 12  # Qwen3-TTS-12Hz : 12 éléments par seconde de voix


def max_tokens(segs):
    """La plus longue voix permise pour un paquet : 6 caractères par seconde au plus lent, + 3 s.

    Sans limite (8 192, ≈ 11 min), une réplique qui déraille fait attendre tout le paquet ; coupée
    trop tôt, la réécoute (Whisper) la trouve fausse et la refait.
    """
    return int(CODEC_HZ * (3 + max(len(s["text"]) for s in segs) / 6))


def render_lines(chapter, data, segs, progress=None, tries=2):
    """Fait dire les répliques (segments prévus par tts.plan, engine « qwen »)."""
    if not segs:
        return
    with _BUSY:
        _render_lines(chapter, data, segs, progress, tries)


def _render_lines(chapter, data, segs, progress, tries):
    done = [0]
    total = len(segs)

    def make(batch, attempt):
        with tempfile.TemporaryDirectory() as tmp:
            refs = {d: reference(chapter, d) for d in {s["design"] for s in batch}}
            raws = {}
            # 1. Qwen, avec l'émotion, par paquets de répliques de longueur voisine (un seul modèle chargé à la fois)
            made = 0
            for group in groups(batch):
                if attempt == 0 and progress:
                    progress(made, 2 * total)  # la barre avance dès Qwen (la conversion fait la seconde moitié)
                made += len(group)
                jobs = [{"text": sentence_case(s["text"]), "out": os.path.join(tmp, f"{s['audio_key']}.wav"),
                         "instruct": f"{s['design']}. {EMOTION.get(s.get('emotion') or 'neutral', '')}"} for s in group]
                seed = zlib.crc32(f"{'|'.join(s['audio_key'] for s in group)}:{attempt}".encode())
                try:
                    _ask("qwen", {"batch": jobs, "seed": seed, "max_tokens": max_tokens(group)})
                    raws.update({s["audio_key"]: j["out"] for s, j in zip(group, jobs)})
                except Exception as e:  # le paquet raté : une à une
                    print(f"  [!] Qwen ({e}) : réplique par réplique")
                    for s, j in zip(group, jobs):
                        try:
                            _ask("qwen", {**j, "seed": seed, "max_tokens": max_tokens([s])})
                            raws[s["audio_key"]] = j["out"]
                        except Exception as e2:
                            print(f"  [!] Qwen : {e2} : {s['text'][:40]}")
            for s in batch:  # 2. le timbre du personnage, 3. vitesse et volume
                raw = raws.get(s["audio_key"])
                if not raw:
                    continue
                fixed = raw + ".vc.wav"
                try:
                    _ask("vc", {"vc": raw, "target": str(refs[s["design"]]), "out": fixed})
                except Exception as e:
                    print(f"  [!] Conversion : {e}")
                    fixed = raw
                _finish(fixed, chapter.root / s["audio"], s)
                if attempt == 0:
                    done[0] += 1
                    print(f"  [OK] qwen {s.get('emotion')} | {s['text'][:50]}")
                    if progress:
                        progress(total + done[0], 2 * total)
        close()

    try:
        make(segs, 0)
        bad = [s for s in segs if (chapter.root / s["audio"]).is_file()]
        bad = _wrong(chapter, data, bad) + [s for s in segs if not (chapter.root / s["audio"]).is_file()]
        for attempt in range(1, tries + 1):
            if not bad:
                break
            print(f"  Réécoute : {len(bad)} réplique(s) mal dite(s), essai {attempt + 1}")
            make(bad, attempt)
            bad = _wrong(chapter, data, bad)
    finally:
        close()
    for s in bad:  # toujours fausse : la voix de secours, juste
        _fallback(chapter, s)


def _fallback(chapter, s):
    import asyncio

    from manhwa import chatterbox_tts
    from manhwa.voices import synthesize

    params = {k: s[k] for k in ("voice", "rate", "pitch", "volume") if k in s}
    try:
        asyncio.run(synthesize(s["text"], chapter.root / s["audio"], params))
        print(f"  [voix de secours] {s['text'][:50]}")
    except Exception as e:
        print(f"  [!] {e}")
    finally:
        chatterbox_tts.close()


def sample(chapter, design):
    """La voix du personnage, à écouter dans le Studio : sa référence (Busy si les voix sont en cours de création)."""
    path = voices_dir(chapter) / f"{hashlib.sha1(design.encode('utf-8')).hexdigest()[:12]}.wav"
    if path.is_file():
        return path
    if not _BUSY.acquire(blocking=False):
        raise Busy("occupé")
    try:
        return reference(chapter, design)
    finally:
        close()
        _BUSY.release()
