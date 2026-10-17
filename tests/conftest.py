import pytest


@pytest.fixture(autouse=True)
def no_pro_soundbank(monkeypatch):
    """Les tests ne dépendent pas de la bibliothèque pro installée sur la machine (.cache/soundbank)."""
    from manhwa import soundbank

    monkeypatch.setattr(soundbank, "_BANK", {"takes": [], "vectors": __import__("numpy").zeros((0, 512), "float32")})
