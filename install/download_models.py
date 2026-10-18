"""Télécharge d'avance les modèles d'un environnement, pour que le premier épisode ne s'arrête pas dessus.

    .venv-edit\\Scripts\\python install\\download_models.py edit

Sans ça, chaque modèle se télécharge au premier usage (même dossier, mêmes conditions que les
petits programmes *_worker.py) : ce script ne fait que le faire plus tôt. Relancé, il ne refait rien.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("HF_HOME", os.path.join(ROOT, ".cache", "hf"))
MODELS = os.path.join(ROOT, ".cache", "models")

# (dépôt Hugging Face, dossier dans .cache/models, fichier qui dit « déjà là », fichiers à ne pas prendre)
WANTED = {
    "tts": [("Qwen/Qwen3.5-2B", "qwen3.5-2b", "model.safetensors.index.json", None),  # vision_worker.py, ≈ 4,6 Go
            ("laion/larger_clap_general", "clap-general", "config.json", None)],      # clap_worker.py
    "qwen": [("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "qwen3-tts-design", "config.json", None)],  # qwen_worker.py, ≈ 4,3 Go
    "edit": [("black-forest-labs/FLUX.2-klein-4B", "flux2-klein-4b", os.path.join("transformer", "config.json"),
              ["flux-2-klein-4b.safetensors", "*.jpg"])],                             # edit_worker.py, ≈ 16 Go
}


def main(env):
    from huggingface_hub import snapshot_download

    for repo, name, marker, ignore in WANTED[env]:
        folder = os.path.join(MODELS, name)
        if os.path.isfile(os.path.join(folder, marker)):
            print(f"  {repo} : déjà là")
            continue
        print(f"  {repo} : téléchargement…", flush=True)
        snapshot_download(repo, local_dir=folder, ignore_patterns=ignore)
    if env == "tts":  # Chatterbox range ses poids dans le cache Hugging Face (HF_HOME) : on le laisse faire
        from chatterbox.tts import ChatterboxTTS
        from chatterbox.vc import ChatterboxVC

        print("  Chatterbox : téléchargement (ou déjà là)…", flush=True)
        ChatterboxVC.from_pretrained("cpu")
        ChatterboxTTS.from_pretrained(device="cpu")
    print("  Modèles prêts.")


if __name__ == "__main__":
    main(sys.argv[1])
