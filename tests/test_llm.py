from types import SimpleNamespace

import pytest

from manhwa import llm


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setattr(llm, "load_env", lambda path=None: None)
    for k in llm.ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def fake_claude(monkeypatch, seen, text='{"ok": true}'):
    import anthropic

    class Client:
        def __init__(self, **kw):
            seen["client"] = kw
            self.messages = SimpleNamespace(create=self.create)

        def create(self, **kw):
            seen["request"] = kw
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="thinking"),
                                                                    SimpleNamespace(type="text", text=text)])

    monkeypatch.setattr(anthropic, "Anthropic", Client)


def test_claude_takes_over_without_a_gpt_key(keys):
    keys.setenv("ANTHROPIC_API_KEY", "sk-ant-test-1234")
    seen = {}
    fake_claude(keys, seen)
    assert llm.public_settings()["configured"] and not llm.public_settings()["gpt_configured"]
    assert llm.chat([{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Say ok"}]) == {"ok": True}
    req = seen["request"]
    assert req["model"] == "claude-haiku-5-5" and "temperature" not in req
    assert "Be brief." in req["system"] and "JSON" in req["system"]
    assert req["messages"] == [{"role": "user", "content": "Say ok"}]
    assert seen["client"]["base_url"] == llm.CLAUDE_URL  # jamais une adresse héritée de l'environnement


def test_claude_takes_over_when_the_gpt_key_is_refused(keys):
    keys.setenv("DAILY_OPENAI_BASE_URL", "https://proxy.example/v1")
    keys.setenv("DAILY_OPENAI_KEY", "old-key-123456")
    keys.setenv("ANTHROPIC_API_KEY", "sk-ant-test-1234")
    seen = {}
    fake_claude(keys, seen, text='Here: {"voices": []}')
    keys.setattr(llm.requests, "post", lambda *a, **k: SimpleNamespace(status_code=401, text="expired"))
    assert llm.chat([{"role": "user", "content": "json please"}]) == {"voices": []}
    img = [{"role": "user", "content": [{"type": "text", "text": "what?"},
                                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}}]}]
    llm.chat(img, json_mode=False)
    assert seen["request"]["messages"][0]["content"][1] == {
        "type": "image", "source": {"type": "base64", "data": "QUJD", "media_type": "image/jpeg"}}


def test_without_any_key_the_error_says_so(keys):
    with pytest.raises(llm.LLMError):
        llm.chat([{"role": "user", "content": "hi"}])
