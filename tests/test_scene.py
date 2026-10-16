import numpy as np

from manhwa import scene, sfx


def test_tall_panels_are_cut_in_overlapping_squares():
    assert len(scene.tiles(np.zeros((300, 300, 3), np.uint8))) == 1
    tall = scene.tiles(np.zeros((1200, 300, 3), np.uint8))
    assert 2 <= len(tall) <= 6 and all(t.shape[:2] == (300, 300) for t in tall)
    assert len(scene.tiles(np.zeros((20000, 300, 3), np.uint8))) == 6
    wide = scene.tiles(np.zeros((200, 700, 3), np.uint8))
    assert all(t.shape[:2] == (200, 200) for t in wide)


def test_recommendations_from_the_image_and_gpt():
    fire = {"cats": {"fire": 0.6, "none": 0.3, "wood": 0.2, "cloth": 0.1}, "seen": {"du feu": 0.6, "du bois": 0.2}}
    assert scene.recommend(fire) == (["fire", "wood", "cloth"], "fire")
    # pas sûr (sous SURE, ou moins que « rien ») : proposé, mais pas mis d'office
    assert scene.recommend({"cats": {"slash": 0.3, "none": 0.6}}) == (["slash"], None)
    assert scene.recommend({"cats": {"slash": 0.5, "none": 0.7}}) == (["slash"], None)
    # des robes partout : jamais mis d'office ; GPT passe devant
    assert scene.recommend({"cats": {"cloth": 0.9, "none": 0.1}})[1] is None
    assert scene.recommend(fire, gpt="door") == (["door", "fire", "wood"], "door")
    assert scene.recommend(None) == ([], None)


def test_sound_items_carry_what_the_panel_shows():
    data = {"frames": [
        {"file": "f1.jpg", "crop": [0, 0, 10, 10], "bubbles": [{"text": "BAM", "kind": "sfx", "box": [0, 0, 5, 5]}]},
        {"file": "f2.jpg", "crop": [0, 10, 10, 10], "bubbles": []},
    ]}
    seen = {"f1.jpg": {"cats": {"punch": 0.7, "none": 0.2}, "seen": {"un coup de poing": 0.7}},
            "f2.jpg": {"cats": {"none": 0.9}, "seen": {}}}
    spot = sfx.spots(data, seen)[0]
    assert spot["recs"] == ["punch"] and spot["proposed"] == "punch" and spot["seen"] == ["un coup de poing"]
    action = next(a for a in sfx.silent_frames(data, seen) if a["frame"] == "f2.jpg")
    assert action["recs"] == [] and action["proposed"] == sfx.NONE
    assert {"fire", "wind"} <= set(sfx.CATEGORIES)
