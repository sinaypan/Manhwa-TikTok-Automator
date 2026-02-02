import os
import glob
import cv2
import argparse
import importlib.util


def load_module_from_path(py_path: str, module_name: str = "ocr_module"):
    """Importe un .py depuis un chemin (même si le nom du fichier commence par un chiffre)."""
    spec = importlib.util.spec_from_file_location(module_name, py_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossible de charger le module depuis: {py_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", required=True, help="Dossier contenant frame_*.jpg")
    parser.add_argument(
        "--ocr_py",
        default=None,
        help="Chemin vers ton .py qui contient la fonction OCR (ex: 2.advanced_slicer.py). "
             "Si non fourni, on cherche 2.advanced_slicer.py dans le dossier parent de --frames."
    )
    parser.add_argument(
        "--func",
        default="extract_text_ultra_strict_from_cv",
        help="Nom de la fonction OCR à utiliser dans le .py importé"
    )
    parser.add_argument("--append", action="store_true", help="Ajoute au transcript au lieu d'écraser")
    args = parser.parse_args()

    frames_dir = args.frames
    if not os.path.isdir(frames_dir):
        print(f"[X] Dossier frames introuvable: {frames_dir}")
        return

    # transcript dans le même dossier frames
    out_txt = os.path.join(frames_dir, "transcript.txt")

    # si ocr_py non fourni: on suppose qu'il est dans le dossier parent de frames_tiktok
    if args.ocr_py is None:
        parent = os.path.dirname(frames_dir.rstrip("\\/"))
        ocr_py = os.path.join(parent, "2.advanced_slicer.py")
    else:
        ocr_py = args.ocr_py

    if not os.path.isfile(ocr_py):
        print(f"[X] Fichier OCR .py introuvable: {ocr_py}")
        return

    # import module OCR
    ocrmod = load_module_from_path(ocr_py, module_name="advanced_slicer_import")

    if not hasattr(ocrmod, args.func):
        print(f"[X] La fonction '{args.func}' n'existe pas dans: {ocr_py}")
        print("    -> Vérifie le nom, ou passe --func <nom_fonction>")
        return

    ocr_fn = getattr(ocrmod, args.func)

    frames = sorted(glob.glob(os.path.join(frames_dir, "frame_*.jpg")))
    if not frames:
        print("[X] Aucune frame trouvée (frame_*.jpg).")
        return

    mode = "a" if args.append else "w"
    if mode == "w":
        with open(out_txt, "w", encoding="utf-8") as f:
            f.write("")

    kept, rejected, unreadable = 0, 0, 0

    for path in frames:
        img = cv2.imread(path)
        name = os.path.basename(path)

        if img is None:
            print(f"[!] Illisible: {name}")
            unreadable += 1
            continue

        txt = ocr_fn(img)

        if txt:
            kept += 1
            print(f"[OK] {name} | {txt[:80]}{'...' if len(txt) > 80 else ''}")
            with open(out_txt, "a", encoding="utf-8") as f:
                f.write(f"[{name}] : {txt}\n\n")
        else:
            rejected += 1
            print(f"[NO] {name} | (rejet: bruit/SFX)")

    print("\n--- Terminé ---")
    print(f"Gardés   : {kept}")
    print(f"Rejetés  : {rejected}")
    print(f"Illisibles: {unreadable}")
    print(f"Sortie   : {out_txt}")
    print(f"OCR .py   : {ocr_py}")
    print(f"Fonction  : {args.func}")


if __name__ == "__main__":
    main()
