"""Le petit programme qui fait parler Qwen3-TTS (Apache 2.0), lancé avec .venv-qwen (torch 2.6 + CUDA).

À part, comme chatterbox_worker.py : qwen-tts veut une autre version de transformers.
Une demande JSON par ligne sur l'entrée standard, une réponse par ligne :
    {"text", "instruct" (la voix décrite, et l'émotion), "out" (.wav), "seed"} → {"ok"} | {"error"}
    {"batch": [{"text", "instruct", "out"}, …], "seed"} → {"ok"} : plusieurs à la fois (≈ 2 fois plus vite à 4)
    "max_tokens" : la limite de longueur (12 par seconde de voix) ; sans elle, une réplique qui déraille
    parle jusqu'à 11 minutes et tout le paquet l'attend
Il s'arrête quand l'entrée se ferme : la carte graphique est libérée.
N'importe rien de manhwa : il tourne dans un autre environnement Python.
"""
import json
import os
import sys

MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault("HF_HOME", os.path.join(root, ".cache", "hf"))
    import soundfile as sf
    import torch
    from huggingface_hub import snapshot_download
    from qwen_tts import Qwen3TTSModel

    folder = os.path.join(root, ".cache", "models", "qwen3-tts-design")
    if not os.path.isfile(os.path.join(folder, "config.json")):
        snapshot_download(MODEL, local_dir=folder)  # ≈ 4,3 Go, une fois
    model = Qwen3TTSModel.from_pretrained(folder, device_map="cuda:0" if torch.cuda.is_available() else "cpu",
                                          dtype=torch.bfloat16, attn_implementation="sdpa")
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            job = json.loads(line)
            torch.manual_seed(int(job.get("seed", 0)))
            batch = job.get("batch") or [job]
            extra = {"max_new_tokens": int(job["max_tokens"])} if job.get("max_tokens") else {}
            wavs, sr = model.generate_voice_design(text=[b["text"] for b in batch], language=["English"] * len(batch),
                                                   instruct=[b["instruct"] for b in batch], **extra)
            for b, wav in zip(batch, wavs):
                tmp = b["out"] + ".part.wav"
                sf.write(tmp, wav, sr)
                os.replace(tmp, b["out"])
            print(json.dumps({"ok": True}), flush=True)
        except Exception as e:  # une réplique ratée n'arrête pas les autres
            print(json.dumps({"error": str(e)[:300]}), flush=True)


if __name__ == "__main__":
    main()
