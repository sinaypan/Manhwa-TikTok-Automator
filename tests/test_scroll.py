import numpy as np

from manhwa import scroll


def panels():
    a = scroll.Panel([0, 0, 400, 300], 1.0, 0.0, 2.0)            # petite case
    b = scroll.Panel([100, 400, 200, 1500], 1.0, 2.0, 6.0)       # case haute et étroite
    b.bubbles = [(1.0, 700.0), (4.0, 1600.0)]
    return [a, b]


def test_camera_glides_to_each_case_then_stays():
    keys = scroll.camera_keys(panels(), 400, 600, 3000)
    cam = scroll.camera_path(keys)
    assert cam(0.0)[1] == cam(1.9)[1]                      # posée sur la première case
    assert cam(2.0 + scroll.GLIDE + 0.01)[1] > cam(1.9)[1]  # elle est descendue vers la suivante
    assert all(0 <= k[1][1] <= 3000 for k in keys)


def test_tall_case_follows_its_bubbles():
    keys = scroll.camera_keys(panels(), 400, 600, 3000)
    ys = [k[1][1] for k in keys if k[0] >= 2.0]
    assert ys == sorted(ys) and len(ys) == 3  # son haut, puis la bulle de chaque réplique


def test_fit_zooms_so_the_case_fills_the_width():
    keys = scroll.camera_keys(panels(), 400, 600, 3000, fit=True)
    zooms = [k[1][2] for k in keys]
    assert zooms[0] == 1.0                     # 400 de large : déjà toute la largeur
    assert abs(zooms[-1] - 400 / (200 * (1 + 2 * scroll.FIT_MARGIN))) < 1e-6  # 200 de large : ≈ ×1,85 (marge comprise)
    assert keys[-1][1][0] == 200               # centrée sur la case étroite


def test_scroll_clip_keeps_the_video_size():
    strip = (np.random.default_rng(0).random((3000, 400, 3)) * 255).astype(np.uint8)
    clip = scroll.scroll_clip(strip, panels(), 400, 600, 8.0, fit=True)
    for t in (0.0, 2.3, 5.0, 7.9):
        assert clip.get_frame(t).shape == (600, 400, 3)
