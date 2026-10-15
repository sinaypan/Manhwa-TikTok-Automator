import numpy as np
import pytest
from fastapi.testclient import TestClient

from manhwa import cast, llm, review, voices
from manhwa.config import load_config
from manhwa.images import write_jpeg
from manhwa.project import Chapter

VOICES = [{"name": "en-US-AndrewNeural", "gender": "Male", "locale": "en-US", "traits": "Warm"},
          {"name": "en-US-GuyNeural", "gender": "Male", "locale": "en-US", "traits": "Passion"},
          {"name": "en-US-ChristopherNeural", "gender": "Male", "locale": "en-US", "traits": "Reliable"},
          {"name": "en-US-AvaNeural", "gender": "Female", "locale": "en-US", "traits": "Caring"}]


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    """Ni clé réelle ni réseau : .env et la liste des voix sont remplacés."""
    monkeypatch.setattr(llm, "env_path", lambda: tmp_path / ".env")
    for name in llm.ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(voices, "list_voices", lambda: VOICES)


def test_gpt_settings_are_saved_in_env_and_never_shown(tmp_path):
    assert llm.normalize_base("https://x.run.app/v1/chat/completions") == "https://x.run.app/v1"
    assert not llm.public_settings()["configured"]
    llm.save_settings(base="https://x.run.app/v1/chat/completions", model="gpt-4.1", key="sk-abcdefghijkl")
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "DAILY_OPENAI_BASE_URL=https://x.run.app/v1\n" in text and "DAILY_OPENAI_KEY=sk-abcdefghijkl" in text
    shown = llm.public_settings()
    assert shown["configured"] and shown["key_hint"] == "sk-…ijkl" and "abcdefgh" not in str(shown)
    llm.save_settings(key="sk-zzzzzzzz9999")  # nouvelle clé du jour : le reste est gardé
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert text.count("DAILY_OPENAI_KEY=") == 1 and "sk-zzzzzzzz9999" in text and "x.run.app" in text


def test_prosody_combines_speed_voice_and_emotion():
    cfg = load_config()
    cfg["tts"]["rate"], cfg["tts"]["volume"], cfg["render"]["speed"] = "+0%", "+0%", 1.25
    calm = voices.prosody(cfg, {"name": "en-US-GuyNeural", "pitch": "-8Hz", "rate": "-4%"})
    assert calm == {"voice": "en-US-GuyNeural", "rate": "+20%", "pitch": "-8Hz", "volume": "+0%"}
    shout = voices.prosody(cfg, {"name": "en-US-GuyNeural", "pitch": "-8Hz", "rate": "-4%"}, "shouting")
    assert shout["rate"] == "+32%" and shout["pitch"] == "-2Hz" and shout["volume"] == "+25%"
    assert voices.hz("-99") == "-20Hz" and voices.pct("abc") == "+0%"


def test_auto_voice_avoids_taken_and_narrator_voices():
    v = voices.auto_voice("Male", {"en-US-AndrewNeural"}, "en-US-GuyNeural", VOICES)
    assert v["name"] == "en-US-ChristopherNeural"
    assert voices.auto_voice("Female", set(), "x", VOICES)["name"] == "en-US-AvaNeural"


def frame(file, bubbles, speakers=None):
    return {"file": file, "crop": [0, 0, 800, 600], "bubbles": bubbles, "speakers": speakers or {}}


def bubble(text, kind="dialogue", y=50):
    return {"text": text, "kind": kind, "box": [100, y, 300, 60], "conf": 0.8}


@pytest.fixture
def chapter(tmp_path):
    ch = Chapter(tmp_path / "Série" / "chapter-001")
    (ch.root / "pages").mkdir(parents=True)
    write_jpeg(ch.root / "pages" / "001.jpg", np.full((600, 800, 3), 200, np.uint8))
    data = ch.load()
    data["frames"] = [
        frame("frame_0001.jpg", [bubble("IDON'T THINK CAN GO."), bubble("Lh", "sfx", 300)]),
        frame("frame_0002.jpg", [bubble("Long ago, in the east...", "dialogue")], {}),
    ]
    ch.save(data)
    crew = cast.load_cast(ch)
    hero = cast.new_character(crew)
    crew["characters"][0].update(name="Hero", voice={"name": "en-US-AndrewNeural", "pitch": "-6Hz", "rate": "+0%"})
    cast.save_cast(ch, crew)
    return ch, hero


