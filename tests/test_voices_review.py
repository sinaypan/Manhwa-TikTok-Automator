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


def test_review_keeps_my_own_version(chapter, monkeypatch):
    ch, hero = chapter
    cfg = load_config()
    llm.save_settings(base="https://x/v1", key="sk-test-123456")
    monkeypatch.setattr(review, "ask", lambda items, *a: {
        "frame_0001.jpg#0": {"text": "I DON'T THINK CAN GO!", "kind": "dialogue", "speaker": "unknown", "emotion": "sad"},
        "frame_0002.jpg#0": {"text": "Long ago, in the east...", "kind": "narration", "speaker": "unknown", "emotion": "calm"},
    })
    review.run_review(ch, cfg)
    data = ch.load()
    crew = cast.load_cast(ch)
    # ma version au lieu de celle de GPT ; une valeur invalide ne change rien
    assert review.decide(data, [{"key": "frame_0001.jpg#0", "field": "text", "state": "accepted", "value": "  I DON'T THINK  I CAN GO. "},
                                {"key": "frame_0002.jpg#0", "field": "kind", "state": "accepted", "value": "joie"}]) == 1
    assert review.decide(data, [{"key": "frame_0002.jpg#0", "field": "kind", "state": "accepted", "value": "thought"}]) == 1
    lines = cast.lines(data, crew)
    assert lines[0]["text"] == "I DON'T THINK I CAN GO." and lines[1]["kind"] == "thought"
    ch.save(data)
    review.run_review(ch, cfg)  # GPT repasse : ma version reste, acceptée
    items = {(p["key"], p["field"]): p for p in review.proposals(ch.load(), crew)}
    assert items[("frame_0001.jpg#0", "text")]["new"] == "I DON'T THINK I CAN GO."
    assert items[("frame_0001.jpg#0", "text")]["state"] == "accepted"
    assert items[("frame_0002.jpg#0", "kind")]["new"] == "thought"


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


def test_automatic_voices_differ_by_accent_pitch_and_age():
    many = VOICES + [{"name": "en-GB-RyanNeural", "gender": "Male", "locale": "en-GB", "traits": "Bright"}]
    a = voices.auto_voice("Male", set(), "en-US-ChristopherNeural", many, rank=0)
    b = voices.auto_voice("Male", {a["name"]}, "en-US-ChristopherNeural", many, rank=1)
    assert a["name"][:5] != b["name"][:5] and a["pitch"] != b["pitch"]  # autre accent, autre hauteur
    old = voices.auto_voice("Male", set(), "x", many, page={"hair": "Silver-white"})
    assert (old["pitch"], old["rate"]) == ("-10Hz", "-8%")
    assert voices.is_old({"personality": "The old master of the sect."}) and not voices.is_old({"hair": "Black"})
    crew = [{"voice": {"name": "v", "pitch": "+0Hz"}}, {"voice": {"name": "v", "pitch": "+2Hz"}},
            {"voice": {"name": "v", "pitch": "+0Hz", "by": "user"}, "voice_ok": True}, {"voice": {"name": "w", "pitch": "+0Hz"}}]
    assert voices.spread(crew)
    assert [c["voice"]["pitch"] for c in crew] == ["+0Hz", "+8Hz", "+0Hz", "+0Hz"]  # ton choix n'est pas touché


