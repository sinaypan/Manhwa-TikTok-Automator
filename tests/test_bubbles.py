from manhwa.bubbles import clean, spoken_text, to_bubbles
from manhwa.ocr_bench import match

W = 800


def line(text, x, y, w=200, h=40, conf=0.99):
    return {"text": text, "conf": conf, "box": [x, y, w, h]}


def kinds(bubbles):
    return [(b["kind"], b["text"]) for b in bubbles]


def test_words_on_one_row_are_read_left_to_right():
    # un moteur qui rend un mot à la fois, « FEEL » 1 px plus bas que « ANY »
    lines = [line("DON'T", 10, 0, 240, 55), line("FEEL", 249, 1, 150, 51), line("ANY", 414, 0, 140, 58),
             line("SADNESS", 16, 67, 280, 52), line("EITHER", 308, 68, 227, 52)]
    assert spoken_text(to_bubbles(lines, W)) == "DON'T FEEL ANY SADNESS EITHER"


def test_spaced_words_on_one_row_stay_together():
    # « HOW TERRIBLE OF A HUMAN AM I...? » : le « I...? » un peu plus loin, lu avec hésitation,
    # ne doit pas finir seul (et jeté comme bruit)
    lines = [line("HOW TERRIBLE OF", 0, 0, 380, 60, 0.99), line("A HUMAN AM", 30, 70, 300, 60, 0.98),
             line("I...?", 370, 72, 70, 58, 0.55)]
    assert spoken_text(to_bubbles(lines, W)) == "HOW TERRIBLE OF A HUMAN AM I...?"
    # « THAT IS HOW HE DIED. » rendu mot par mot, avec des mots mal assurés au milieu
    lines = [line("THAT", 1, 1, 167, 51), line("IS", 190, 10, 50, 40, 0.6), line("HOW HE", 260, 8, 230, 44, 0.65),
             line("DIED.", 536, 0, 142, 52)]
    assert spoken_text(to_bubbles(lines, W)) == "THAT IS HOW HE DIED."


def test_two_bubbles_side_by_side_stay_separate():
    # deux bulles à la même hauteur mais loin l'une de l'autre
    lines = [line("YES,", 40, 100, 120, 40), line("NO.", 600, 100, 100, 40)]
    assert [b["text"] for b in to_bubbles(lines, W)] == ["YES,", "NO."]


def test_two_bubbles_are_separate_and_in_reading_order():
    lines = [line("I LOOKED IN THE", 300, 340), line("EASTERN PARTS", 300, 385), line("YOU'RE BACK.", 60, 100),
             line("GOOD WORK.", 60, 145)]
    bubbles = to_bubbles(lines, W)
    assert [b["text"] for b in bubbles] == ["YOU'RE BACK. GOOD WORK.", "I LOOKED IN THE EASTERN PARTS"]


def test_noise_is_not_read():
    lines = [
        line("ASURASCANS.COM", 600, 1300, 170, 30),         # filigrane
        line("와드득", 100, 100, 270, 280, 0.9),            # SFX coréen
        line("Lyu", 528, 68, 272, 285, 0.49),               # SFX coréen lu comme des lettres
        line("...", 300, 900, 40, 20),                      # bulle de ponctuation
        line("IF YOU WANT TO DO IT,", 200, 500),
    ]
    bubbles = to_bubbles(lines, W)
    assert spoken_text(bubbles) == "IF YOU WANT TO DO IT,"
    assert {k for k, _ in kinds(bubbles)} == {"watermark", "sfx", "silent", "dialogue"}


def test_credits_page_split_in_words_is_recognised():
    lines = [line("READ", 338, 115, 88, 45), line("AT", 423, 120, 36, 36), line("ASURASCANS.COM", 176, 169, 456, 79),
             line("FOR", 216, 279, 62, 38), line("THE", 262, 279, 68, 37), line("FASTEST", 332, 279, 111, 38),
             line("RELEASES", 451, 279, 134, 38)]
    assert spoken_text(to_bubbles(lines, W)) is None


def test_big_clean_text_stays_dialogue_but_big_shaky_word_is_sfx():
    assert spoken_text(to_bubbles([line("A WISE CHOICE.", 250, 90, 300, 140, 1.0)], W)) == "A WISE CHOICE."
    assert kinds(to_bubbles([line("KRAAAK", 100, 90, 500, 200, 0.95)], W)) == [("sfx", "KRAAAK")]
    assert kinds(to_bubbles([line("BAM!", 100, 90, 120, 40)], W)) == [("sfx", "BAM!")]


def test_title_and_numbers():
    bubbles = to_bubbles([line("1", 380, 0, 40, 60), line("Prologue", 290, 230, 180, 80)], W)
    assert spoken_text(bubbles) is None


def test_clean_fixes_one_read_as_i_but_keeps_real_numbers():
    assert clean("1 LOOKED IN THE") == "I LOOKED IN THE"
    assert clean("taking place 800 years earlier, 1 year") == "taking place 800 years earlier, 1 year"
    assert clean("YOU’RE  BACK.") == "YOU'RE BACK."


def test_bench_match_counts_words_in_order():
    assert match("HE WAS CUT IN HALF.", "HE WAS CUT IN HALF") == (5, 5, 5)
    assert match("HE WAS CUT IN HALF.", "IN ay A qr") == (1, 5, 4)
