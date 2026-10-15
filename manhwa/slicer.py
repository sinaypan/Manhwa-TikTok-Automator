"""Découpe manuelle (V1 améliorée) : on cadre chaque frame 9:16 dans le long strip.

Temporaire : remplacé par la découpe automatique + l'écran Découpe du Studio (phase 1).
"""
import os
import time

import cv2
import numpy as np

from manhwa.images import BG_MODES, letterbox, load_strip, write_jpeg

PREVIEW_W, PREVIEW_H = 540, 960
HANDLE_R = 16
MIN_SIZE = 80
SAVE_COOLDOWN_SEC = 0.30

KEY_ENTER, KEY_BACKSPACE = 13, 8
KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT = 2490368, 2621440, 2424832, 2555904


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class CropBox:
    """Cadre de découpe, en coordonnées du viewport (pas du strip entier)."""

    def __init__(self, vw, vh):
        self.reset(vw, vh)

    def reset(self, vw, vh):
        self.x, self.y, self.w, self.h = 0, 0, vw, vh
        self.drag_mode = self.drag_start = self.orig = None

    def rect(self):
        return self.x, self.y, self.w, self.h

    def _hit(self, px, py):
        corners = {
            "tl": (self.x, self.y),
            "tr": (self.x + self.w, self.y),
            "bl": (self.x, self.y + self.h),
            "br": (self.x + self.w, self.y + self.h),
        }
        for name, (cx, cy) in corners.items():
            if (px - cx) ** 2 + (py - cy) ** 2 <= HANDLE_R ** 2:
                return name
        if self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h:
            return "move"
        return None

    def on_mouse(self, event, px, py, vw, vh):
        if event == cv2.EVENT_LBUTTONDOWN:
            hit = self._hit(px, py)
            if hit:
                self.drag_mode, self.drag_start = hit, (px, py)
                self.orig = (self.x, self.y, self.w, self.h)

        elif event == cv2.EVENT_MOUSEMOVE and self.drag_mode:
            dx, dy = px - self.drag_start[0], py - self.drag_start[1]
            ox, oy, ow, oh = self.orig
            if self.drag_mode == "move":
                self.x = clamp(ox + dx, 0, vw - ow)
                self.y = clamp(oy + dy, 0, vh - oh)
                return
            left = ox + dx if self.drag_mode in ("tl", "bl") else ox
            top = oy + dy if self.drag_mode in ("tl", "tr") else oy
            right = ox + ow + dx if self.drag_mode in ("tr", "br") else ox + ow
            bottom = oy + oh + dy if self.drag_mode in ("bl", "br") else oy + oh
            left, top = clamp(left, 0, right - MIN_SIZE), clamp(top, 0, bottom - MIN_SIZE)
            right, bottom = clamp(right, left + MIN_SIZE, vw), clamp(bottom, top + MIN_SIZE, vh)
            self.x, self.y, self.w, self.h = left, top, right - left, bottom - top

        elif event == cv2.EVENT_LBUTTONUP:
            self.drag_mode = self.drag_start = self.orig = None

    def clamp_inside(self, vw, vh):
        self.w = clamp(self.w, MIN_SIZE, vw)
        self.h = clamp(self.h, MIN_SIZE, vh)
        self.x = clamp(self.x, 0, vw - self.w)
        self.y = clamp(self.y, 0, vh - self.h)