def test_checked_bubbles_are_the_truth(chapter, monkeypatch):
    ch, hero = chapter
    cfg = load_config()
    data = ch.load()
    keys = [b["key"] for b in review.all_bubbles(data)]
    assert keys == ["frame_0001.jpg#0", "frame_0001.jpg#1", "frame_0002.jpg#0"]
    review.check_bubble(data, "frame_0001.jpg#0", text="I DON'T THINK I CAN GO.", checked=True)
    review.check_bubble(data, "frame_0002.jpg#0", kind="narration", checked=True)
    with pytest.raises(ValueError):
        review.check_bubble(data, "frame_0002.jpg#0", kind="joie")
    rows = {b["key"]: b for b in review.all_bubbles(data)}
    assert rows["frame_0001.jpg#0"]["text"] == "I DON'T THINK I CAN GO." and rows["frame_0001.jpg#0"]["checked"]
    assert rows["frame_0002.jpg#0"]["kind"] == "narration" and not rows["frame_0001.jpg#1"]["checked"]
    ch.save(data)

    # GPT repasse : il complète le ton mais ne change plus une bulle vérifiée
    llm.save_settings(base="https://x/v1", key="sk-test-123456")
    monkeypatch.setattr(review, "ask", lambda items, *a: {i["id"]: {"text": "WRONG", "kind": "dialogue", "speaker": "unknown",
                                                                     "emotion": "sad"} for i in items})
    review.run_review(ch, cfg)
    rows = {b["key"]: b for b in review.all_bubbles(ch.load())}
    assert rows["frame_0001.jpg#0"]["text"] == "I DON'T THINK I CAN GO." and rows["frame_0002.jpg#0"]["kind"] == "narration"
    from manhwa import textfix

    textfix.run_textfix(ch)
    assert {b["key"]: b for b in review.all_bubbles(ch.load())}["frame_0001.jpg#0"]["text"] == "I DON'T THINK I CAN GO."


def test_kokoro_voices_are_listed_and_read_in_normal_case():
    from manhwa import kokoro_tts

    names = [v["name"] for v in kokoro_tts.catalog()]
    assert "kokoro:am_michael" in names and len(names) == 28
    assert {v["gender"] for v in kokoro_tts.catalog() if v["name"].startswith("kokoro:bf_")} == {"Female"}
    assert kokoro_tts.label("kokoro:bm_george") == "George (UK, Kokoro)" == voices.short_name("kokoro:bm_george")
    assert kokoro_tts.readable("I DON'T THINK SO. YOU? i AM HERE") == "I don't think so. You? I am here"
    assert kokoro_tts.readable("Already in normal case.") == "Already in normal case."


def test_pilot_accepts_gpt_and_sure_speakers_but_never_your_choices(chapter, monkeypatch):
    from manhwa import pilot

    ch, hero = chapter
    cfg = load_config()
    llm.save_settings(base="https://x/v1", key="sk-test-123456")
    monkeypatch.setattr(review, "ask", lambda items, *a: {
        "frame_0001.jpg#0": {"text": "I DON'T THINK I CAN GO.", "kind": "dialogue", "speaker": "Hero", "emotion": "sad"},
        "frame_0002.jpg#0": {"text": "Long ago, in the east...", "kind": "narration", "speaker": "narrator", "emotion": "calm"},
    })
    review.run_review(ch, cfg)  # lancée à la main : tout attend ta décision
    data = ch.load()
    assert {p["state"] for p in review.proposals(data, cast.load_cast(ch))} == {"pending"}
    review.decide(data, [{"key": "frame_0002.jpg#0", "field": "kind", "state": "rejected"}])
    ch.save(data)

    cfg["auto"] = {"sounds": True, "review": True, "speakers": 0.0}
    pilot.run_pilot(ch, cfg)  # pendant « Tout faire »
    items = {(p["key"], p["field"]): p for p in review.proposals(ch.load(), cast.load_cast(ch))}
    assert items[("frame_0001.jpg#0", "text")]["state"] == "accepted" and items[("frame_0001.jpg#0", "text")]["auto"]
    assert items[("frame_0002.jpg#0", "kind")]["state"] == "rejected"  # ton refus reste
    assert pilot.summary(ch, ch.load(), cfg)["textes"] == 1
    data = ch.load()
    review.decide(data, [{"key": "frame_0001.jpg#0", "field": "text", "state": "rejected"}])
    assert not {(p["key"], p["field"]): p for p in review.proposals(data, cast.load_cast(ch))}[("frame_0001.jpg#0", "text")]["auto"]


