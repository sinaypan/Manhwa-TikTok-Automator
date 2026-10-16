from manhwa import listen
from manhwa.project import Chapter


def test_difference_and_what_gets_flagged():
    assert listen.difference("YOU'RE AWAK", "You're a W.") == 0.5
    assert listen.difference("DIE, YOU SWINES!", "Die you swines.") == 0.0
    seg = lambda text, wer: {"text": text, "wer": wer}
    assert listen.flagged(seg("HE WASA MONSTER.", 0.33))
    assert not listen.flagged(seg("KUKUK. SEEMS LIKE YOU'RE JUST AS SURPRISED.", 0.14))  # sous le seuil
    assert not listen.flagged(seg("PHEW...", 1.0))  # un vrai mot seul : Whisper entend « fuel »
    assert listen.flagged(seg("PeDOCe", 1.0))  # un mot qui n'existe pas


def test_checks_list_what_is_wrong_in_the_video(tmp_path):
    ch = Chapter(tmp_path / "Série" / "chapter-001")
    (ch.root / "audio").mkdir(parents=True)
    (ch.root / "audio" / "a.mp3").write_bytes(b"x")
    data = ch.load()
    data["frames"] = [
        {"file": "f1.jpg", "segments": [{"text": "HE WASA MONSTER.", "audio": "audio/a.mp3", "heard": "He was a monster.", "wer": 0.33}]},
        {"file": "f2.jpg", "segments": [{"text": "WHERE IS IT?", "audio": "audio/missing.mp3"}]},
        {"file": "f3.jpg", "segments": []},
    ]
    data["steps"]["render"] = {"timeline": [["f1.jpg", 0.0, 3.0], ["f2.jpg", 3.0, 2.0], ["f3.jpg", 5.0, 0.3]]}
    kinds = [(c["frame"], c["kind"]) for c in listen.checks(ch, data)]
    assert kinds == [("f1.jpg", "heard"), ("f2.jpg", "missing"), ("f3.jpg", "short")]
