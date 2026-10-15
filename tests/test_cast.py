import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from manhwa import cast
from manhwa.config import load_config
from manhwa.faces import MODELS, assign, cluster, faces_key, models_dir
from manhwa.images import write_jpeg
from manhwa.panels import build_frames, load_analysis
from manhwa.project import Chapter
from manhwa.studio.server import create_app

CID = "Série Test/chapter-001"


def unit(*v):
    v = np.array(v, np.float32)
    return v / np.linalg.norm(v)


def test_cluster_groups_similar_heads_and_keeps_others_apart():
    a, b = unit(1, 0, 0), unit(0, 1, 0)
    near_a = unit(1, 0.1, 0)
    groups = cluster([a, b, near_a, unit(1, 0, 0.1), unit(0, 0, 1)])
    assert sorted(map(sorted, groups)) == [[0, 2, 3], [1], [4]]
    assert cluster([]) == []


def test_assign_uses_known_characters_then_new_groups():
    hero, thug, window = unit(1, 0, 0), unit(0, 1, 0), unit(0, 0, 1)
    faces = [{"id": f"f{i:04d}", "char": None} for i in range(5)]
    vecs = [unit(1, 0.05, 0), thug, unit(0.05, 1, 0), unit(0, 0.02, 1), unit(0.6, 0, 0.8)]
    created = []

    def new():
        created.append(f"c{len(created) + 10}")
        return created[-1]

    assign(faces, vecs, {"c1": hero}, [window], new)
    assert faces[0]["char"] == "c1"                                # reconnu : déjà nommé dans la série
    assert faces[1]["char"] == faces[2]["char"] == created[0]      # deux têtes proches : nouveau personnage
    assert faces[3].get("not_face") and faces[3]["char"] is None   # comme une forme déjà écartée
    assert faces[4]["char"] is None                                # seule : à ranger à la main


def frame(file, crop, bubbles):
    return {"file": file, "crop": crop, "bubbles": bubbles}


def bubble(text, box, kind="dialogue"):
    return {"text": text, "kind": kind, "box": box, "conf": 0.99}


def test_lines_suggest_the_face_nearest_to_the_bubble():
    crew = {"characters": [{"id": "c1", "name": "Hero"}, {"id": "c2", "name": ""}], "next": 3}
    data = {
        "frames": [
            frame("frame_0001.jpg", [0, 0, 800, 1000], [bubble("HELLO.", [600, 100, 150, 60]), bubble("BAM", [0, 0, 50, 50], "sfx")]),
            frame("frame_0002.jpg", [0, 1000, 800, 600], [bubble("WHO ARE YOU?", [100, 50, 200, 60])]),
        ],
        "faces": {"key": "x", "list": [
            {"id": "f0001", "frame": "frame_0001.jpg", "box": [80, 600, 120, 120], "char": "c1"},
            {"id": "f0002", "frame": "frame_0001.jpg", "box": [600, 250, 120, 120], "char": "c2"},
        ]},
    }
    lines = cast.lines(data, crew)
    assert [l["text"] for l in lines] == ["HELLO.", "WHO ARE YOU?"]  # le SFX n'est pas une réplique
    assert lines[0]["suggestion"] == "c2" and lines[0]["candidates"][:2] == ["c2", "c1"]
    assert lines[1]["faces"] == [] and lines[1]["suggestion"] in ("c1", "c2")  # personnage de la case d'avant
    v = lines[0]["view"]
    assert v[0] == 0 and v[2] == 800 and v[1] <= 100 and v[1] + v[3] >= 720  # la bulle et les deux visages

    assert cast.set_speakers(data, [{"key": "frame_0001.jpg#0", "char": "c1"}, {"key": "frame_0002.jpg#0", "char": cast.NARRATOR}]) == 2
    assert data["frames"][0]["speakers"] == {"HELLO.": "c1"}
    lines = cast.lines(data, crew)
    assert [l["speaker"] for l in lines] == ["c1", cast.NARRATOR]
    cast.set_speakers(data, [{"key": "frame_0001.jpg#0", "char": None}, {"key": "frame_0009.jpg#0", "char": "c1"}])
    assert cast.lines(data, crew)[0]["speaker"] is None


@pytest.fixture
def inbox(tmp_path):
    rng = np.random.default_rng(1)
    white = lambda h: np.full((h, 400, 3), 255, np.uint8)
    art = lambda h: rng.integers(0, 255, (h, 400, 3), dtype=np.uint8)
    pages = tmp_path / "Série Test" / "chapter-001" / "pages"
    pages.mkdir(parents=True)
    write_jpeg(pages / "001.jpg", np.vstack([white(40), art(500), white(100), art(300)]), 95)
    return tmp_path


@pytest.fixture
def client(inbox):
    cfg = load_config()
    cfg["inbox"] = str(inbox)
    return TestClient(create_app(cfg)), cfg, Chapter(inbox / "Série Test" / "chapter-001")


