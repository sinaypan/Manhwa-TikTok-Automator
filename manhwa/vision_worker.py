"""Le petit programme qui fait regarder les cases à Qwen3.5-2B, lancé avec .venv-tts (torch 2.6 + CUDA).

Comme chatterbox_worker.py : à part, pour que torch ne touche jamais l'environnement du Studio.
Il lit des demandes JSON (une par ligne) sur l'entrée standard et répond une ligne JSON par demande :
    {"image" (chemin), "prompt"} → {"text"} | {"error"}
Il s'arrête quand l'entrée se ferme : la carte graphique est libérée.
N'importe rien de manhwa : il tourne dans un autre environnement Python.
"""
import json
import os
import sys

MODEL = "Qwen/Qwen3.5-2B"  # Apache 2.0 : utilisable sur une chaîne monétisée
MAX_SIDE = 768  # assez pour lire l'action, ≈ 4 s par case sur une RTX 3050


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault("HF_HOME", os.path.join(root, ".cache", "hf"))
    import torch
    from huggingface_hub import snapshot_download
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor

    folder = os.path.join(root, ".cache", "models", "qwen3.5-2b")
    if not os.path.isfile(os.path.join(folder, "model.safetensors")):
        snapshot_download(MODEL, local_dir=folder)  # ≈ 4,6 Go, une fois
    cuda = torch.cuda.is_available()
    proc = AutoProcessor.from_pretrained(folder)
    model = AutoModelForImageTextToText.from_pretrained(folder, dtype=torch.bfloat16 if cuda else torch.float32,
                                                        device_map="cuda" if cuda else "cpu")
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            job = json.loads(line)
            img = Image.open(job["image"]).convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            msgs = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": job["prompt"]}]}]
            inputs = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, return_dict=True,
                                              return_tensors="pt", enable_thinking=False).to(model.device)
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=int(job.get("max_tokens", 90)), do_sample=False,
                                     pad_token_id=proc.tokenizer.eos_token_id)
            text = proc.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            print(json.dumps({"text": text.strip()}), flush=True)
        except Exception as e:  # une case ratée n'arrête pas les autres
            print(json.dumps({"error": str(e)[:300]}), flush=True)


if __name__ == "__main__":
    main()