def test_expressive_voice_carries_the_emotion():
    cfg = load_config()
    plain = voices.prosody(cfg, {"name": "en-US-AndrewNeural"}, "angry")
    assert "expressive" not in plain  # sans la case cochée : rien ne change (mêmes fichiers qu'avant)
    rich = voices.prosody(cfg, {"name": "en-US-AndrewNeural", "expressive": True}, "angry")
    assert rich["expressive"] and rich["emotion"] == "angry"
    assert cast.clean_voice({"name": "en-US-AndrewNeural", "expressive": True})["expressive"]
    assert "expressive" not in cast.clean_voice({"name": "en-US-AndrewNeural"})
    from manhwa import chatterbox_tts

    assert chatterbox_tts.INTENSITY["shouting"] > chatterbox_tts.INTENSITY["neutral"] > chatterbox_tts.INTENSITY["sad"]


def test_json_requests_always_mention_json(monkeypatch):
    llm.save_settings(base="https://x/v1", key="sk-test-123456")
    sent = []

    class Ok:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    monkeypatch.setattr(llm.requests, "post", lambda url, json, **k: sent.append(json) or Ok())
    assert llm.ping()
    llm.chat([{"role": "user", "content": "Say hi"}])  # le proxy (Azure) exige le mot « json »
    assert all(any("json" in m["content"].lower() for m in body["messages"]) for body in sent)


def test_not_text_drops_its_pending_proposals(chapter):
    ch, hero = chapter
    data = ch.load()
    frame = data["frames"][0]
    frame["review"] = {"IDON'T THINK CAN GO.": {"text": "I DON'T THINK I CAN GO.", "speaker": hero,
                                                "state": {"text": "pending", "speaker": "pending"}}}
    review.check_bubble(data, "frame_0001.jpg#0", kind="noise", checked=True)
    r = frame["review"]["IDON'T THINK CAN GO."]
    assert r["state"] == {"text": "rejected", "speaker": "rejected", "kind": "accepted"} and r["checked"]
    assert review.all_bubbles(data)[0]["kind"] == "noise"


def test_qwen_lines_use_the_character_design_and_sentence_case(monkeypatch, tmp_path):
    from manhwa import qwen_voice, tts
    from manhwa.config import load_config

    assert qwen_voice.sentence_case("YOU PARASITE! I SAID NO.") == "You parasite! I said no."
    assert qwen_voice.sentence_case("Already fine") == "Already fine"
    monkeypatch.setattr(qwen_voice, "available", lambda: True)
    cfg = load_config()
    cfg["tts"]["engine"] = "qwen"
    assert tts.use_qwen(cfg)
    cfg["tts"]["engine"] = "edge"
    assert not tts.use_qwen(cfg)
    assert set(qwen_voice.EMOTION) >= {"neutral", "angry", "shouting", "scared", "sad", "whisper"}


def test_without_gpt_each_character_gets_a_different_voice_asked_again_later(monkeypatch, tmp_path):
    from manhwa import llm, qwen_voice

    class Ch:
        root = tmp_path / "serie" / "ch1"

        def load(self):
            return {"frames": []}

    Ch.root.mkdir(parents=True)
    crew = {"characters": [{"id": "c1", "name": "A"}, {"id": "c2", "name": "B"}, {"id": "c3", "name": "C"}], "next": 4}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(llm.LLMError("clé expirée")))
    monkeypatch.setattr(qwen_voice, "_female_voices", lambda: [])
    assert qwen_voice.ensure_designs(Ch(), crew)
    voices = [crew["designs"][c] for c in ("c1", "c2", "c3")]
    assert len(set(voices)) == 3 and crew["designs_auto"] == ["c1", "c2", "c3"]
    assert "narrator" in crew["designs"]
    monkeypatch.setattr(llm, "chat", lambda *a, **k: {"voices": [{"id": "c2", "voice": "Gruff old smuggler, natural and human"}]})
    qwen_voice.ensure_designs(Ch(), crew)  # la clé est revenue : GPT redécrit
    assert crew["designs"]["c2"] == "Gruff old smuggler, natural and human" and "c2" not in crew["designs_auto"]
