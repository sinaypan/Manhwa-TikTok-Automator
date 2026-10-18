"""Les filigranes du site : appris de ceux que l'OCR a lus, retrouvés ailleurs, effacés (watermark.py)."""
import json

import cv2
import numpy as np

from manhwa import watermark as wm

W, H = 800, 9000
SPOTS = [(60, 700), (500, 2100), (120, 3600), (430, 5000), (40, 6400), (520, 7900)]  # le coin du bandeau
TEXT_AT = (70, 12)  # où commence le texte dans le bandeau


def page():
    """Une planche dessinée (dégradés, traits, bruit) avec le même filigrane semi-transparent posé six fois."""
    rng = np.random.default_rng(3)
    img = np.zeros((H, W, 3), np.uint8)
    for y in range(0, H, 300):
        img[y:y + 300] = rng.integers(40, 220, 3)
    img = cv2.GaussianBlur(img, (0, 0), 25)
    for _ in range(400):
        p = rng.integers(0, [W, H], 2)
        q = p + rng.integers(-150, 150, 2)
        cv2.line(img, tuple(int(v) for v in p), tuple(int(v) for v in q), tuple(int(v) for v in rng.integers(0, 255, 3)), 2)
    img = np.clip(img.astype(np.int16) + rng.integers(-12, 12, img.shape), 0, 255).astype(np.uint8)
    clean = img.copy()
    for x, y in SPOTS:
        band = img[y:y + 50, x:x + 260].astype(np.float32)
        img[y:y + 50, x:x + 260] = (0.5 * band + 0.5 * 90).astype(np.uint8)  # bandeau gris, à moitié transparent
        cv2.circle(img, (x + 30, y + 25), 16, (150, 60, 160), -1)                 # le logo
        cv2.putText(img, "MYSITE.COM", (x + TEXT_AT[0], y + 38), cv2.FONT_HERSHEY_DUPLEX, 0.9, (200, 120, 210), 2)
    return img, clean


def ocr_seeds(n=4):
    """Ce que l'OCR aurait lu : le texte de n filigranes seulement (les autres sont ratés)."""
    return [(x + TEXT_AT[0], y + TEXT_AT[1], 180, 30, "MYSITE.COM") for x, y in SPOTS[:n]]


def test_template_covers_the_whole_banner_not_just_the_letters():
    img, _ = page()
    t = wm.learn(img, ocr_seeds())
    assert t is not None and len(t["at"]) == 4
    bx, by, bw, bh = t["box"]
    mask = t["mask"] > 0
    assert mask[by:by + bh, bx:bx + bw].mean() > 0.8         # les lettres
    assert mask[:, :bx].any()                                 # et le logo, à gauche du texte
    assert mask.mean() < 0.9                                  # pas toute la fenêtre


def test_finds_the_ones_ocr_missed_without_false_alarms():
    img, _ = page()
    t = wm.learn(img, ocr_seeds())
    found = wm.find(img, t)
    ys = sorted(y + int(t["box"][1]) for _, y, _ in found)
    want = sorted(y + TEXT_AT[1] for _, y in SPOTS)
    assert len(found) == len(SPOTS)
    assert all(abs(a - b) <= 4 for a, b in zip(ys, want))


def test_too_few_seeds_learns_nothing():
    img, _ = page()
    assert wm.learn(img, ocr_seeds(2)) is None


def test_erase_repaints_the_banner(monkeypatch):
    img, clean = page()
    t = wm.learn(img, ocr_seeds())
    monkeypatch.setattr(wm, "inpaint", lambda im, hole: cv2.inpaint(im, (hole > 0).astype(np.uint8), 5, cv2.INPAINT_TELEA))
    x, y, _ = wm.find(img, t)[-1]
    px, py, patch = wm.erase(img, x, y, t["mask"])
    out = img.copy()
    out[py:py + patch.shape[0], px:px + patch.shape[1]] = patch
    sx, sy = SPOTS[-1]
    before = np.abs(img[sy:sy + 50, sx:sx + 260].astype(int) - clean[sy:sy + 50, sx:sx + 260]).mean()
    after = np.abs(out[sy:sy + 50, sx:sx + 260].astype(int) - clean[sy:sy + 50, sx:sx + 260]).mean()
    assert after < before / 2


def test_clean_pastes_patches_only_for_the_same_pages(tmp_path, monkeypatch):
    class Chapter:
        root = tmp_path

    folder = wm.folder(Chapter)
    folder.mkdir(parents=True)
    cv2.imwrite(str(folder / "000.png"), np.full((10, 20, 3), 255, np.uint8))
    (folder / "index.json").write_text(json.dumps({"pages": "abc", "patches": [{"file": "000.png", "x": 5, "y": 7}]}))
    cfg = {"slicer": {"max_src_width": 800}, "watermark": {"remove": True}}
    strip = np.zeros((50, 50, 3), np.uint8)
    monkeypatch.setattr("manhwa.panels.pages_key", lambda chapter, w: "abc")
    out = wm.clean(Chapter, strip, cfg)
    assert out[7:17, 5:25].min() == 255 and out[:7].max() == 0 and strip.max() == 0
    monkeypatch.setattr("manhwa.panels.pages_key", lambda chapter, w: "other pages")
    assert wm.clean(Chapter, strip, cfg).max() == 0
    assert wm.clean(Chapter, strip, {**cfg, "watermark": {"remove": False}}).max() == 0


def test_site_ad_panels_are_spotted():
    ad = {"crop": [0, 0, 800, 434], "bubbles": [{"kind": "credit", "box": [176, 116, 459, 201], "text": "READ AT FOR THE FASTEST RELEASES"}]}
    story = {"crop": [0, 0, 800, 434], "bubbles": [{"kind": "credit", "box": [176, 116, 459, 201], "text": "READ AT"},
                                                  {"kind": "dialogue", "box": [10, 10, 100, 40], "text": "RUN!"}]}
    small = {"crop": [0, 0, 800, 2000], "bubbles": [{"kind": "credit", "box": [10, 10, 120, 20], "text": "discord"}]}
    assert wm.is_ad(ad) and not wm.is_ad(story) and not wm.is_ad(small)
