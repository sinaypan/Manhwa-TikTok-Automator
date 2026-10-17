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
    # le premier proposé est mis d'office, même peu sûr ; trop faible (< PROPOSE) : rien
    assert scene.recommend({"cats": {"slash": 0.3, "none": 0.6}}) == (["slash"], "slash")
    assert scene.recommend({"cats": {"cloth": 0.9, "none": 0.1}}) == (["cloth"], "cloth")
    assert scene.recommend({"cats": {"slash": 0.02, "none": 0.9}}) == ([], None)
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


def test_the_video_takes_the_proposal_until_you_choose():
    data = {"frames": [
        {"file": "f1.jpg", "crop": [0, 0, 10, 10], "bubbles": []},
        {"file": "f2.jpg", "crop": [0, 10, 10, 10], "bubbles": [], "action_sound": {"chosen": "none"}},
    ]}
    seen = {"f1.jpg": {"cats": {"fire": 0.6}}, "f2.jpg": {"cats": {"door": 0.8}}}
    assert sfx.frame_sounds(data, seen) == {}  # sans [auto] : seulement tes choix
    auto = sfx.frame_sounds(data, seen, auto=True)
    assert list(auto) == ["f1.jpg"] and "fire" in auto["f1.jpg"][0][0].replace("\\", "/")  # « aucun son » choisi : respecté


def test_drawn_english_sound_effects_are_recognised():
    assert [sfx.onomatopoeia(t) for t in ("BAM!", "WHOOOOSH", "CLANG CLANG", "THUD...", "LA", "9F", "")] == \
        ["punch", "whoosh", "metal", "impact", None, None, None]
    data = {"frames": [{"file": "f1.jpg", "crop": [0, 0, 10, 10], "bubbles": [{"text": "SHIIING", "kind": "sfx", "box": [0, 0, 5, 5]}]}]}
    assert sfx.spots(data, {"f1.jpg": {"cats": {"punch": 0.7}}})[0]["recs"][:2] == ["blade_draw", "punch"]
    assert [sfx.onomatopoeia(t) for t in ("SPLAT", "쾅!!", "덜컹")] == ["blood", "slam", "wood"]


def test_gpt_choice_from_what_happens_comes_first_and_can_be_two_sounds():
    fire = {"cats": {"fire": 0.6, "wood": 0.2}}
    assert scene.recommend(fire, ai={"sounds": ["slam", "blood"]}) == (["slam", "blood", "fire", "wood"], "slam+blood")
    assert scene.recommend(fire, ai={"sounds": []}) == (["fire", "wood"], "none")
    data = {"frames": [{"file": "f1.jpg", "crop": [0, 0, 10, 10], "bubbles": []}]}
    seen = {"f1.jpg": {"cats": {}, "ai": {"frame:f1.jpg": {"what": "Il est projeté contre un mur", "sounds": ["slam", "blood"], "why": "choc et sang"}}}}
    item = sfx.silent_frames(data, seen)[0]
    assert (item["proposed"], item["what"], item["why"]) == ("slam+blood", "Il est projeté contre un mur", "choc et sang")
    sfx.set_sounds(data, [{"key": "frame:f1.jpg", "sound": ["punch", "blood"]}])
    assert sfx.silent_frames(data, seen)[0]["sound"] == "punch+blood"
    assert sfx.layers("punch+blood") == ["punch", "blood"] and sfx.layers("none") == []
    import pytest
    with pytest.raises(ValueError):
        sfx.set_sounds(data, [{"key": "frame:f1.jpg", "sound": "punch+laser"}])


def test_the_image_shakes_and_flashes_with_the_hits():
    from manhwa import motion

    assert motion.effects([]) == {}
    assert motion.effects([(["footsteps"], 2)]) == {}  # des pas : rien ne bouge
    soft = motion.effects([(["punch"], 1)])
    hard = motion.effects([(["slam", "blood"], 3)])
    assert hard["shake"] > motion.effects([(["punch"], 2)])["shake"] and "flash" in hard and "flash" not in soft
    assert motion.offset(0.0, 10) == (0.0, 0.0) and motion.offset(2.0, 10) == (0.0, 0.0)
    assert abs(motion.offset(0.07, 10)[0]) > 0 and motion.flash_at(0.06, 0.5) > 0.4
    data = {"frames": [{"file": "f1.jpg", "crop": [0, 0, 10, 10], "bubbles": [], "action_sound": {"chosen": "slam+blood"}}]}
    seen = {"f1.jpg": {"ai": {"frame:f1.jpg": {"sounds": ["slam"], "strength": 3}}}}
    assert sfx.frame_hits(data, seen) == {"f1.jpg": [(["slam", "blood"], 3)]}


def test_takes_are_cut_on_silences_and_levelled():
    import numpy as np

    from manhwa import soundbank

    rate = soundbank.RATE
    hit = np.sin(np.linspace(0, 400, int(0.3 * rate))) * 0.5
    y = np.concatenate([hit, np.zeros(int(0.5 * rate)), hit * 0.1, np.zeros(int(0.5 * rate))]).astype(np.float32)
    parts = soundbank.takes(y)
    assert len(parts) == 2 and all(0.25 < len(p) / rate < 0.5 for p in parts)
    a, b = soundbank._level(parts[0].copy()), soundbank._level(parts[1].copy())
    assert abs(np.sqrt(np.mean(a[: len(a) // 2] ** 2)) - np.sqrt(np.mean(b[: len(b) // 2] ** 2))) < 0.02  # même volume
    assert sfx.gains("punch+blood", 3)[0] > sfx.gains("punch", 1)[0] and sfx.gains("footsteps", 2)[0] < 1


def test_sonniss_picks_useful_sounds_and_ambiences_by_name():
    from manhwa import sonniss

    z = "https://mirror/x.zip"
    files = [(z, "SoundBits -  Just Gore | Add On/Splat_01.wav", 300_000),
             (z, "Pack/Punch_Heavy_03.wav", 200_000), (z, "Pack/Punch_Heavy_03.wav", 200_000),  # en double
             (z, "Pack/Car Engine Idle.wav", 100_000),  # rien d'utile
             (z, "Pack/Wind, Ext, Gust, Grasslands.wav", 40_000_000),  # long, mais utile (son début)
             (z, "Amb/Forest quiet birds morning.wav", 20_000_000), (z, "Amb/City traffic forest.wav", 20_000_000),
             (z, "Amb/Cave drips loop.wav", 1_000_000)]  # trop court pour une ambiance
    p = sonniss.choose(files)
    names = [n.rsplit("/", 1)[-1] for _, n, _ in p["sfx"]]
    assert names == ["Splat_01.wav", "Punch_Heavy_03.wav", "Wind, Ext, Gust, Grasslands.wav"]
    # une longue prise de vent sert aussi d'ambiance ; la ville et la prise trop courte, non
    assert [n.rsplit("/", 1)[-1] for _, n, _ in p["ambience"]] == ["Forest quiet birds morning.wav",
                                                                  "Wind, Ext, Gust, Grasslands.wav"]
