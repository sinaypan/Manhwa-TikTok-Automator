"""Réécouter la voix : Whisper (local) retranscrit chaque réplique, on compare au texte.

Une réplique dont la voix ne dit pas ce qui est écrit est signalée (« La voix a dit : … ») :
souvent une erreur de lecture (« IDON'T », « YOU'RE AWAK »), parfois un mot que la voix
prononce mal. Mesuré sur le ch. 1 : 7 des 10 répliques mal lues signalées, 1 fausse
alerte sur 15 (une interjection, ignorée depuis).

Whisper travaille par fenêtres de 30 s : les répliques sont mises bout à bout (paquets de
≈ 25 s, un blanc entre deux) et chaque mot entendu revient à sa réplique par son instant.
Modèle « small » (MIT, ≈ 480 Mo), téléchargé au premier usage dans .cache/models/ et
vérifié par son empreinte. Sur la carte graphique (≈ 3× plus rapide), sinon le processeur.
Résultat dans chaque segment : heard (ce que Whisper a entendu), wer (part des mots
différents), heard_key (la voix réécoutée ; recalculé seulement si l'audio change).
"""
import difflib
import subprocess

import numpy as np

from manhwa.ocr_bench import words

LISTEN_VERSION = 2  # 2 : les instants des mots (sous-titres)
_REV = "536b0662742c02347bc0e980a01041f333bce120"
_BASE = f"https://huggingface.co/Systran/faster-whisper-small/resolve/{_REV}"
MODELS = {
    "whisper-small/config.json": (f"{_BASE}/config.json", "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828"),
    "whisper-small/model.bin": (f"{_BASE}/model.bin", "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
    "whisper-small/tokenizer.json": (f"{_BASE}/tokenizer.json", "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
    "whisper-small/vocabulary.txt": (f"{_BASE}/vocabulary.txt", "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913"),
}
RATE = 16_000
CHUNK = 25.0       # secondes de voix par passage de Whisper
GAP = 0.8          # blanc entre deux répliques
FLAG = 0.15        # au-delà de cette part de mots différents, la réplique est signalée
# des interjections que Whisper écrit chacun à sa façon (« HAH » → « Huh », « KEUK » → « K.U.K. »)
INTERJECTIONS = {"HUH", "HAH", "HA", "HAHA", "HM", "HMM", "MM", "MMM", "UM", "UH", "AH", "AHH", "OH", "EH", "KEUK",
                 "KUK", "KUH", "TSK", "PFF", "PFFT", "UGH", "ARGH", "OOF", "HEH", "EUK", "KHEUK"}
_MODEL = {}


def _model():
    if "m" not in _MODEL:
        from faster_whisper import WhisperModel

        from manhwa.faces import ensure_models, models_dir

        from manhwa.gpu import enable_cuda_dlls

        ensure_models(MODELS)
        folder = str(models_dir() / "whisper-small")
        _MODEL["m"] = None
        if enable_cuda_dlls():  # sans les DLL CUDA, CTranslate2 reste bloqué : on ne tente même pas
            try:
                import ctranslate2

                if ctranslate2.get_cuda_device_count():
                    _MODEL["m"] = WhisperModel(folder, device="cuda", compute_type="float16")
            except Exception as e:
                print(f"  [!] Whisper sur la carte graphique impossible ({e}) : processeur")
        if _MODEL["m"] is None:
            _MODEL["m"] = WhisperModel(folder, device="cpu", compute_type="int8")
    return _MODEL["m"]


def pcm(path):
    """L'audio en 16 kHz mono (avec le ffmpeg du rendu), prêt pour Whisper."""
    import imageio_ffmpeg

    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "quiet", "-i", str(path), "-f", "s16le", "-ac", "1",
                          "-ar", str(RATE), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def difference(expected, heard, names=frozenset()):
    """Part des mots attendus qui n'ont pas été entendus à leur place (0 = identique).

    names : les noms de la série (« ZHONGYANG », « KAM ») : Whisper ne les connaît pas, on les saute.
    """
    skip = set(names) | INTERJECTIONS
    clean = lambda text: [w.replace("'", "") for w in words(text) if w not in skip]  # LIZARD'S = LIZARDS
    a, b = clean(expected), clean(heard)
    if not a:
        return 0.0
    same = sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    return round(1 - same / len(a), 3)


def flagged(segment, names=None):
    """La voix ne dit pas ce qui est écrit.

    Un seul mot (« PHEW… » entendu « fuel ») ne compte que s'il n'existe pas (« PeDOCe »).
    names : les noms de la série, sautés dans la comparaison (sinon, l'écart gardé).
    """
    from manhwa.textfix import frequency

    said = words(segment.get("text"))
    wer = difference(segment["text"], segment.get("heard", ""), names) if names is not None and "heard" in segment         else segment.get("wer", 0)
    if wer < FLAG or not said:
        return False
    return len(said) >= 2 or not frequency(said[0])


def transcribe(clips, timed=False):
    """clips : [tableau audio] → [texte entendu], en passant les répliques par paquets.

    timed : renvoie aussi les mots avec leur instant dans la réplique ([[mot, début, fin]]).
    """
    model = _model()
    out = [[] for _ in clips]
    times = [[] for _ in clips]
    gap = np.zeros(int(GAP * RATE), np.float32)
    i = 0
    while i < len(clips):
        spans, parts, t = [], [], 0.0
        while i < len(clips) and (not parts or t + len(clips[i]) / RATE <= CHUNK):
            d = len(clips[i]) / RATE
            spans.append((i, t, t + d))
            parts += [clips[i], gap]
            t += d + GAP
            i += 1
        segments, _ = model.transcribe(np.concatenate(parts), language="en", beam_size=1, word_timestamps=True,
                                       condition_on_previous_text=False, vad_filter=False)
        for s in segments:
            for w in s.words or []:
                mid = (w.start + w.end) / 2
                owner = next(((k, a) for k, a, b in spans if a - GAP / 2 <= mid < b + GAP / 2), None)
                if owner is not None:
                    out[owner[0]].append(w.word)
                    times[owner[0]].append([w.word.strip(), round(max(0.0, w.start - owner[1]), 3),
                                            round(max(0.0, w.end - owner[1]), 3)])
    texts = ["".join(ws).strip() for ws in out]
    return (texts, times) if timed else texts


SHORT = 0.6        # s : une case qui passe plus vite ne se voit pas
LONG = 12.0        # s : une case affichée plus longtemps lasse


def _bubble_key(frame, text):
    """La bulle (« frame#index ») dont la voix lit ce texte."""
    from manhwa.review import effective

    j = next((b["index"] for b in effective(frame) if b["text"] == text), None)
    return f"{frame['file']}#{j}" if j is not None else None


def checks(chapter, data):
    """Ce qui cloche dans la vidéo, sans la regarder : [{"frame", "t", "kind", "text"}]."""
    from manhwa.textfix import protected_words

    timeline = (data["steps"].get("render") or {}).get("timeline") or []
    starts = {file: start for file, start, _ in timeline}
    names = protected_words(chapter, [b["text"] for f in data["frames"] for b in f.get("bubbles") or []])
    out = []
    for file, start, duration in timeline:
        if duration < SHORT:
            out.append({"frame": file, "t": start, "kind": "short", "text": f"Case affichée {duration:.1f} s seulement"})
        elif duration > LONG:
            out.append({"frame": file, "t": start, "kind": "long", "text": f"Case affichée {duration:.0f} s"})
    for f in data["frames"]:
        for s in f.get("segments") or []:
            t = starts.get(f["file"], 0.0)
            if not (chapter.root / s["audio"]).is_file():
                out.append({"frame": f["file"], "t": t, "kind": "missing", "text": f"Voix manquante : « {s['text'][:60]} »"})
            elif flagged(s, names):
                out.append({"frame": f["file"], "t": t, "kind": "heard", "key": _bubble_key(f, s["text"]),
                            "text": f"La voix a dit « {s.get('heard', '')[:60]} » au lieu de « {s['text'][:60]} »"})
    return sorted(out, key=lambda c: c["t"])


def run_listen(chapter, cfg=None, progress=None):
    """Réécoute les répliques dont l'audio a changé. Renvoie le nombre de répliques signalées."""
    data = chapter.load()
    todo = [(f["file"], k, s) for f in data["frames"] for k, s in enumerate(f.get("segments") or [])
            if s.get("heard_key") != f"{LISTEN_VERSION}:{s.get('audio_key')}" and (chapter.root / s["audio"]).is_file()]
    results = {}
    batch = 40
    for start in range(0, len(todo), batch):
        part = todo[start:start + batch]
        heard, times = transcribe([pcm(chapter.root / s["audio"]) for _, _, s in part], timed=True)
        for (file, k, s), h, ws in zip(part, heard, times):
            results[(file, k)] = (h, difference(s["text"], h), f"{LISTEN_VERSION}:{s.get('audio_key')}", ws)
        if progress:
            progress(min(start + batch, len(todo)), len(todo))
    data = chapter.load()  # relu : on a pu changer des choses pendant l'écoute
    for f in data["frames"]:
        for k, s in enumerate(f.get("segments") or []):
            got = results.get((f["file"], k))
            if got and s.get("audio_key") == got[2].split(":", 1)[1]:
                s["heard"], s["wer"], s["heard_key"], s["words"] = got  # words : les instants, pour les sous-titres
    chapter.save(data)
    n = len([c for c in checks(chapter, data) if c["kind"] == "heard"])
    print(f"  Réécoute : {len(results)} répliques, {n} où la voix ne dit pas ce qui est écrit.")
    return n
