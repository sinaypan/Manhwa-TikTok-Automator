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


def test_enter_rules_cut_on_hits_and_fade_between_places():
    fxs = [{}, {"shake": 30}, {}, {"shake": 9}, {}]
    places = [{"from": 1}, {"from": 1}, {"from": 3}, {"from": 3}, None]
    assert scroll.enter_rules(fxs, places) == ["glide", "cut", "fade", "glide", "glide"]


def test_cut_arrives_at_once():
    a, b = panels()
    b.enter = "cut"
    keys = scroll.camera_keys([a, b], 400, 600, 3000)
    cam = scroll.camera_path(keys)
    first_b = next(k for k in keys if k[0] == b.start)
    assert abs(cam(b.start + 0.01)[1] - first_b[1][1]) < 1e-6  # déjà là, sans glisser


def test_gpu_frames_match_the_processor():
    import pytest

    from manhwa import scroll_gpu

    if not scroll_gpu.available():
        pytest.skip("pas de carte graphique")
    import cv2

    strip = cv2.GaussianBlur((np.random.default_rng(0).random((3000, 400, 3)) * 255).astype(np.uint8), (0, 0), 3)
    ps = panels()
    ps[1].depth = cv2.GaussianBlur(np.random.default_rng(1).random((375, 50)).astype(np.float32), (0, 0), 8)
    ps[1].fx = {"shake": 30, "punch": 0.08, "flash": 0.3}
    ps[1].enter = "cut"
    cpu = scroll.scroll_clip(strip, ps, 400, 600, 8.0, fit=True)
    gpu = scroll_gpu.scroll_clip_gpu(strip, panels_with(ps), 400, 600, 8.0, fit=True)
    for t in (0.5, 2.06, 2.3, 5.0, 7.9):
        a, b = cpu.get_frame(t), gpu.get_frame(t)
        assert b.shape == a.shape and cv2.PSNR(a, b) > 30, t


def panels_with(ps):
    # les mêmes cases, sans ce que le calcul du processeur a gardé en route
    out = []
    for p in ps:
        q = scroll.Panel([0, 0, 1, 1], 1.0, p.start, p.duration)
        q.__dict__.update({k: v for k, v in p.__dict__.items() if not k.startswith("_")})
        out.append(q)
    return out
