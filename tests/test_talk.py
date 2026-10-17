import numpy as np

from manhwa import talk


def test_mouth_beats_with_each_syllable():
    # trois syllabes fortes séparées par des creux, puis un silence
    env = np.concatenate([np.tile(np.r_[np.linspace(0.2, 1, 6), np.linspace(1, 0.2, 6)], 3), np.zeros(20)]).astype(np.float32)
    states = [talk.syllable(env, i) for i in range(0, len(env), talk.ENV_FPS // talk.FLAP)]
    changes = sum(a != b for a, b in zip(states, states[1:]))
    assert talk.MOUTHS[2] in states and talk.MOUTHS[0] in states
    assert changes >= 4  # elle s'ouvre et se ferme, pas une seule ouverture continue
    assert states[-1] == talk.MOUTHS[0]  # fermée dans le silence


def test_quiet_voice_never_opens_wide():
    env = np.tile(np.r_[np.linspace(0.13, 0.4, 6), np.linspace(0.4, 0.13, 6)], 4).astype(np.float32)
    assert talk.MOUTHS[2] not in {talk.syllable(env, i) for i in range(len(env))}


def test_blink_is_short_and_regular():
    times = np.arange(0, 20, 1 / 24)
    closed = [talk.blink_at(t, seed=3) for t in times]
    starts = [t for t, a, b in zip(times[1:], closed, closed[1:]) if b and not a]
    assert 3 <= len(starts) <= 7
    assert sum(closed) / 24 < 0.25 * 8


def test_talkers_keep_the_speaker_largest_face():
    data = {
        "frames": [{"file": "a.jpg", "segments": [{"speaker": "c1"}]}, {"file": "b.jpg", "segments": [{"speaker": "c2"}]}],
        "faces": {"list": [
            {"id": "f0001", "frame": "a.jpg", "box": [0, 0, 150, 150], "char": "c1"},
            {"id": "f0002", "frame": "a.jpg", "box": [0, 0, 300, 300], "char": "c1"},
            {"id": "f0003", "frame": "a.jpg", "box": [0, 0, 300, 300], "char": "c3"},  # ne parle pas ici
            {"id": "f0004", "frame": "b.jpg", "box": [0, 0, 60, 60], "char": "c2"},  # trop petit
            {"id": "f0005", "frame": "b.jpg", "box": [0, 0, 200, 200], "char": "c2", "not_face": True},
        ]},
    }
    assert [f["id"] for f in talk.talkers(data)] == ["f0002"]


def test_zones_follow_what_the_drawing_changed():
    rng = np.random.default_rng(0)
    original = (rng.random((256, 256, 3)) * 30 + 150).astype(np.uint8)
    drawn = {}
    for state, (y, h) in {"mouth_closed": (180, 6), "mouth_half": (178, 14), "mouth_open": (175, 24)}.items():
        im = original.copy()
        im[y:y + h, 100:156] = 20  # la bouche, redessinée
        drawn[state] = im
    eyes = original.copy()
    eyes[90:100, 60:100] = 20
    eyes[90:100, 156:196] = 20
    drawn["eyes_closed"] = eyes
    mouth, eye = talk.zones(original, drawn)
    assert mouth[185, 128] > 200 and mouth[40, 128] == 0 and mouth[95, 80] < 30
    assert eye[95, 80] > 200 and eye[95, 176] > 200 and eye[185, 128] == 0
