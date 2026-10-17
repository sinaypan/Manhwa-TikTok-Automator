import pytest


@pytest.fixture(autouse=True)
def no_pro_soundbank(monkeypatch):
    """Les tests ne dépendent pas de la bibliothèque pro installée sur la machine (.cache/soundbank)."""
    from manhwa import soundbank

    monkeypatch.setattr(soundbank, "_BANK", {"takes": [], "vectors": __import__("numpy").zeros((0, 512), "float32")})


@pytest.fixture(autouse=True)
def no_chatterbox_for_all(monkeypatch):
    """« toutes les voix expressives » (config.toml) dépend de .venv-tts : pas dans les tests."""
    from manhwa import voices

    monkeypatch.setattr(voices, "_chatterbox", lambda: False)


@pytest.fixture(autouse=True)
def no_qwen(monkeypatch):
    """Qwen3-TTS (config.toml : engine = "qwen") dépend de .venv-qwen : pas dans les tests."""
    from manhwa import qwen_voice

    monkeypatch.setattr(qwen_voice, "available", lambda: False)
