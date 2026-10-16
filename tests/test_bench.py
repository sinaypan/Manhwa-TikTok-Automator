import numpy as np
import pytest

from manhwa import bench, cast
from manhwa.images import write_jpeg
from manhwa.project import Chapter


def bubble(text, kind="dialogue", x=10):
    return {"text": text, "kind": kind, "conf": 0.9, "box": [x, 10, 100, 40]}


@pytest.fixture
def chapter(tmp_path):
    ch = Chapter(tmp_path / "Série" / "chapter-001")
    (ch.root / "pages").mkdir(parents=True)
    write_jpeg(ch.root / "pages" / "001.jpg", np.full((600, 800, 3), 200, np.uint8))
    crew = cast.load_cast(ch)
    hero, thug = cast.new_character(crew), cast.new_character(crew)
    cast.save_cast(ch, crew)
    data = ch.load()
    data["frames"] = [
        {"file": "f1.jpg", "crop": [0, 0, 400, 300], "bubbles": [bubble("IDON'T KNOW."), bubble("AAA9CAEAAA")],
         "speakers": {"IDON'T KNOW.": hero},
         "review": {"IDON'T KNOW.": {"text": "I DON'T KNOW.", "kind": "dialogue", "emotion": "sad",
                                     "state": {"text": "accepted"}},
                    "AAA9CAEAAA": {"text": "AAA9CAEAAA", "kind": "noise", "emotion": "neutral",
                                   "state": {"kind": "accepted"}}},
         "sounds": {}},
        {"file": "f2.jpg", "crop": [0, 300, 400, 300], "bubbles": [bubble("RUN!", x=300)], "speakers": {"RUN!": thug},
         "action_sound": {}},
    ]
    # le visage du héros près de la 1re bulle, celui du brigand près de la 2e
    data["faces"] = {"key": "k", "list": [
        {"id": "a", "frame": "f1.jpg", "box": [20, 60, 40, 40], "char": hero},
        {"id": "b", "frame": "f2.jpg", "box": [20, 60, 40, 40], "char": hero},
        {"id": "c", "frame": "f2.jpg", "box": [320, 60, 40, 40], "char": thug},
        {"id": "d", "frame": "f2.jpg", "box": [200, 200, 40, 40], "char": None, "not_face": True},
    ]}
    ch.save(data)
    v = np.eye(4, dtype=np.float32)
    v[1] = v[0]  # a et b : la même tête ; c et d : différentes
    cast.vectors_path(ch).parent.mkdir(parents=True, exist_ok=True)
    np.savez(cast.vectors_path(ch), ids=np.array(["a", "b", "c", "d"]), vecs=v)
    return ch, hero, thug


def test_freeze_then_score_every_step(chapter):
    ch, hero, thug = chapter
    kept = bench.freeze(ch)
    assert kept["bulles"] == 3 and kept["qui parle"] == 2 and kept["visages"] == 4

    report = bench.run_bench(ch)
    k = report["kinds"]
    assert (k["erreurs"], k["bulles"]) == (0, 3)  # le charabia est repéré (textfix), pas lu
    raw, _ = bench.score_kinds(ch.load(), bench.load_gold(ch), predict=lambda frame, b: b["kind"])
    assert (raw["erreurs"], raw["erreurs qui s'entendent"]) == (1, 1)  # les seules règles de lecture le liraient
    t = report["text"]
    assert (t["répliques"], t["à corriger"], t["corrigées"], t["abîmées"]) == (2, 1, 1, 0)  # « IDON'T » recollé
    s = report["speakers"]
    assert s["répliques"] == 2 and s["justes"] == 1.0  # chaque bulle à côté du bon visage
    f = report["faces"]
    assert f["visages"] == 4 and f["paires retrouvées"] == 1.0 and f["à déplacer"] == 1  # c tout seul : à ranger
    assert report["emotion"]["justes"] == 0.0  # sans GPT tout est neutre, la référence dit « triste »
    assert len(bench.previous_runs(ch)) == 1

    # un module qui corrige le texte : il se mesure sans toucher au chapitre
    data, gold = ch.load(), bench.load_gold(ch)
    fixed, _ = bench.score_text(data, gold, predict=lambda frame, b: b["text"].replace("IDON'T", "I DON'T"))
    assert (fixed["corrigées"], fixed["abîmées"], fixed["répliques exactes"]) == (1, 0, 1.0)
    broke, _ = bench.score_text(data, gold, predict=lambda frame, b: b["text"].lower() + " X")
    assert broke["abîmées"] == 1


def test_a_changed_bubble_is_left_out(chapter):
    ch, _, _ = chapter
    bench.freeze(ch)
    data = ch.load()
    data["frames"][0]["bubbles"][0]["text"] = "I DONT KNOW"  # relu autrement depuis : plus comparable
    report, _ = bench.score_text(data, bench.load_gold(ch))
    assert report["répliques"] == 1


def test_bench_needs_a_reference(chapter):
    ch, _, _ = chapter
    with pytest.raises(RuntimeError):
        bench.run_bench(ch)
