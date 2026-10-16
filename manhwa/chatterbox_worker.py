"""Le petit programme qui fait parler Chatterbox, lancé avec .venv-tts (torch 2.6 + CUDA).

Il est à part pour que torch et ses dépendances figées ne touchent jamais l'environnement
du Studio. Il lit des demandes JSON (une par ligne) sur l'entrée standard et répond une
ligne JSON par demande :
    {"text", "ref" (voix de référence, 10 s), "exaggeration", "cfg", "out" (.wav)} → {"ok"} | {"error"}
Il s'arrête quand l'entrée se ferme (le Studio a fini) : la carte graphique est libérée.
N'importe rien de manhwa : il tourne dans un autre environnement Python.
"""
import json
import os
import sys


def main():
    os.environ.setdefault("HF_HOME", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "hf"))
    import torch
    import torchaudio
    from chatterbox.tts import ChatterboxTTS

    model = ChatterboxTTS.from_pretrained(device="cuda" if torch.cuda.is_available() else "cpu")
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            job = json.loads(line)
            wav = model.generate(job["text"], audio_prompt_path=job["ref"], exaggeration=float(job.get("exaggeration", 0.5)),
                                 cfg_weight=float(job.get("cfg", 0.5)))
            tmp = job["out"] + ".part.wav"
            torchaudio.save(tmp, wav, model.sr)
            os.replace(tmp, job["out"])
            print(json.dumps({"ok": True}), flush=True)
        except Exception as e:  # une réplique ratée n'arrête pas les autres
            print(json.dumps({"error": str(e)[:300]}), flush=True)


if __name__ == "__main__":
    main()
