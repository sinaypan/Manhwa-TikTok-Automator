import numpy as np

from manhwa.config import load_config
from manhwa.images import letterbox, list_images, load_strip, write_jpeg
from manhwa.project import Chapter, find_chapters
from manhwa.slicer import next_frame_index, save_frame, undo_last_frame
from manhwa.tts import audio_key


def make_pages(folder, names, width=400, height=300):
    folder.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(names):
        img = np.full((height, width, 3), 20 * i, dtype=np.uint8)
        write_jpeg(folder / name, img)


def test_list_images_natural_order(tmp_path):
    make_pages(tmp_path, ["10.jpg", "2.jpg", "1.jpg", "100.jpg"])
    (tmp_path / "notes.txt").write_text("x")
    assert [p.name for p in list_images(tmp_path)] == ["1.jpg", "2.jpg", "10.jpg", "100.jpg"]


def test_find_chapters_in_inbox(tmp_path):
    make_pages(tmp_path / "Serie A" / "chapter-010" / "pages", ["001.jpg"])
    make_pages(tmp_path / "Serie A" / "chapter-002", ["1.jpg"])  # ajouté à la main
    (tmp_path / "Serie B" / "vide").mkdir(parents=True)
    names = [c.root.name for c in find_chapters(tmp_path)]
    assert names == ["chapter-002", "chapter-010"]
    # un chapitre passé directement
    assert len(find_chapters(tmp_path / "Serie A" / "chapter-010")) == 1


def test_bg_mode_changes_output():
    """Régression V1 : la touche M changeait l'affichage mais pas l'image sauvegardée."""
    crop = np.random.default_rng(0).integers(0, 255, (300, 400, 3), dtype=np.uint8)
    blur = letterbox(crop, 1080, 1920, "blur")
    black = letterbox(crop, 1080, 1920, "black")
    assert blur.shape == black.shape == (1920, 1080, 3)
    assert black[0, 0].tolist() == [0, 0, 0]
    assert not np.array_equal(blur, black)


def test_save_and_undo_frames(tmp_path):
    cfg = load_config()
    make_pages(tmp_path / "pages", ["1.jpg", "2.jpg"])
    chapter = Chapter(tmp_path)
    strip, used = load_strip(chapter.pages(), cfg["slicer"]["max_src_width"])
    assert strip.shape[:2] == (600, 400) and len(used) == 2

    data = chapter.load()
    assert save_frame(chapter, data, strip, (0, 0, 400, 300), cfg, "black") == "frame_0001.jpg"
    assert save_frame(chapter, data, strip, (0, 300, 400, 300), cfg, "black") == "frame_0002.jpg"
    assert chapter.load()["frames"][1]["crop"] == [0, 300, 400, 300]

    removed = undo_last_frame(chapter, data)
    assert removed["file"] == "frame_0002.jpg"
    assert not (chapter.frames_dir / "frame_0002.jpg").exists()
    assert next_frame_index(chapter.load()["frames"]) == 2


def test_audio_key_follows_text_and_voice():
    cfg = load_config()
    key = audio_key("Hello there", cfg)
    assert audio_key("Hello there", cfg) == key
    assert audio_key("Hello world", cfg) != key
    cfg["tts"]["voice"] = "fr-FR-HenriNeural"
    assert audio_key("Hello there", cfg) != key
