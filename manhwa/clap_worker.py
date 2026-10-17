"""Le petit programme qui fait écouter les sons à CLAP (LAION, Apache 2.0), lancé avec .venv-tts.

CLAP met un son et une phrase (« a heavy punch ») dans le même espace : on compare l'un à l'autre.
On ne fait que s'en servir (aucun entraînement) : la licence des sons Sonniss interdit d'entraîner
une IA avec eux. Comme vision_worker.py : une demande JSON par ligne, une réponse par ligne.
    {"audio": [chemins], "out": fichier .npy} → {"ok"}   (vecteurs des sons, dans l'ordre)
    {"text": [phrases], "out": fichier .npy} → {"ok"}
Il s'arrête quand l'entrée se ferme. N'importe rien de manhwa.
"""
import json
import os
import sys

MODEL = "laion/larger_clap_general"
SECONDS = 7  # CLAP écoute 10 s au plus ; un bruitage tient dans les premières secondes


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault("HF_HOME", os.path.join(root, ".cache", "hf"))
    import librosa
    import numpy as np
    import torch
    from huggingface_hub import snapshot_download
    from transformers import ClapModel, ClapProcessor

    folder = os.path.join(root, ".cache", "models", "clap-general")
    if not os.path.isfile(os.path.join(folder, "config.json")):
        snapshot_download(MODEL, local_dir=folder)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    proc = ClapProcessor.from_pretrained(folder)
    model = ClapModel.from_pretrained(folder).to(device).eval()
    print(json.dumps({"ready": True}), flush=True)

    def unit(x):
        x = x if torch.is_tensor(x) else x.pooler_output  # transformers 5 : une sortie, et pas le vecteur
        return x / x.norm(dim=-1, keepdim=True).clamp_min(1e-9)

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            job = json.loads(line)
            out = []
            with torch.no_grad():
                if "audio" in job:
                    for k in range(0, len(job["audio"]), 16):
                        waves = []
                        for p in job["audio"][k:k + 16]:
                            try:
                                y, _ = librosa.load(p, sr=48000, mono=True, duration=SECONDS)
                            except Exception:
                                y = np.zeros(4800, np.float32)
                            waves.append(y if len(y) else np.zeros(4800, np.float32))
                        x = proc(audio=waves, sampling_rate=48000, return_tensors="pt").to(device)
                        out.append(unit(model.get_audio_features(**x)).cpu().numpy())
                else:
                    x = proc(text=job["text"], return_tensors="pt", padding=True).to(device)
                    out.append(unit(model.get_text_features(**x)).cpu().numpy())
            np.save(job["out"], np.concatenate(out).astype(np.float32))
            print(json.dumps({"ok": True}), flush=True)
        except Exception as e:
            print(json.dumps({"error": str(e)[:300]}), flush=True)


if __name__ == "__main__":
    main()
