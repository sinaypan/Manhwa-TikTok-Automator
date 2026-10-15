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


def test_unknown_or_escaping_chapter_is_refused(client):
    api, _ = client
    assert api.get("/api/chapter", params={"id": "../../Windows"}).status_code == 404
    assert api.get("/api/chapter", params={"id": "Nope/chapter-9"}).status_code == 404


def test_build_frames_keeps_text_of_unchanged_crops(inbox):
    cfg = load_config()
    chapter = Chapter(inbox / "Série Test" / "chapter-001")
    assert build_frames(chapter, cfg) == 3
    data = chapter.load()
    data["frames"][0].update({"text": "HELLO THERE", "ocr_key": "k"})
    chapter.save(data)
    # on retire la 2e coupe : la 1re case ne change pas et garde son texte ; la case
    # fusionnée (1020 px, plus haute qu'un écran) est coupée en 2 frames
    data["cut"]["cuts"] = data["cut"]["cuts"][:1]
    chapter.save(data)
    assert build_frames(chapter, cfg) == 3
    frames = chapter.load()["frames"]
    assert frames[0]["text"] == "HELLO THERE"
    assert [f["panel"] for f in frames] == [0, 1, 1]
    assert "text" not in frames[1]
