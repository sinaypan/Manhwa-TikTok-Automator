"""Le petit programme qui fait regarder les cases à Qwen3.5-2B, lancé avec .venv-tts (torch 2.6 + CUDA).

Comme chatterbox_worker.py : à part, pour que torch ne touche jamais l'environnement du Studio.
Il lit des demandes JSON (une par ligne) sur l'entrée standard et répond une ligne JSON par demande :
    {"image" (chemin), "prompt"} → {"text"} | {"error"}
    {"batch": [{"image", "prompt"}, …]} → {"texts": […]} : plusieurs cases à la fois (bien plus rapide)
Il s'arrête quand l'entrée se ferme : la carte graphique est libérée.
N'importe rien de manhwa : il tourne dans un autre environnement Python.
"""
import json
import os
import sys

MODEL = "Qwen/Qwen3.5-2B"  # Apache 2.0 : utilisable sur une chaîne monétisée
MAX_SIDE = 768  # assez pour lire l'action ; ≈ 2 s par case sur une RTX 3050, 6 à la fois


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
    proc.tokenizer.padding_side = "left"  # plusieurs cases à la fois : chacune finit au même endroit
    model = AutoModelForImageTextToText.from_pretrained(folder, dtype=torch.bfloat16 if cuda else torch.float32,
                                                        device_map="cuda" if cuda else "cpu")
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            job = json.loads(line)
            batch = job.get("batch") or [job]
            convs = []
            for b in batch:
                img = Image.open(b["image"]).convert("RGB")
                img.thumbnail((MAX_SIDE, MAX_SIDE))
                convs.append([{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": b["prompt"]}]}])

            def look(convs):
                try:
                    inputs = proc.apply_chat_template(convs, add_generation_prompt=True, tokenize=True, return_dict=True,
                                                      return_tensors="pt", padding=True, enable_thinking=False).to(model.device)
                    with torch.no_grad():
                        out = model.generate(**inputs, max_new_tokens=int(job.get("max_tokens", 90)), do_sample=False,
                                             pad_token_id=proc.tokenizer.eos_token_id)
                    return [t.strip() for t in proc.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)]
                except torch.cuda.OutOfMemoryError:  # des cases trop grandes ensemble : en deux fois
                    torch.cuda.empty_cache()
                    if len(convs) == 1:
                        raise
                    half = len(convs) // 2
                    return look(convs[:half]) + look(convs[half:])

            texts = look(convs)
            print(json.dumps({"texts": texts} if "batch" in job else {"text": texts[0]}), flush=True)
        except Exception as e:  # une case ratée n'arrête pas les autres
            print(json.dumps({"error": str(e)[:300]}), flush=True)


if __name__ == "__main__":
    main()