def draw_ui(img, header_lines, footer, toast=None):
    h, w = img.shape[:2]
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (w, 120), (0, 0, 0), -1)
    img = cv2.addWeighted(overlay, 0.40, img, 0.60, 0)
    y = 28
    for line in header_lines:
        cv2.putText(img, line, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)
        y += 26

    overlay = img.copy()
    cv2.rectangle(overlay, (0, h - 44), (w, h), (0, 0, 0), -1)
    img = cv2.addWeighted(overlay, 0.40, img, 0.60, 0)
    cv2.putText(img, footer, (16, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    if toast:
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 130), (w, 175), (0, 0, 0), -1)
        img = cv2.addWeighted(overlay, 0.30, img, 0.70, 0)
        cv2.putText(img, toast, (16, 162), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def next_frame_index(frames):
    return max((int(f["file"][6:10]) for f in frames), default=0) + 1


def save_frame(chapter, data, strip, rect, cfg, bg_mode):
    """Écrit la frame 9:16 du crop `rect` (coordonnées du strip) et l'ajoute au projet."""
    x, y, w, h = rect
    out = letterbox(strip[y:y + h, x:x + w], cfg["output"]["width"], cfg["output"]["height"],
                    bg_mode, cfg["slicer"]["blur_ksize"])
    if out is None:
        return None
    chapter.frames_dir.mkdir(parents=True, exist_ok=True)
    name = f"frame_{next_frame_index(data['frames']):04d}.jpg"
    write_jpeg(chapter.frames_dir / name, out, cfg["slicer"]["jpeg_quality"])
    data["frames"].append({"file": name, "crop": [int(x), int(y), int(w), int(h)], "bg": bg_mode})
    chapter.save(data)
    return name


def undo_last_frame(chapter, data):
    if not data["frames"]:
        return None
    frame = data["frames"].pop()
    try:
        os.remove(chapter.frames_dir / frame["file"])
    except FileNotFoundError:
        pass
    chapter.save(data)
    return frame


def run_slicer(chapter, cfg):
    sc = cfg["slicer"]
    strip, used = load_strip(chapter.pages(), sc["max_src_width"])
    if strip is None:
        print("  Aucune image lisible dans ce chapitre.")
        return False

    data = chapter.load()
    H, W = strip.shape[:2]
    strip_info = {"width": W, "height": H, "max_width": sc["max_src_width"], "pages": [p.name for p in used]}
    if data["frames"] and data.get("strip") not in (None, strip_info):
        print("  [!] Les pages ont changé depuis la dernière découpe : les anciennes frames ne correspondent plus.")
        if input("  Tout recommencer (supprime les frames existantes) ? [o/N] ").strip().lower() != "o":
            return False
        while undo_last_frame(chapter, data):
            pass
    data["strip"] = strip_info
    chapter.save(data)

    view_h = clamp(int(W * 16 / 9), 1, H)
    state = {"view_y": 0}
    crop = CropBox(W, view_h)
    bg_mode = sc["bg_mode"] if sc["bg_mode"] in BG_MODES else "auto"
    step, resize_step = sc["move_step"], sc["resize_step"]
    show_help = True
    last_save = 0.0
    toast_msg, toast_until = None, 0.0

    def toast(msg, seconds=1.2):
        nonlocal toast_msg, toast_until
        toast_msg, toast_until = msg, time.time() + seconds

    win = "Decoupe - " + chapter.root.name
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)

    def mouse_cb(event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEWHEEL:
            # le sens est dans le signe de flags (positif = molette vers le haut)
            direction = -1 if flags > 0 else 1
            state["view_y"] += direction * step * 4
            return
        crop.on_mouse(event, int(x * W / PREVIEW_W), int(y * view_h / PREVIEW_H), W, view_h)

    cv2.setMouseCallback(win, mouse_cb)
    print(f"  Fenêtre de découpe ouverte ({len(data['frames'])} frames déjà faites). Q pour terminer.")

    while True:
        state["view_y"] = clamp(state["view_y"], 0, max(0, H - view_h))
        view_y = state["view_y"]
        viewport = strip[view_y:view_y + view_h, 0:W]

        crop.clamp_inside(W, view_h)
        cx, cy, cw, ch = crop.rect()
        dim = (viewport * 0.25).astype(np.uint8)
        dim[cy:cy + ch, cx:cx + cw] = viewport[cy:cy + ch, cx:cx + cw]
        cv2.rectangle(dim, (cx, cy), (cx + cw, cy + ch), (0, 0, 255), 3)
        for hx, hy in [(cx, cy), (cx + cw, cy), (cx, cy + ch), (cx + cw, cy + ch)]:
            cv2.circle(dim, (hx, hy), 10, (0, 0, 255), -1)
        preview = cv2.resize(dim, (PREVIEW_W, PREVIEW_H), interpolation=cv2.INTER_AREA)

        if show_help:
            lines = [
                "Molette/fleches: defiler | souris: deplacer, coins: redim.",
                "IJKL: deplacer cadre | +/-: taille | R: cadre plein | M: fond",
                "ENTREE: garder | RETOUR: annuler la derniere | O: test OCR | H | Q",
            ]
        else:
            lines = [f"Strip {W}x{H} | y={view_y} ({100 * (view_y + view_h) // H}%) | cadre {cw}x{ch}"]
        footer = f"{len(data['frames'])} frames | prochaine: frame_{next_frame_index(data['frames']):04d} | fond={bg_mode}"
        preview = draw_ui(preview, lines, footer, toast_msg if time.time() < toast_until else None)
        cv2.imshow(win, preview)

        key = cv2.waitKeyEx(10)
        if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
            break  # fenêtre fermée avec la croix
        if key == -1:
            continue

        if key in (ord("q"), ord("Q"), 27):
            break
        elif key in (ord("h"), ord("H")):
            show_help = not show_help
        elif key in (ord("m"), ord("M")):
            bg_mode = BG_MODES[(BG_MODES.index(bg_mode) + 1) % len(BG_MODES)]
            toast(f"Fond = {bg_mode}", 0.8)
        elif key in (ord("r"), ord("R")):
            crop.reset(W, view_h)
            toast("Cadre plein ecran", 0.8)
        elif key == KEY_UP:
            state["view_y"] -= step * 4
        elif key == KEY_DOWN:
            state["view_y"] += step * 4
        elif key == KEY_LEFT:
            state["view_y"] -= step
        elif key == KEY_RIGHT:
            state["view_y"] += step
        elif key in (ord("i"), ord("I")):
            crop.y -= step
        elif key in (ord("k"), ord("K")):
            crop.y += step
        elif key in (ord("j"), ord("J")):
            crop.x -= step
        elif key in (ord("l"), ord("L")):
            crop.x += step
        elif key in (ord("+"), ord("=")):
            crop.w += resize_step
            crop.h += resize_step
        elif key in (ord("-"), ord("_")):
            crop.w -= resize_step
            crop.h -= resize_step
        elif key in (ord("o"), ord("O")):
            from manhwa.ocr import read_text

            text = read_text(strip[view_y + cy:view_y + cy + ch, cx:cx + cw], cfg)
            print(f"  [OCR test] {text or '(rien / bruit)'}")
            toast(f"OCR: {text[:28]}..." if text else "OCR: rien")
        elif key == KEY_BACKSPACE:
            removed = undo_last_frame(chapter, data)
            if removed:
                state["view_y"] = removed["crop"][1]  # on revient là où était la frame annulée
                crop.reset(W, view_h)
            toast(f"Annule: {removed['file']}" if removed else "Rien a annuler", 0.8)
        elif key == KEY_ENTER and time.time() - last_save >= SAVE_COOLDOWN_SEC:
            last_save = time.time()
            name = save_frame(chapter, data, strip, (cx, view_y + cy, cw, ch), cfg, bg_mode)
            if name:
                print(f"  [OK] {name}")
                toast(f"OK: {name}")
                # on avance jusqu'à la fin du cadre gardé : la suite est la prochaine case
                state["view_y"] = view_y + cy + ch
                crop.reset(W, view_h)

    cv2.destroyAllWindows()
    print(f"  Découpe terminée : {len(data['frames'])} frames.")
    return True
