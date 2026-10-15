"""Ligne de commande : python -m manhwa <commande> ...

    download <url>   télécharge des chapitres dans inbox/
    status [chemin]  état de chaque chapitre
    slice <chemin>   découpe manuelle des frames 9:16
    ocr <chemin>     lit le texte des frames
    tts <chemin>     génère les voix
    render <chemin>  assemble la vidéo
    make [chemin]    tout d'un coup (découpe si besoin → OCR → voix → vidéo)

<chemin> peut être un chapitre, une série ou tout l'inbox (par défaut).
"""
import argparse
import sys
from pathlib import Path

from manhwa.config import inbox_dir, load_config, load_env
from manhwa.project import find_chapters

STEPS = ("pages", "frames", "texte", "voix", "vidéo")


def chapter_progress(chapter, cfg):
    """Nombre d'étapes faites sur 5, et le détail pour l'affichage."""
    from manhwa.ocr import ocr_key
    from manhwa.render import render_key
    from manhwa.tts import audio_key

    data = chapter.load()
    frames = data["frames"]
    pages = len(chapter.pages())
    texts = [f for f in frames if f.get("text")]
    ocr_done = bool(frames) and all(f.get("ocr_key") == ocr_key(f, data, cfg) for f in frames)
    tts_done = ocr_done and all(
        f.get("audio_key") == audio_key(f["text"], cfg) and (chapter.root / f.get("audio", "")).is_file()
        for f in texts
    )
    video_done = chapter.video_path.is_file() and data["steps"].get("render", {}).get("key") == render_key(chapter, data, cfg)
    done = [pages > 0, bool(frames), ocr_done, tts_done, video_done]
    # une étape ne compte que si toutes les précédentes sont faites
    count = next((i for i, ok in enumerate(done) if not ok), len(done))
    detail = f"{pages} pages · {len(frames)} frames · {len(texts)} textes"
    return count, detail


def progress_bar(count, total=len(STEPS), width=10):
    filled = round(width * count / total)
    return "█" * filled + "░" * (width - filled)


def resolve_chapters(path, cfg):
    path = Path(path) if path else inbox_dir(cfg)
    chapters = find_chapters(path)
    if not chapters:
        print(f"Aucun chapitre trouvé dans {path}")
        print("Un chapitre = un dossier avec des images (ou un sous-dossier pages/ avec des images).")
    return chapters


def cmd_status(args, cfg):
    chapters = resolve_chapters(args.path, cfg)
    if not chapters:
        return 1
    width = max(len(c.name) for c in chapters)
    for chapter in chapters:
        count, detail = chapter_progress(chapter, cfg)
        step = "terminé" if count == len(STEPS) else f"prochaine étape : {STEPS[count]}"
        print(f"{chapter.name:<{width}}  {progress_bar(count)} {count}/{len(STEPS)}  {detail}  ({step})")
    return 0


def cmd_download(args, cfg):
    from manhwa.ingest.scraper import download_series

    try:
        download_series(args.url, cfg, selection=args.chapters, series=args.series, force=args.force)
    except ValueError as e:
        print(e)
        return 1
    return 0


def _for_each(args, cfg, label, fn):
    chapters = resolve_chapters(args.path, cfg)
    for chapter in chapters:
        print(f"== {label} : {chapter.name}")
        fn(chapter)
    return 0 if chapters else 1


def cmd_slice(args, cfg):
    from manhwa.slicer import run_slicer

    return _for_each(args, cfg, "Découpe", lambda c: run_slicer(c, cfg))


def cmd_ocr(args, cfg):
    from manhwa.ocr import run_ocr

    return _for_each(args, cfg, "OCR", lambda c: run_ocr(c, cfg, force=args.force))


def cmd_tts(args, cfg):
    from manhwa.tts import run_tts

    return _for_each(args, cfg, "Voix", lambda c: run_tts(c, cfg, force=args.force))


def cmd_render(args, cfg):
    from manhwa.render import run_render

    return _for_each(args, cfg, "Rendu", lambda c: run_render(c, cfg, force=args.force))


def cmd_make(args, cfg):
    from manhwa.ocr import run_ocr
    from manhwa.render import run_render
    from manhwa.slicer import run_slicer
    from manhwa.tts import run_tts

    def make(chapter):
        if not chapter.load()["frames"]:
            if args.no_slice:
                print("  Pas encore découpé : ignoré (--no-slice).")
                return
            print("  [1/4] Découpe")
            if not run_slicer(chapter, cfg) or not chapter.load()["frames"]:
                print("  Aucune frame gardée : chapitre ignoré.")
                return
        print("  [2/4] OCR")
        run_ocr(chapter, cfg)
        print("  [3/4] Voix")
        run_tts(chapter, cfg)
        print("  [4/4] Vidéo")
        run_render(chapter, cfg)

    return _for_each(args, cfg, "Chapitre", make)


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m manhwa", description="Manhwa TikTok Automator")
    parser.add_argument("--config", help="autre fichier config.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("download", help="télécharger des chapitres dans inbox/")
    p.add_argument("url", help="URL de la page de la série")
    p.add_argument("-c", "--chapters", help="ex : 12, 1-5, 1-5,8, all, latest (sinon demandé)")
    p.add_argument("--series", help="nom du dossier de la série (sinon lu sur la page)")
    p.add_argument("--force", action="store_true", help="retélécharger même si déjà complet")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("status", help="état des chapitres")
    p.add_argument("path", nargs="?", help="chapitre, série ou inbox (par défaut)")
    p.set_defaults(func=cmd_status)

    for name, func, help_text in [
        ("slice", cmd_slice, "découpe manuelle des frames"),
        ("ocr", cmd_ocr, "lire le texte des frames"),
        ("tts", cmd_tts, "générer les voix"),
        ("render", cmd_render, "assembler la vidéo"),
        ("make", cmd_make, "tout d'un coup"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("path", nargs="?", help="chapitre, série ou inbox (par défaut)")
        if name in ("ocr", "tts", "render"):
            p.add_argument("--force", action="store_true", help="refaire même si déjà à jour")
        if name == "make":
            p.add_argument("--no-slice", action="store_true", help="ignorer les chapitres pas encore découpés")
        p.set_defaults(func=func)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # accents et barres dans la console Windows
    args = build_parser().parse_args(argv)
    load_env()
    cfg = load_config(args.config)
    try:
        return args.func(args, cfg)
    except KeyboardInterrupt:
        print("\nInterrompu. Tout ce qui était fini est sauvegardé.")
        return 130
    except RuntimeError as e:
        print(f"Erreur : {e}")
        return 1
