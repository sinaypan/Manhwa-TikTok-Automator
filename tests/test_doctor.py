"""L'installateur et l'estimation de durée (doctor.py)."""
import importlib.util
import re

from manhwa import doctor
from manhwa.config import ROOT


def _found(**ready):
    keys = ("gpu", "nvenc", "browser", "tts", "qwen", "edit", "sounds", "key")
    return {k: (ready.get(k, ready.get("all", False)), k, "") for k in keys}


def test_same_machine_gives_measured_total():
    rows = doctor.estimate(_found(all=True), 1.0, 1.0, 6.0)
    assert [how for _, _, how in rows] == ["ici"] * len(doctor.STEPS)
    assert sum(s for _, s, _ in rows) == sum(s for _, s, _, _, _ in doctor.STEPS)


def test_faster_card_shortens_gpu_steps_only():
    slow = dict((n, s) for n, s, _ in doctor.estimate(_found(all=True), 1.0, 1.0, 12.0))
    fast = dict((n, s) for n, s, _ in doctor.estimate(_found(all=True), 1.0, 2.0, 12.0))
    assert fast["Visages qui parlent (FLUX.2 klein, ≈ 22 visages)"] == slow["Visages qui parlent (FLUX.2 klein, ≈ 22 visages)"] / 2
    assert fast["Relecture, voix, sons, lieux (GPT ou Claude)"] == slow["Relecture, voix, sons, lieux (GPT ou Claude)"]


def test_no_card_falls_back_or_skips():
    rows = {n: (s, how) for n, s, how in doctor.estimate(_found(browser=True), 1.0, None, 0.0)}
    assert rows["Visages qui parlent (FLUX.2 klein, ≈ 22 visages)"] == (None, "sautée")
    assert rows["Relecture, voix, sons, lieux (GPT ou Claude)"] == (None, "sautée")  # pas de clé
    assert rows["Ce qui se passe dans les cases (Qwen3.5-2B)"] == (None, "sautée")    # ni modèle, ni GPT
    assert rows["Voix (Qwen3-TTS, timbre de chaque personnage, réécoute)"][1].startswith("voix de base")
    assert rows["Rendu de la vidéo (9 min)"] == (185, "rendu par le processeur")


def test_small_card_skips_big_models():
    rows = {n: how for n, _, how in doctor.estimate(_found(all=True), 1.0, 1.0, 4.0)}
    assert rows["Visages qui parlent (FLUX.2 klein, ≈ 22 visages)"] == "sautée"
    assert rows["Ce qui se passe dans les cases (Qwen3.5-2B)"] == "décrit par GPT"


def test_installer_files_agree():
    script = (ROOT / "install" / "install.ps1").read_bytes()
    assert script.startswith(b"\xef\xbb\xbf")  # Windows PowerShell 5.1 lit les accents grâce à ce début
    text = script.decode("utf-8-sig")
    for name in ("lock-main-gpu.txt", *(f"lock-{n}" for n in doctor.MODELS)):
        assert name.split("lock-")[1].replace(".txt", "") in text
    for lock in (ROOT / "install").glob("lock-*.txt"):
        pins = [l for l in lock.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
        assert pins and all(re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[^\s]+", l) for l in pins), lock.name
    for name in doctor.MODELS:
        assert "torch==2.6.0+cu124" in (ROOT / "install" / f"lock-{name}.txt").read_text(encoding="utf-8")
    assert "paddlepaddle-gpu==" in (ROOT / "install" / "lock-main-gpu.txt").read_text(encoding="utf-8")
    assert "install\\install.ps1" in (ROOT / "Installer.bat").read_text(encoding="utf-8")


def test_downloads_match_doctor_checks():
    spec = importlib.util.spec_from_file_location("download_models", ROOT / "install" / "download_models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.WANTED) == set(doctor.MODELS)
    for name, models in module.WANTED.items():
        assert [(folder, marker) for _, folder, marker, _ in models] == doctor.MODELS[name]


def test_machine_is_read():
    info = doctor.machine()
    assert info["threads"] >= 1 and info["free"] >= 0 and info["cpu"]
