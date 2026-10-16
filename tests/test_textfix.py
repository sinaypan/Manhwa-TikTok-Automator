from manhwa import textfix
from manhwa.project import Chapter


def fix(text, protected=frozenset()):
    out, changes = textfix.fix_text(text, protected)
    return out, [c["sure"] for c in changes]


def test_glued_words_and_lost_letters_are_fixed_for_sure():
    assert fix("IDON'T THINK CAN KEEP THAT PROMISE.") == ("I DON'T THINK CAN KEEP THAT PROMISE.", [True])
    assert fix("....SOIT'S JUST MURDER.") == ("....SO IT'S JUST MURDER.", [True])
    assert fix("HE WASA MONSTER.") == ("HE WAS A MONSTER.", [True])
    assert fix("YOU WON'T BE ABLE TO MOVE ANYMORE. S E") == ("YOU WON'T BE ABLE TO MOVE ANYMORE.", [True])
    assert fix("I WILL GIvE YOU THE ANTIDOTE.")[0] == "I WILL GIVE YOU THE ANTIDOTE."


def test_one_letter_fixes_are_only_proposed():
    assert fix("YOU'RE AWAK") == ("YOU'RE AWAKE", [False])  # dernier mot : il a perdu sa fin
    assert fix("BUT TO THINK IT TAS SOME KID") == ("BUT TO THINK IT WAS SOME KID", [False])
    assert fix("Inner castle of Colden Jade Hall") == ("Inner castle of Golden Jade Hall", [False])


def test_real_words_names_and_contractions_are_kept():
    for text in ("YOU'RE BACK. GOOD WORK.", "I FOUND THE HERB,", "YIKES!", "HAH! YOU'RE RIGHT.", "WE'D TRUST YOU"):
        assert fix(text) == (text, [])
    assert fix("MOK GYEONGWOON, MUNNO!", {"MOK", "GYEONGWOON", "MUNNO"}) == ("MOK GYEONGWOON, MUNNO!", [])
    assert fix("The main character of Myst, Might, Mayhem", {"MYST"})[1] == []
    # un terme qui revient dans le chapitre n'est pas une erreur de lecture
    assert "QIGONG" in textfix.protected_words(texts=["HIS QIGONG", "THAT QIGONG IS STRONG"])


def test_gibberish_is_not_read():
    assert textfix.is_gibberish("a A A 9 CAE A A") and textfix.is_gibberish("AAA9CAEAAA")
    for text in ("I AM A MAN.", "WHAT?!", "HE IS 800 YEARS OLD.", "A..."):
        assert not textfix.is_gibberish(text)
    text, kind, _ = textfix.local_fix({"text": "a A A 9 CAE A A", "kind": "dialogue"}, set())
    assert kind == "noise"
    assert textfix.local_fix({"text": "KRR", "kind": "sfx"}, set()) == ("KRR", "sfx", [])


def test_run_textfix_writes_reviewable_proposals(tmp_path):
    ch = Chapter(tmp_path / "Série" / "chapter-001")
    (ch.root / "pages").mkdir(parents=True)
    data = ch.load()
    box = [0, 0, 10, 10]
    data["frames"] = [{"file": "f1.jpg", "crop": [0, 0, 100, 100], "bubbles": [
        {"text": "HE WASA MONSTER.", "kind": "dialogue", "box": box},
        {"text": "YOU'RE AWAK", "kind": "dialogue", "box": box},
        {"text": "GPT DID THIS ONE WASA", "kind": "dialogue", "box": box},
    ], "review": {"GPT DID THIS ONE WASA": {"text": "GPT DID THIS ONE WAS A", "state": {"text": "pending"}}}}]
    ch.save(data)
    assert textfix.run_textfix(ch) == 2
    reviews = ch.load()["frames"][0]["review"]
    assert reviews["HE WASA MONSTER."]["state"] == {"text": "accepted"}  # sûr : appliqué d'office
    assert reviews["YOU'RE AWAK"]["state"] == {"text": "pending"}  # à valider dans Relecture
    assert reviews["GPT DID THIS ONE WASA"].get("by") is None  # celle de GPT n'est pas touchée

    from manhwa import review

    assert [b["text"] for b in review.effective(ch.load()["frames"][0])][:2] == ["HE WAS A MONSTER.", "YOU'RE AWAK"]


def test_tone_from_punctuation_when_no_one_chose():
    from manhwa.emotion import guess
    from manhwa.review import effective

    assert [guess(t) for t in ("WHAT?!", "WHO?", "RUN!", "YOU WILL PAY FOR THIS!", "HAHAHA", "UGH...", "I SEE...", "OK.")] == \
        ["surprised", "surprised", "shouting", "excited", "mocking", "pain", "neutral", "neutral"]
    assert guess("I KEPT WALKING DOWN THAT ROAD...") == "thinking"
    frame = {"bubbles": [{"text": "WHAT?!", "kind": "dialogue"}, {"text": "WHO?", "kind": "dialogue"}],
             "review": {"WHO?": {"emotion": "cold"}}}
    assert [b["emotion"] for b in effective(frame)] == ["surprised", "cold"]  # GPT (ou toi) passe devant
