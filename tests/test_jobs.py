import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from manhwa import sfx
from manhwa.config import load_config
from manhwa.images import write_jpeg
from manhwa.panels import build_frames
from manhwa.project import Chapter
from manhwa.studio.jobs import Jobs

CID = "Série/chapter-001"


def wait(jobs, key, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        job = jobs.get(key)
        if job and job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("travail pas fini")


def test_auto_skips_optional_steps_that_fail(monkeypatch):
    jobs = Jobs(load_config())
    names = [n for n, _, _ in jobs._steps("auto", {})]
    assert names == ["frames", "ocr", "textfix", "faces", "scene", "wiki", "review", "voices", "sounds", "pilot", "tts", "render",
                     "listen", "parts"]
    assert [o for _, _, o in jobs._steps("auto", {})] == [False, False, False, False, True, True, True, True, True, True, False, False, True, True]
    ran = []

    def fail(c, p):
        raise RuntimeError("Clé GPT absente")

    monkeypatch.setattr(jobs, "_steps", lambda kind, params: [
        ("frames", lambda c, p: ran.append("frames"), False),
        ("review", fail, True),
        ("tts", lambda c, p: ran.append("tts"), False),
    ])
    jobs.submit("a", None, "auto")
    job = wait(jobs, "a")
    assert job["status"] == "done" and ran == ["frames", "tts"]
    assert job["warnings"] == ["Relecture GPT : Clé GPT absente"]

    monkeypatch.setattr(jobs, "_steps", lambda kind, params: [("tts", fail, False)])
    jobs.submit("b", None, "make")
    assert wait(jobs, "b")["status"] == "error"


@pytest.fixture
def client(tmp_path):
    pages = tmp_path / "Série" / "chapter-001" / "pages"
    pages.mkdir(parents=True)
    rng = np.random.default_rng(3)
    write_jpeg(pages / "001.jpg", np.vstack([np.full((40, 400, 3), 255, np.uint8), rng.integers(0, 255, (500, 400, 3), dtype=np.uint8),
                                             np.full((100, 400, 3), 255, np.uint8), rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)]), 95)
    cfg = load_config()
    cfg["inbox"] = str(tmp_path)
    from manhwa.studio.server import create_app

    return TestClient(create_app(cfg)), cfg, Chapter(pages.parent)


def test_import_checks_the_link_and_selection(client):
    api, _, _ = client
    assert api.post("/api/import", json={"url": "pas un lien"}).status_code == 422
    assert api.post("/api/import", json={"url": "https://site/serie", "chapters": "abc"}).status_code == 422


def test_flags_and_silent_frame_sounds(client):
    api, cfg, chapter = client
    api.get("/api/chapter", params={"id": CID})
    build_frames(chapter, cfg)
    data = chapter.load()
    first = data["frames"][0]["file"]
    data["steps"]["render"] = {"key": "x", "timeline": [[f["file"], 2.0 * i, 2.0] for i, f in enumerate(data["frames"])]}
    chapter.save(data)

    v = api.get("/api/video_info", params={"id": CID}).json()
    assert [x["start"] for x in v["timeline"]] == [0.0, 2.0] and v["flags"] == []
    v = api.post("/api/flags", params={"id": CID}, json={"frame": first, "t": 1.234, "reason": "voice"}).json()
    flag = v["flags"][0]
    assert (flag["frame"], flag["t"], flag["reason"], flag["done"]) == (first, 1.23, "voice", False)
    assert api.post("/api/flags", params={"id": CID}, json={"frame": first, "reason": "?"}).status_code == 422
    v = api.put(f"/api/flags/{flag['id']}", params={"id": CID}, json={"done": True}).json()
    assert v["flags"][0]["done"]
    assert api.put(f"/api/flags/{flag['id']}", params={"id": CID}, json={"delete": True}).json()["flags"] == []

    # cases sans texte : GPT propose, on accepte, et le rendu prend le son
    data = chapter.load()
    assert [s["frame"] for s in sfx.silent_frames(data)] == [f["file"] for f in data["frames"]]
    data["frames"][0]["action_sound"] = {"suggested": "punch", "reason": "il frappe"}
    chapter.save(data)
    s = api.get("/api/sounds", params={"id": CID}).json()
    assert s["actions"][0]["suggested"] == "punch" and s["actions"][0]["sound"] == sfx.NONE
    s = api.post("/api/sounds", params={"id": CID}, json={"choices": [{"key": f"frame:{first}", "sound": "punch"}]}).json()
    assert s["actions"][0]["sound"] == "punch"
    sounds = sfx.frame_sounds(chapter.load())
    assert list(sounds) == [first] and "punch" in sounds[first][0].replace("\\", "/")
