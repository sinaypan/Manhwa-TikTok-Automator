from manhwa import captions, parts


def timeline_data(lengths, last_lines):
    t, tl, frames = 0.0, [], []
    for k, (d, text) in enumerate(zip(lengths, last_lines)):
        tl.append([f"f{k}.jpg", t, d])
        frames.append({"file": f"f{k}.jpg", "segments": [{"text": text}] if text else []})
        t += d
    return {"frames": frames, "steps": {"render": {"timeline": tl}}}


def test_parts_stay_between_60_and_90_s_and_end_on_suspense():
    data = timeline_data([10] * 30, ["OK."] * 30)
    data["frames"][6]["segments"] = [{"text": "WHAT?!"}]  # coupe à 70 s : une question
    data["frames"][14]["segments"] = [{"text": "IS THIS..."}]
    spans = parts.plan(data)
    assert all(60 <= b - a <= 90 for a, b in spans) and spans[0] == (0.0, 70) and spans[-1][1] == 300
    assert parts.plan(timeline_data([10] * 8, ["OK."] * 8)) == [(0.0, 80)]  # assez court : une seule partie


def test_karaoke_words_follow_the_voice():
    timed = captions.word_times("I DON'T KNOW. RUN!", 2.0)
    assert [w for w, _, _ in timed] == ["I", "DON'T", "KNOW.", "RUN!"] and timed[-1][2] == 2.0
    assert all(a < b for _, a, b in timed)
    heard = [["I", 0.0, 0.2], ["don't", 0.2, 0.5], ["know.", 0.5, 0.9], ["Run!", 1.2, 1.6]]
    assert captions.word_times("I DON'T KNOW. RUN!", 2.0, heard)[3][1:] == (1.2, 1.6)  # instants de Whisper
    evts = captions.events([("I DON'T KNOW. RUN!", 10.0, 2.0, None)])
    assert [e[2] for e in evts] == [["I", "DON'T", "KNOW."]] * 3 + [["RUN!"]]  # une phrase finie : nouveau groupe
    assert evts[0][0] == 10.0 and [e[3] for e in evts] == [0, 1, 2, 0]


def test_music_follows_the_mood_of_the_scene():
    from manhwa import moods

    fight = {"cats": {"slash": 0.8}}
    frames = [{"file": f"f{k}.jpg", "segments": []} for k in range(12)]
    scene = {f"f{k}.jpg": fight for k in (3, 5, 6)}
    raw = [moods.frame_mood(f, scene) for f in frames]
    assert raw.count("combat") == 3
    sm = moods.smooth(raw)
    assert sm[0] == "calm" and sm[4] == "combat" and sm[-1] == "calm"
    secs = moods.sections(sm, [10.0] * 12)
    assert [m for m, _, _ in secs] == ["calm", "combat", "calm"] and secs[-1][2] == 120.0
    assert moods.frame_mood({"file": "x", "segments": [{"emotion": "sad"}]}, {}) == "sad"


def test_hashtags_are_clean_and_the_part_label_is_drawn():
    from manhwa.config import load_config

    assert parts.clean_tags(["# manhwa Trends", "manhwa", "#Manhwa", "#family-loss", ""]) == ["#manhwaTrends", "#manhwa", "#familyloss"]
    card = parts._title_card("PART 2/6", 1080, load_config())
    assert card.shape[1] == 1080 and card.shape[2] == 4 and card[:, :, 3].max() > 0
