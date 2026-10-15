import numpy as np
import pytest
from fastapi.testclient import TestClient

from manhwa.config import load_config
from manhwa.images import write_jpeg
from manhwa.panels import build_frames
from manhwa.project import Chapter
from manhwa.studio.server import create_app

CID = "Série Test/chapter-001"


@pytest.fixture
def inbox(tmp_path):
    """Un chapitre de 2 pages : 3 cases séparées par des marges blanches."""
    rng = np.random.default_rng(1)
    white = lambda h: np.full((h, 400, 3), 255, np.uint8)
    art = lambda h: rng.integers(0, 255, (h, 400, 3), dtype=np.uint8)
    pages = tmp_path / "Série Test" / "chapter-001" / "pages"
    pages.mkdir(parents=True)
    write_jpeg(pages / "001.jpg", np.vstack([white(40), art(500), white(100), art(300)]), 95)
    write_jpeg(pages / "002.jpg", np.vstack([white(120), art(600), white(40)]), 95)
    return tmp_path


@pytest.fixture
def client(inbox):
    cfg = load_config()
    cfg["inbox"] = str(inbox)
    return TestClient(create_app(cfg)), cfg


def test_library_lists_series_and_progress(client):
    api, _ = client
    lib = api.get("/api/library").json()
    assert [s["name"] for s in lib["series"]] == ["Série Test"]
    chapter = lib["series"][0]["chapters"][0]
    assert chapter["id"] == CID
    assert chapter["progress"]["done"] == 1  # pages présentes, pas encore découpé


def test_chapter_detail_proposes_cuts(client):
    api, _ = client
    ch = api.get("/api/chapter", params={"id": CID}).json()
    assert ch["width"] == 400 and ch["height"] == 1700
    assert len(ch["cuts"]) == 2 and len(ch["panels"]) == 3
    assert ch["tiles"]["count"] >= 1
    assert api.get("/api/tile", params={"id": CID, "i": 0}).headers["content-type"] == "image/jpeg"
    p = ch["panels"][0]
    preview = api.get("/api/preview", params={"id": CID, "y0": p["y0"], "y1": p["y1"]})
    assert preview.status_code == 200 and preview.content[:2] == b"\xff\xd8"


def test_edit_and_reset_cuts(client):
    api, _ = client
    ch = api.get("/api/chapter", params={"id": CID}).json()
    first = ch["cuts"][0]
    res = api.put("/api/cuts", params={"id": CID}, json={"cuts": [first], "reviewed": True}).json()
    assert len(res["panels"]) == 2
    again = api.get("/api/chapter", params={"id": CID}).json()
    assert again["cuts"] == [first] and again["edited"] and again["reviewed"]
    reset = api.post("/api/cuts/reset", params={"id": CID}).json()
    assert len(reset["cuts"]) == 2 and not reset["edited"]


def test_notice_tells_manual_frames_from_outdated_ones(client, inbox):
    api, cfg = client
    chapter = Chapter(inbox / "Série Test" / "chapter-001")
    build_frames(chapter, cfg)
    ch = api.get("/api/chapter", params={"id": CID}).json()
    assert ch["manual_frames"] == 0 and not ch["stale_frames"]
    api.put("/api/cuts", params={"id": CID}, json={"cuts": ch["cuts"][:1]})
    ch = api.get("/api/chapter", params={"id": CID}).json()
    assert ch["manual_frames"] == 0 and ch["stale_frames"]  # retouchée après la vidéo
    data = chapter.load()
    for f in data["frames"]:
        f.pop("panel")  # comme des frames de l'ancienne fenêtre
    chapter.save(data)
    assert api.get("/api/chapter", params={"id": CID}).json()["manual_frames"] == 3


def test_unknown_or_escaping_chapter_is_refused(client):
    api, _ = client
    assert api.get("/api/chapter", params={"id": "../../Windows"}).status_code == 404
    assert api.get("/api/chapter", params={"id": "Nope/chapter-9"}).status_code == 404


def test_build_frames_keeps_text_of_unchanged_crops(inbox):
    cfg = load_config()
    chapter = Chapter(inbox / "Série Test" / "chapter-001")
    assert build_frames(chapter, cfg) == 3
    data = chapter.load()
    data["frames"][0].update({"text": "HELLO THERE", "ocr_key": "k", "lines": [{"text": "HELLO THERE"}], "bubbles": []})
    chapter.save(data)
    # on retire la 2e coupe : la 1re case ne change pas et garde son texte ; la case
    # fusionnée (1020 px, moins de 2 écrans) reste une seule frame
    data["cut"]["cuts"] = data["cut"]["cuts"][:1]
    chapter.save(data)
    assert build_frames(chapter, cfg) == 2
    frames = chapter.load()["frames"]
    assert frames[0]["text"] == "HELLO THERE"
    assert frames[0]["lines"] == [{"text": "HELLO THERE"}]  # pas besoin de relire la case
    assert [f["panel"] for f in frames] == [0, 1]
    assert "text" not in frames[1]
    assert sorted(p.name for p in chapter.frames_dir.iterdir()) == ["frame_0001.jpg", "frame_0002.jpg"]


def test_preview_announces_the_same_frames_as_the_video(client, inbox):
    """Régression : l'aperçu montrait la case entière alors que la vidéo la coupait en deux."""
    api, cfg = client
    ch = api.get("/api/chapter", params={"id": CID}).json()
    api.put("/api/cuts", params={"id": CID}, json={"cuts": []})  # une seule case de 1 700 px
    chapter = Chapter(inbox / "Série Test" / "chapter-001")
    build_frames(chapter, cfg)
    video = [f["crop"] for f in chapter.load()["frames"]]
    p = api.put("/api/cuts", params={"id": CID}, json={"cuts": []}).json()["panels"][0]
    announced = api.get("/api/panel", params={"id": CID, "y0": p["y0"], "y1": p["y1"]}).json()
    assert [[a, b - a] for a, b in announced["parts"]] == [[c[1], c[3]] for c in video]
    assert len(video) == 2  # 1 660 px > 2 écrans de 711 px


def test_resort_bubbles_without_reading_images_again(inbox, monkeypatch):
    """Quand seul le tri change, les bulles sont recalculées depuis les lignes gardées."""
    import manhwa.ocr as ocr
    from manhwa.bubbles import BUBBLES_VERSION

    cfg = load_config()
    chapter = Chapter(inbox / "Série Test" / "chapter-001")
    build_frames(chapter, cfg)
    data = chapter.load()
    for f in data["frames"]:
        f["lines"] = [{"text": "WHERE ARE YOU GOING", "conf": 0.99, "box": [10, 10, 300, 40]}]
        f["ocr_key"] = ocr.ocr_key(f, data, cfg)
        f["bubbles_version"] = BUBBLES_VERSION - 1
    chapter.save(data)
    monkeypatch.setattr(ocr, "read_crop_lines", lambda *a: (_ for _ in ()).throw(AssertionError("relu !")))
    ocr.run_ocr(chapter, cfg)
    frames = chapter.load()["frames"]
    assert all(f["text"] == "WHERE ARE YOU GOING" and f["bubbles_version"] == BUBBLES_VERSION for f in frames)
