import numpy as np

from manhwa import panels as P

W = 400


def strip_of(blocks):
    """blocks = [("art" | "white" | "black" | "sky", hauteur)] → strip BGR."""
    rng = np.random.default_rng(0)
    parts = []
    for kind, h in blocks:
        if kind == "art":
            parts.append(rng.integers(0, 255, (h, W, 3), dtype=np.uint8))
        elif kind == "white":
            parts.append(np.full((h, W, 3), 255, np.uint8))
        elif kind == "black":
            parts.append(np.zeros((h, W, 3), np.uint8))
        elif kind == "sky":  # bande unie bleue au milieu d'une case
            parts.append(np.full((h, W, 3), (200, 150, 90), np.uint8))
    return np.vstack(parts)


def cuts_for(strip):
    std, mean = P.row_profile(strip)
    return P.auto_cuts(std, mean, W), std


def test_cuts_in_white_and_black_gutters():
    strip = strip_of([("white", 50), ("art", 500), ("white", 80), ("art", 600), ("black", 120), ("art", 400), ("white", 40)])
    cuts, std = cuts_for(strip)
    assert [c["y"] for c in cuts] == [590, 1290]
    assert all(c["sure"] for c in cuts)
    panels = P.panels_from_cuts([c["y"] for c in cuts], std)
    assert panels == [(50, 550), (630, 1230), (1350, 1750)]  # marges unies retirées


def test_flat_sky_inside_a_panel_is_not_a_gutter():
    strip = strip_of([("art", 300), ("sky", 60), ("art", 300), ("white", 80), ("art", 300)])
    cuts, _ = cuts_for(strip)
    assert [c["y"] for c in cuts] == [700]


def test_tiny_piece_is_merged_with_close_neighbour():
    # un « ... » de 20 px juste sous une case : recollé ; une vraie bulle loin de tout : gardée
    strip = strip_of([("art", 500), ("white", 30), ("art", 20), ("white", 300), ("art", 150), ("white", 300), ("art", 500)])
    cuts, std = cuts_for(strip)
    panels = P.panels_from_cuts([c["y"] for c in cuts], std)
    assert panels == [(0, 550), (850, 1000), (1300, 1800)]


def test_thin_line_in_tall_panel_is_proposed_as_doubt():
    # un trait blanc de 5 px entre deux cases collées : proposé « à vérifier »
    strip = strip_of([("art", 900), ("white", 5), ("art", 900)])
    cuts, _ = cuts_for(strip)
    assert [(c["y"], c["sure"]) for c in cuts] == [(902, False)]


def test_dark_flat_area_in_tall_panel_is_not_proposed():
    # un aplat sombre presque uni (écart-type ≈ 7, comme sur un vrai chapitre) : pas une séparation
    rng = np.random.default_rng(3)
    flat = (np.full((8, W, 3), 30, np.int16) + rng.integers(-20, 20, (8, W, 3))).clip(0, 255).astype(np.uint8)
    strip = np.vstack([strip_of([("art", 900)]), flat, strip_of([("art", 900)])])
    cuts, _ = cuts_for(strip)
    assert cuts == []


def test_snap_to_nearest_gutter():
    gutters = [{"y0": 100, "y1": 140, "sure": True}, {"y0": 900, "y1": 960, "sure": True}]
    assert P.snap(110, gutters, 50) == 120
    assert P.snap(180, gutters, 50) == 120
    assert P.snap(500, gutters, 50) == 500  # rien de proche : on coupe là où on a cliqué


def test_tall_panel_is_split_on_quiet_rows():
    # 2 212 px > 2 écrans (1 422 px) : 2 frames ; la coupe se cale sur la bande blanche
    # de 12 px (trop fine pour une gouttière) plutôt qu'au milieu exact
    strip = strip_of([("art", 1090), ("white", 12), ("art", 1110)])
    std, _ = P.row_profile(strip)
    parts = P.split_tall(0, strip.shape[0], W, std)
    assert len(parts) == 2
    assert parts[0][0] == 0 and parts[-1][1] == strip.shape[0]
    assert 1090 <= parts[1][0] < 1102


def test_panel_up_to_two_screens_stays_whole():
    # 1,5 écran (un visage en gros plan) : une seule frame, pas deux moitiés zoomées
    std = np.full(1066, 30.0, np.float32)
    assert P.split_tall(0, 1066, W, std) == [(0, 1066)]
    assert len(P.split_tall(0, 1500, W, std)) == 2  # au-delà de 2 écrans (1422 px)


def test_horizontal_margins_are_trimmed():
    strip = strip_of([("art", 300)])
    strip[:, :40] = 255
    strip[:, -40:] = 255
    assert P.horizontal_bounds(strip, 0, 300) == (40, W - 40)
