import numpy as np

from manhwa import motion, qwen_voice


def test_qwen_length_limit_follows_the_longest_line():
    short = qwen_voice.max_tokens([{"text": "Huh?"}])
    long = qwen_voice.max_tokens([{"text": "Huh?"}, {"text": "x" * 120}])
    assert short == int(qwen_voice.CODEC_HZ * (3 + 4 / 6))  # 3 s de marge + 4 caractères
    assert long == qwen_voice.CODEC_HZ * (3 + 20)  # 6 caractères par seconde au plus lent
    assert long < 8192  # bien sous la limite du modèle (≈ 11 min)


def test_depth_camera_at_quarter_size_moves_like_before():
    # l'ancien calcul (pleine taille) et le nouveau (au quart, agrandi) donnent la même image
    import cv2

    h, w = 192, 108
    rng = np.random.default_rng(0)
    img = cv2.GaussianBlur((rng.random((h, w, 3)) * 255).astype(np.uint8), (0, 0), 2)
    depth = cv2.GaussianBlur(rng.random((h, w)).astype(np.float32), (0, 0), 20)
    clip = motion.depth_zoom_clip(img, depth, 2.0, 0.04)
    frame = clip.get_frame(1.5)
    assert frame.shape == img.shape
    # même chose avec un relief déjà au quart (gardé sur le disque)
    small = cv2.resize(depth, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    again = motion.depth_zoom_clip(img, small, 2.0, 0.04).get_frame(1.5)
    assert np.abs(frame.astype(int) - again.astype(int)).mean() < 0.5


def test_depth_is_kept_on_disk(tmp_path, monkeypatch):
    calls = []

    def fake(rgb, rect, boxes, crop_w):
        calls.append(1)
        return np.full(rgb.shape[:2], 0.5, np.float32)

    monkeypatch.setattr(motion, "depth_map", fake)
    img = np.zeros((64, 36, 3), np.uint8)
    a = motion.cached_depth(tmp_path, img, [0, 0, 36, 64], [])
    b = motion.cached_depth(tmp_path, img, [0, 0, 36, 64], [])
    assert len(calls) == 1 and a.shape == (16, 9) and np.allclose(a, b)
    motion.cached_depth(tmp_path, img, [0, 0, 36, 64], [[1, 1, 5, 5]])  # autres bulles : refait
    assert len(calls) == 2