def fake_faces(chapter, cfg):
    """Ce que run_faces aurait trouvé, sans les modèles : deux visages du même personnage + un inconnu."""
    data = chapter.load()
    first = data["frames"][0]
    first["bubbles"] = [bubble("YOU'RE BACK.", [20, 20, 200, 50])]
    crew = cast.load_cast(chapter)
    cid = cast.new_character(crew, cover="chapter-001/f0001")
    faces = [{"id": "f0001", "frame": first["file"], "box": [40, 200, 80, 80], "char": cid},
             {"id": "f0002", "frame": first["file"], "box": [250, 200, 80, 80], "char": cid},
             {"id": "f0003", "frame": data["frames"][1]["file"], "box": [10, 10, 60, 60], "char": None}]
    data["faces"] = {"key": faces_key(load_analysis(chapter, cfg, compute=False), data["frames"]), "list": faces}
    chapter.save(data)
    cast.save_cast(chapter, crew)
    folder = cast.faces_dir(chapter)
    folder.mkdir(parents=True)
    for f in faces:
        write_jpeg(folder / f"{f['id']}.jpg", np.full((32, 32, 3), 128, np.uint8))
    return cid


def test_studio_cast_screen_moves_names_and_speakers(client):
    api, cfg, chapter = client
    assert api.get("/api/cast", params={"id": CID}).json()["status"] == "missing"
    assert api.post("/api/cast/analyze", params={"id": CID}).status_code == 422  # pas encore de frames
    api.get("/api/chapter", params={"id": CID})
    build_frames(chapter, cfg)
    cid = fake_faces(chapter, cfg)

    c = api.get("/api/cast", params={"id": CID}).json()
    assert c["status"] == "ready" and c["unsorted"] == ["f0003"]
    assert c["characters"] == [{"id": cid, "name": "", "cover": "chapter-001/f0001", "faces": ["f0001", "f0002"]}]
    line = c["lines"][0]
    assert line["text"] == "YOU'RE BACK." and line["suggestion"] == cid

    # nommer : enregistré pour toute la série
    c = api.put("/api/cast/name", params={"id": CID}, json={"char": cid, "name": "  Seo   Ha-eun "}).json()
    assert c["characters"][0]["name"] == "Seo Ha-eun"
    assert json.loads((chapter.root.parent / "characters.json").read_text(encoding="utf-8"))["characters"][0]["name"] == "Seo Ha-eun"

    # un visage mal rangé → nouveau personnage ; l'autre → « pas un visage »
    c = api.post("/api/cast/move", params={"id": CID}, json={"faces": ["f0002"], "to": "new"}).json()
    new = c["moved_to"]
    assert [ch["faces"] for ch in c["characters"]] == [["f0001"], ["f0002"]]
    c = api.post("/api/cast/move", params={"id": CID}, json={"faces": ["f0003"], "to": "not_face"}).json()
    assert c["rejected"] == ["f0003"] and c["unsorted"] == []
    # le nouveau personnage, sans nom, disparaît quand il n'a plus de visage
    c = api.post("/api/cast/move", params={"id": CID}, json={"faces": ["f0002"], "to": cid}).json()
    assert [ch["id"] for ch in c["characters"]] == [cid] and new != cid
    assert api.post("/api/cast/move", params={"id": CID}, json={"faces": ["f0001"], "to": "c99"}).status_code == 422

    # qui parle
    c = api.post("/api/cast/speakers", params={"id": CID}, json={"choices": [{"key": line["key"], "char": cid}]}).json()
    assert c["changed"] == 1 and c["lines"][0]["speaker"] == cid

    # images
    assert api.get("/api/face", params={"id": CID, "f": "f0001"}).content[:2] == b"\xff\xd8"
    assert api.get("/api/face", params={"id": CID, "f": "chapter-001/f0002"}).status_code == 200
    assert api.get("/api/face", params={"id": CID, "f": "../../x/f0001"}).status_code == 422
    v = line["view"]
    crop = api.get("/api/crop", params={"id": CID, "frame": line["frame"], "y": v[1], "h": v[3]})
    assert crop.status_code == 200 and crop.content[:2] == b"\xff\xd8"


def test_speakers_survive_a_rebuild_of_the_frames(client):
    api, cfg, chapter = client
    api.get("/api/chapter", params={"id": CID})
    build_frames(chapter, cfg)
    data = chapter.load()
    data["frames"][0].update(bubbles=[bubble("HI.", [0, 0, 50, 20])], speakers={"HI.": "c1"})
    chapter.save(data)
    build_frames(chapter, cfg)
    assert chapter.load()["frames"][0]["speakers"] == {"HI.": "c1"}


@pytest.mark.skipif(not all((models_dir() / name).is_file() for name in MODELS), reason="modèles de visages absents")
def test_run_faces_end_to_end(client):
    api, cfg, chapter = client
    api.get("/api/chapter", params={"id": CID})
    build_frames(chapter, cfg)
    assert cast.run_faces(chapter, cfg) >= 0
    c = api.get("/api/cast", params={"id": CID}).json()
    assert c["status"] == "ready"
    assert cast.run_faces(chapter, cfg) == 0  # déjà à jour
