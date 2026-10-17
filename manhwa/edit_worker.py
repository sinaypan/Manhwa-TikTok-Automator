"""Le petit programme qui redessine un détail d'une case avec FLUX.2 [klein] 4B (Apache 2.0), lancé avec .venv-edit.

À part, comme qwen_worker.py : diffusers et son torch restent hors de l'environnement du Studio.
    python edit_worker.py jobs.json
jobs.json : [{"image" (chemin), "prompt", "out" (.png), "seed"}, …] ; une ligne JSON par image faite.

Sur une carte de 6 Go : les consignes sont lues une fois pour toutes (le lecteur de texte, 8 Go, tourne sur
le processeur ; gardées dans .cache/), ensuite le modèle d'image est gardé en 8 bits sur la carte.
N'importe rien de manhwa : il tourne dans un autre environnement Python.

Installation (≈ 16 Go de modèle, téléchargé au premier usage) :
    uv venv --python 3.12 .venv-edit
    uv pip install --python .venv-edit/Scripts/python.exe torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
    uv pip install --python .venv-edit/Scripts/python.exe diffusers transformers accelerate safetensors pillow
"""
import gc
import hashlib
import json
import os
import sys
import time

MODEL = "black-forest-labs/FLUX.2-klein-4B"


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault("HF_HOME", os.path.join(root, ".cache", "hf"))
    import torch
    from diffusers import Flux2KleinPipeline
    from huggingface_hub import snapshot_download
    from PIL import Image

    jobs = json.load(open(sys.argv[1], encoding="utf-8"))
    folder = os.path.join(root, ".cache", "models", "flux2-klein-4b")
    if not os.path.isfile(os.path.join(folder, "transformer", "config.json")):
        snapshot_download(MODEL, local_dir=folder, ignore_patterns=["flux-2-klein-4b.safetensors", "*.jpg"])  # ≈ 16 Go

    t = time.time()
    # les consignes lues une fois pour toutes (≈ 1 min chacune sur le processeur), gardées sur le disque
    store = os.path.join(root, ".cache", "models", "flux2-klein-prompts")
    os.makedirs(store, exist_ok=True)
    path_of = lambda p: os.path.join(store, hashlib.sha1(p.encode("utf-8")).hexdigest()[:16] + ".pt")
    embeds = {p: torch.load(path_of(p)) for p in dict.fromkeys(j["prompt"] for j in jobs) if os.path.isfile(path_of(p))}
    new = [p for p in dict.fromkeys(j["prompt"] for j in jobs) if p not in embeds]
    if new:
        pipe = Flux2KleinPipeline.from_pretrained(folder, transformer=None, vae=None, torch_dtype=torch.bfloat16)
        with torch.no_grad():
            for prompt in new:
                embeds[prompt] = pipe.encode_prompt(prompt, device="cpu")[0]
                torch.save(embeds[prompt], path_of(prompt))
        del pipe
        gc.collect()
    # les consignes sont complétées à 512 éléments : coupées à leur vraie longueur (≈ 50), le dessin est
    # pareil, plus rapide, et le modèle ne déborde plus de la carte de 6 Go (mesuré : 15 s au lieu de 17,5)
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(os.path.join(folder, "tokenizer"))
    for prompt, e in embeds.items():
        text = tok.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True,
                                       enable_thinking=False)
        embeds[prompt] = e[:, :len(tok(text)["input_ids"])]
    print(json.dumps({"encoded": len(new), "s": round(time.time() - t, 1)}), flush=True)

    t = time.time()
    pipe = Flux2KleinPipeline.from_pretrained(folder, text_encoder=None, tokenizer=None, torch_dtype=torch.bfloat16)
    pipe.transformer.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16)
    pipe.to("cuda")
    print(json.dumps({"ready": True, "s": round(time.time() - t, 1)}), flush=True)
    for j in jobs:
        t = time.time()
        try:
            img = Image.open(j["image"]).convert("RGB")
            out = pipe(image=img, prompt_embeds=embeds[j["prompt"]].to("cuda"), height=img.height, width=img.width,
                       num_inference_steps=int(j.get("steps", 4)), guidance_scale=1.0,
                       generator=torch.Generator("cuda").manual_seed(int(j.get("seed", 0)))).images[0]
            tmp = j["out"] + ".part.png"
            out.save(tmp)
            os.replace(tmp, j["out"])  # arrêté en pleine écriture : pas de dessin à moitié gardé
            print(json.dumps({"ok": j["out"], "s": round(time.time() - t, 1),
                              "vram": round(torch.cuda.max_memory_allocated() / 2 ** 30, 2)}), flush=True)
        except Exception as e:  # une image ratée n'arrête pas les autres
            print(json.dumps({"error": str(e)[:300], "out": j["out"]}), flush=True)
        torch.cuda.empty_cache()  # la carte ne garde rien d'un dessin à l'autre : pas de débordement


if __name__ == "__main__":
    main()