def test_review_proposes_and_waits_for_approval(chapter, monkeypatch):
    ch, hero = chapter
    cfg = load_config()
    llm.save_settings(base="https://x/v1", key="sk-test-123456")

    def fake_ask(items, context, sheet, series, number):
        assert {i["text"] for i in items} == {"IDON'T THINK CAN GO.", "Lh", "Long ago, in the east..."}
        return {
            "frame_0001.jpg#0": {"text": "I DON'T THINK I CAN GO.", "kind": "dialogue", "speaker": "Hero", "emotion": "sad"},
            "frame_0001.jpg#1": {"text": "LH", "kind": "sfx", "speaker": "unknown", "emotion": "neutral", "sfx": "impact"},
            "frame_0002.jpg#0": {"text": "Long ago, in the east...", "kind": "narration", "speaker": "narrator", "emotion": "calm"},
        }

    monkeypatch.setattr(review, "ask", fake_ask)
    assert review.run_review(ch, cfg) == 3
    data = ch.load()
    crew = cast.load_cast(ch)
    items = {(p["key"], p["field"]): p for p in review.proposals(data, crew)}
    assert set(items) == {("frame_0001.jpg#0", "text"), ("frame_0001.jpg#0", "speaker"),
                          ("frame_0002.jpg#0", "kind"), ("frame_0002.jpg#0", "speaker")}  # rien sur le SFX
    assert items[("frame_0001.jpg#0", "speaker")]["new"] == "Hero"

    # avant validation : texte d'origine, mais l'émotion est déjà là
    line = cast.lines(data, crew)[0]
    assert line["text"] == "IDON'T THINK CAN GO." and line["emotion"] == "sad"

    review.decide(data, [{"key": "frame_0001.jpg#0", "field": "text", "state": "accepted"},
                         {"key": "frame_0001.jpg#0", "field": "speaker", "state": "accepted"},
                         {"key": "frame_0002.jpg#0", "field": "kind", "state": "accepted"}])
    lines = cast.lines(data, crew)
    assert lines[0]["text"] == "I DON'T THINK I CAN GO." and lines[0]["speaker"] == hero
    assert lines[1]["kind"] == "narration" and lines[1]["suggestion"] == cast.NARRATOR

    # la voix : le héros avec sa voix (et le ton triste), la narration avec le narrateur
    from manhwa.tts import plan

    segs = plan(ch, data, cfg, crew)
    one, two = segs["frame_0001.jpg"][0], segs["frame_0002.jpg"][0]
    assert one["voice"] == "en-US-AndrewNeural" and one["emotion"] == "sad" and one["text"] == "I DON'T THINK I CAN GO."
    assert two["voice"] == cfg["tts"]["voice"] and two["speaker"] == cast.NARRATOR
    assert len(segs["frame_0001.jpg"]) == 1  # le SFX n'est pas lu

    # une relecture refaite garde les décisions déjà prises
    ch.save(data)
    review.run_review(ch, cfg)
    states = {(p["key"], p["field"]): p["state"] for p in review.proposals(ch.load(), crew)}
    assert states[("frame_0001.jpg#0", "text")] == "accepted" and states[("frame_0002.jpg#0", "speaker")] == "pending"

    review.set_emotion(data, "frame_0001.jpg#0", "angry")
    assert cast.lines(data, crew)[0]["emotion"] == "angry"
    with pytest.raises(ValueError):
        review.set_emotion(data, "frame_0001.jpg#0", "joie")


def test_studio_settings_and_voice_choice(chapter):
    ch, hero = chapter
    cfg = load_config()
    cfg["inbox"] = str(ch.root.parent.parent)
    api = TestClient(create_app(cfg))
    cid = "Série/chapter-001"
    r = api.put("/api/settings/gpt", json={"base": "https://x/v1/chat/completions", "key": "sk-secret-abcdef"}).json()
    assert r["gpt"]["configured"] and "secret" not in str(r)
    assert "secret" not in api.get("/api/settings").text
    assert api.put("/api/settings/gpt", json={"key": "has space"}).status_code == 422

    c = api.put("/api/cast/character", params={"id": cid}, json={"char": hero, "voice": {"name": "en-US-GuyNeural", "pitch": "-40", "rate": "+5"}}).json()
    v = c["characters"][0]
    assert v["voice"]["name"] == "en-US-GuyNeural" and v["voice"]["pitch"] == "-20Hz" and v["voice_ok"]
    assert api.put("/api/cast/character", params={"id": cid}, json={"char": hero, "voice": {"name": "nope"}}).status_code == 422
    c = api.put("/api/cast/narrator", params={"id": cid}, json={"voice": {"name": "en-US-AvaNeural"}}).json()
    assert c["narrator_voice"]["name"] == "en-US-AvaNeural" and c["emotions"]["sad"] == "triste"
    assert api.get("/api/review", params={"id": cid}).json()["items"] == []


from manhwa.studio.server import create_app  # noqa: E402  (après le monkeypatch des voix)


def test_secondary_characters_and_extras(chapter):
    ch, hero = chapter
    cfg = load_config()
    cfg["inbox"] = str(ch.root.parent.parent)
    api = TestClient(create_app(cfg))
    cid = "Série/chapter-001"
    c = api.post("/api/cast/new", params={"id": cid}, json={"name": "  Garde  ", "key": "frame_0001.jpg#0"}).json()
    guard = c["created"]
    assert next(x for x in c["characters"] if x["id"] == guard)["name"] == "Garde"
    lines = cast.lines(ch.load(), cast.load_cast(ch))
    assert lines[0]["speaker"] == guard  # il dit la réplique tout de suite, sans visage
    assert api.post("/api/cast/new", params={"id": cid}, json={"name": " "}).status_code == 422

    # un figurant : une voix du bon genre, différente de celle du héros, réglable
    c = api.post("/api/cast/speakers", params={"id": cid}, json={"choices": [{"key": "frame_0002.jpg#0", "char": "extra_f"}]}).json()
    assert cast.lines(ch.load(), cast.load_cast(ch))[1]["speaker"] == "extra_f"
    assert c["extras"]["extra_f"]["voice"]["name"] == "en-US-AvaNeural"
    from manhwa.tts import plan

    segs = plan(ch, ch.load(), cfg)
    assert segs["frame_0002.jpg"][0]["voice"] == "en-US-AvaNeural"
    c = api.put("/api/cast/extra", params={"id": cid}, json={"extra": "extra_m", "voice": {"name": "en-US-GuyNeural"}}).json()
    assert c["extras"]["extra_m"]["voice"]["name"] == "en-US-GuyNeural"
    assert api.put("/api/cast/extra", params={"id": cid}, json={"extra": "x", "voice": {"name": "en-US-GuyNeural"}}).status_code == 422
