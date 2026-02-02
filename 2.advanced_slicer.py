import cv2
import os
import glob
import numpy as np
import time
import pytesseract
import re
from PIL import Image
import pandas as pd



# =========================
# CONFIG
# =========================
TIKTOK_W, TIKTOK_H = 1080, 1920
PREVIEW_W, PREVIEW_H = 540, 960
BG_MODE = "blur"          # "blur" | "black" | "gray"
BLUR_KSIZE = 61
MAX_SRC_WIDTH = 1200
SAVE_COOLDOWN_SEC = 0.30

MOVE_STEP = 20
RESIZE_STEP = 20
SUPPORTED = (".jpg", ".jpeg", ".png", ".webp")

HANDLE_R = 16

# =========================
# Utils
# =========================
def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def load_images_as_one(folder):
    files = sorted([f for f in glob.glob(os.path.join(folder, "*.*"))
                    if f.lower().endswith(SUPPORTED)])
    if not files:
        return None, []

    imgs = []
    widths = []
    for f in files:
        im = cv2.imread(f)
        if im is None:
            continue
        widths.append(im.shape[1])
        imgs.append(im)

    if not imgs:
        return None, []

    target_w = min(min(widths), MAX_SRC_WIDTH)

    resized = []
    for im in imgs:
        h, w = im.shape[:2]
        if w != target_w:
            scale = target_w / w
            new_h = int(h * scale)
            im = cv2.resize(im, (target_w, new_h), interpolation=cv2.INTER_AREA)
        resized.append(im)

    big = cv2.vconcat(resized)
    return big, files

def make_background(frame_9_16):
    if BG_MODE == "black":
        return np.zeros_like(frame_9_16)
    if BG_MODE == "gray":
        return np.full_like(frame_9_16, 40)
    k = BLUR_KSIZE if BLUR_KSIZE % 2 == 1 else BLUR_KSIZE + 1
    return cv2.GaussianBlur(frame_9_16, (k, k), 0)

def letterbox_to_tiktok(crop, out_w=TIKTOK_W, out_h=TIKTOK_H):
    if crop is None or crop.size == 0:
        return None

    ch, cw = crop.shape[:2]

    # cover -> fond 9:16
    scale_cover = max(out_w / cw, out_h / ch)
    cover = cv2.resize(crop, (int(cw * scale_cover), int(ch * scale_cover)), interpolation=cv2.INTER_AREA)
    y0 = (cover.shape[0] - out_h) // 2
    x0 = (cover.shape[1] - out_w) // 2
    frame = cover[y0:y0 + out_h, x0:x0 + out_w].copy()

    bg = make_background(frame)

    # contain -> collage net au centre
    scale_contain = min(out_w / cw, out_h / ch)
    new_w = int(cw * scale_contain)
    new_h = int(ch * scale_contain)
    crop_rs = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)

    y = (out_h - new_h) // 2
    x = (out_w - new_w) // 2
    bg[y:y + new_h, x:x + new_w] = crop_rs
    return bg

def draw_pretty_ui(img, header_lines, footer, toast=None):
    h, w = img.shape[:2]
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (w, 120), (0, 0, 0), -1)
    img = cv2.addWeighted(overlay, 0.40, img, 0.60, 0)

    y = 28
    for line in header_lines:
        cv2.putText(img, line, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2, cv2.LINE_AA)
        y += 26

    overlay2 = img.copy()
    cv2.rectangle(overlay2, (0, h - 44), (w, h), (0, 0, 0), -1)
    img = cv2.addWeighted(overlay2, 0.40, img, 0.60, 0)
    cv2.putText(img, footer, (16, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2, cv2.LINE_AA)

    # toast (confirmation save)
    if toast:
        overlay3 = img.copy()
        cv2.rectangle(overlay3, (0, 130), (w, 175), (0, 0, 0), -1)
        img = cv2.addWeighted(overlay3, 0.30, img, 0.70, 0)
        cv2.putText(img, toast, (16, 162), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)

    return img

# =========================
# CropBox en coordonnées VIEWPORT (pas global)
# =========================
class CropBox:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.drag_mode = None
        self.drag_start = None
        self.orig = None

    def rect(self):
        return self.x, self.y, self.w, self.h

    def reset_full_viewport(self, vw, vh):
        self.x, self.y, self.w, self.h = 0, 0, vw, vh
        self.drag_mode = None
        self.drag_start = None
        self.orig = None

    def _hit_handle(self, px, py):
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
            hit = self._hit_handle(px, py)
            if hit:
                self.drag_mode = hit
                self.drag_start = (px, py)
                self.orig = (self.x, self.y, self.w, self.h)

        elif event == cv2.EVENT_MOUSEMOVE and self.drag_mode:
            dx = px - self.drag_start[0]
            dy = py - self.drag_start[1]
            ox, oy, ow, oh = self.orig
            min_w, min_h = 80, 80

            if self.drag_mode == "move":
                nx = clamp(ox + dx, 0, vw - ow)
                ny = clamp(oy + dy, 0, vh - oh)
                self.x, self.y = nx, ny

            elif self.drag_mode == "tl":
                nx, ny = ox + dx, oy + dy
                nw, nh = ow - dx, oh - dy
                if nw >= min_w and nh >= min_h:
                    self.x = clamp(nx, 0, ox + ow - min_w)
                    self.y = clamp(ny, 0, oy + oh - min_h)
                    self.w = clamp(nw, min_w, vw - self.x)
                    self.h = clamp(nh, min_h, vh - self.y)

            elif self.drag_mode == "tr":
                ny = oy + dy
                nw, nh = ow + dx, oh - dy
                if nw >= min_w and nh >= min_h:
                    self.y = clamp(ny, 0, oy + oh - min_h)
                    self.w = clamp(nw, min_w, vw - self.x)
                    self.h = clamp(nh, min_h, vh - self.y)

            elif self.drag_mode == "bl":
                nx = ox + dx
                nw, nh = ow - dx, oh + dy
                if nw >= min_w and nh >= min_h:
                    self.x = clamp(nx, 0, ox + ow - min_w)
                    self.w = clamp(nw, min_w, vw - self.x)
                    self.h = clamp(nh, min_h, vh - self.y)

            elif self.drag_mode == "br":
                nw, nh = ow + dx, oh + dy
                if nw >= min_w and nh >= min_h:
                    self.w = clamp(nw, min_w, vw - self.x)
                    self.h = clamp(nh, min_h, vh - self.y)

        elif event == cv2.EVENT_LBUTTONUP:
            self.drag_mode = None
            self.drag_start = None
            self.orig = None

    def clamp_inside(self, vw, vh):
        self.w = clamp(self.w, 80, vw)
        self.h = clamp(self.h, 80, vh)
        self.x = clamp(self.x, 0, vw - self.w)
        self.y = clamp(self.y, 0, vh - self.h)

# =========================
# OCR CONFIG
# =========================
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESS_CONFIG = r"--oem 1 --psm 6"
TESS_LANG = "eng"

def preprocess_image_for_ocr(cv2_img):
    gray = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary

def is_valid_text(text):
    if not text:
        return False
    text = text.strip()
    if len(text) < 4:
        return False
    letters = sum(c.isalpha() for c in text)
    total = len(text)
    if letters < total * 0.5:
        return False
    if re.search(r"(.)\1\1\1", text):
        return False
    return True

def extract_text_smart_from_cv(crop_cv2):
    """OCR directement depuis une image OpenCV (pas besoin de relire le fichier)."""
    try:
        processed = preprocess_image_for_ocr(crop_cv2)
        pil_img = Image.fromarray(processed)
        text = pytesseract.image_to_string(pil_img, lang=TESS_LANG, config=TESS_CONFIG)
        clean = text.replace("\n", " ").strip()
        return clean if is_valid_text(clean) else None
    except Exception as e:
        print(f"[OCR] Erreur: {e}")
        return None
    
# =========================
# OCR STRICT (MANWHA)
# =========================
STRICT = {
    "min_chars": 6,             # <- baisse (pour "WAKE UP!")
    "min_words": 2,             # dialogue minimal
    "min_avg_conf": 68,         # <- baisse un peu (bulles petites)
    "min_letters_ratio": 0.65,  # <- un peu moins strict (apostrophes/!!)
    "max_upper_ratio": 0.95,    # <- on n'interdit plus les MAJ (dialogue souvent en caps)
    "max_punct_ratio": 0.35,    # <- tolère "!?',."
    "max_digit_ratio": 0.10,
}

SFX_BLACKLIST = {
    "bam","boom","pow","crash","bang","slam","thud","wham","whoosh","swoosh",
    "krr","krk","tsk","ugh","ahh","hah","ha","hm","hmm","mm","grr","argh",
    "snap","tap","clack","click","ring","ding","buzz","zip","zap",
}

def normalize_text(s: str) -> str:
    s = s.replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # enlever les “pseudo glyphes” fréquents
    s = s.replace("—", "-").replace("–", "-").replace("…", "...")
    return s

def looks_like_sfx(text: str) -> bool:
    t = text.strip()
    if not t:
        return True

    # enlève ponctuation pour comparer
    low = re.sub(r"[^a-zA-Z\s]", "", t).lower().strip()
    words = [w for w in low.split() if w]

    # blacklist
    for w in words:
        if w in SFX_BLACKLIST:
            return True

    # SFX typique = 1 mot (ou 2 très courts) + tout caps souvent
    raw_words = t.split()
    alpha_only = re.sub(r"[^A-Za-z]", "", t)

    if len(raw_words) == 1 and len(alpha_only) <= 6:
        return True

    # répétitions (bruit)
    if re.search(r"(.)\1\1\1", t):
        return True

    # Beaucoup de symboles
    non_alnum = sum(not c.isalnum() and not c.isspace() for c in t)
    if len(t) and (non_alnum / len(t) > 0.45):
        return True

    return False

def pass_strict_rules(text: str, avg_conf: float) -> bool:
    t = normalize_text(text)
    if len(t) < STRICT["min_chars"]:
        return False

    # ✅ EXCEPTION DIALOGUE : on accepte même si c'est en MAJ
    # si: 2+ mots, contient un espace, confiance ok
    words = t.split()
    if len(words) >= 2 and " " in t and avg_conf >= STRICT["min_avg_conf"]:
        # mais on refuse si c'est clairement blacklist SFX
        if not looks_like_sfx(t):
            return True

    # sinon on applique règles strictes normales
    if looks_like_sfx(t):
        return False

    letters = sum(c.isalpha() for c in t)
    digits  = sum(c.isdigit() for c in t)
    punct   = sum((not c.isalnum()) and (not c.isspace()) for c in t)
    total   = len(t)

    if total == 0:
        return False
    if letters / total < STRICT["min_letters_ratio"]:
        return False
    if digits / total > STRICT["max_digit_ratio"]:
        return False
    if punct / total > STRICT["max_punct_ratio"]:
        return False
    if len(words) < STRICT["min_words"]:
        return False
    if avg_conf < STRICT["min_avg_conf"]:
        return False

    return True

def extract_text_ultra_strict_from_cv(crop_cv2):
    """
    OCR ultra strict:
    - utilise image_to_data pour récupérer confidence par token
    - reconstruit uniquement tokens "bons"
    - filtre manwha (SFX, MAJ, court, bruit)
    """
    try:
        processed = preprocess_image_for_ocr(crop_cv2)
        pil_img = Image.fromarray(processed)

        # data OCR avec confidences
        data = pytesseract.image_to_data(
            pil_img, lang=TESS_LANG, config=TESS_CONFIG, output_type=pytesseract.Output.DICT
        )

        tokens = []
        confs = []
        n = len(data["text"])
        for i in range(n):
            txt = (data["text"][i] or "").strip()
            if not txt:
                continue
            # conf peut être '-1' ou '0'
            try:
                conf = float(data["conf"][i])
            except:
                conf = -1.0

            # token bruit -> skip
            if conf < 60:
                continue

            # token doit avoir au moins 2 lettres
            letters = sum(c.isalpha() for c in txt)
            if letters < 2:
                continue

            # token trop "symboles"
            if re.search(r"(.)\1\1\1", txt):
                continue

            tokens.append(txt)
            confs.append(conf)

        if not tokens:
            return None

        text = normalize_text(" ".join(tokens))

        # confidence moyenne sur tokens gardés
        avg_conf = sum(confs) / len(confs) if confs else 0

        if avg_conf < STRICT["min_avg_conf"]:
            return None

        if not pass_strict_rules(text, avg_conf):
            return None


        return text

    except Exception as e:
        print(f"[OCR] Erreur: {e}")
        return None



# =========================
# Main
# =========================
def main():
    print("=== SLICER TIKTOK V5 (viewport-fixed crop + reset + save toast) ===")
    BG_MODE = "blur"
    folder = input("Chemin du dossier : ").strip('"').strip()
    if not os.path.isdir(folder):
        print("Dossier introuvable.")
        return

    big, files = load_images_as_one(folder)
    if big is None:
        print("Aucune image lisible.")
        return

    out_dir = os.path.join(folder, "frames_tiktok")
    os.makedirs(out_dir, exist_ok=True)

    transcript_file = os.path.join(out_dir, "transcript.txt")


    H, W = big.shape[:2]
    view_h = int(W * (16 / 9))
    view_h = clamp(view_h, 1, H)

    view_y = 0
    crop = CropBox(0, 0, W, view_h)  # ✅ taille par défaut = 1 frame TikTok (tout le viewport)

    show_help = True
    frame_count = len(glob.glob(os.path.join(out_dir, "frame_*.jpg"))) + 1
    last_save = 0.0

    toast_msg = None
    toast_until = 0.0

    win = "TikTok Preview"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)

    # souris: coords preview -> coords viewport (W x view_h)
    def mouse_cb(event, x, y, flags, param):
        nonlocal view_h
        vx = int(x * (W / PREVIEW_W))
        vy = int(y * (view_h / PREVIEW_H))
        crop.on_mouse(event, vx, vy, W, view_h)

    cv2.setMouseCallback(win, mouse_cb)

    while True:
        view_h = int(W * (16 / 9))
        view_h = clamp(view_h, 1, H)
        view_y = clamp(view_y, 0, max(0, H - view_h))

        viewport = big[view_y:view_y + view_h, 0:W].copy()

        # assombrir + highlight crop
        dim = (viewport * 0.25).astype(np.uint8)

        crop.clamp_inside(W, view_h)
        cx, cy, cw, ch = crop.rect()

        # highlight zone crop (dans viewport)
        dim[cy:cy + ch, cx:cx + cw] = viewport[cy:cy + ch, cx:cx + cw]

        # rectangle + handles
        cv2.rectangle(dim, (cx, cy), (cx + cw, cy + ch), (0, 0, 255), 3)
        for (hx, hy) in [(cx, cy), (cx + cw, cy), (cx, cy + ch), (cx + cw, cy + ch)]:
            cv2.circle(dim, (hx, hy), 10, (0, 0, 255), -1)

        preview = cv2.resize(dim, (PREVIEW_W, PREVIEW_H), interpolation=cv2.INTER_AREA)

        if show_help:
            lines = [
                "Souris: drag centre=move | drag coins=resize",
                "Fleches: scroll | IJKL: move crop | +/- resize crop",
                "ENTER: Save (reset crop) | R: reset | M: bg | H: help | Q: quit"
            ]
        else:
            lines = [f"Global {W}x{H} | viewport y={view_y} | crop {cw}x{ch}"]

        footer = f"frame_{frame_count:04d}.jpg | BG={BG_MODE}"
        now = time.time()
        toast = toast_msg if now < toast_until else None
        preview = draw_pretty_ui(preview, lines, footer, toast=toast)

        cv2.imshow(win, preview)

        key = cv2.waitKeyEx(10)
        if key == -1:
            continue

        # quit
        if key in (ord('q'), ord('Q')):
            break

        # help toggle
        if key in (ord('h'), ord('H')):
            show_help = not show_help

        # bg mode toggle
        if key in (ord('m'), ord('M')):
            BG_MODE = "black" if BG_MODE == "blur" else ("gray" if BG_MODE == "black" else "blur")
            toast_msg = f"BG = {BG_MODE}"
            toast_until = time.time() + 0.8

        # reset crop (full frame)
        if key in (ord('r'), ord('R')):
            crop.reset_full_viewport(W, view_h)
            toast_msg = "Reset crop: full TikTok frame"
            toast_until = time.time() + 0.8

        # arrows scroll (waitKeyEx)
        if key == 2490368:      # UP
            view_y -= MOVE_STEP * 4
        elif key == 2621440:    # DOWN
            view_y += MOVE_STEP * 4
        elif key == 2424832:    # LEFT (small up)
            view_y -= MOVE_STEP
        elif key == 2555904:    # RIGHT (small down)
            view_y += MOVE_STEP

        # move crop (IJKL)
        if key in (ord('i'), ord('I')):
            crop.y -= MOVE_STEP
        elif key in (ord('k'), ord('K')):
            crop.y += MOVE_STEP
        elif key in (ord('j'), ord('J')):
            crop.x -= MOVE_STEP
        elif key in (ord('l'), ord('L')):
            crop.x += MOVE_STEP

        # resize crop (+/-)
        if key in (ord('+'), ord('=')):
            crop.w += RESIZE_STEP
            crop.h += RESIZE_STEP
        elif key in (ord('-'), ord('_')):
            crop.w -= RESIZE_STEP
            crop.h -= RESIZE_STEP

        if key in (ord('o'), ord('O')):
            crop.clamp_inside(W, view_h)
            cx, cy, cw, ch = crop.rect()
            gx = cx
            gy = view_y + cy
            crop_img = big[gy:gy + ch, gx:gx + cw]
            ocr_txt = extract_text_ultra_strict_from_cv(crop_img)
            if ocr_txt:
                print(f"[OCR] {ocr_txt}")
                toast_msg = f"OCR: {ocr_txt[:28]}..."
            else:
                print("[OCR] (rien / bruit)")
                toast_msg = "OCR: rien"
            toast_until = time.time() + 1.2



        # SAVE: Enter
        if key == 13:
            now = time.time()
            if now - last_save >= SAVE_COOLDOWN_SEC:
                last_save = now

                crop.clamp_inside(W, view_h)
                cx, cy, cw, ch = crop.rect()

                # ✅ conversion viewport->global
                gx = cx
                gy = view_y + cy
                crop_img = big[gy:gy + ch, gx:gx + cw]

                # ✅ OCR sur le crop (AVANT letterbox, car c'est le vrai contenu)
                ocr_txt = extract_text_ultra_strict_from_cv(crop_img)

                # ✅ sortie TikTok 9:16
                out = letterbox_to_tiktok(crop_img, TIKTOK_W, TIKTOK_H)
                if out is not None:
                    name = f"frame_{frame_count:04d}.jpg"
                    path = os.path.join(out_dir, name)
                    cv2.imwrite(path, out, [int(cv2.IMWRITE_JPEG_QUALITY), 92])

                    # ✅ transcript
                    if ocr_txt:
                        with open(transcript_file, "a", encoding="utf-8") as f:
                            f.write(f"[{name}] : {ocr_txt}\n\n")

                    # ✅ feedback console + UI
                    if ocr_txt:
                        print(f"[OK] Pris: {name} | OCR: {ocr_txt[:80]}{'...' if len(ocr_txt) > 80 else ''}")
                        toast_msg = f"OK: {name} | OCR: {ocr_txt[:24]}..."
                    else:
                        print(f"[OK] Pris: {name} | OCR: (bruit ignore)")
                        toast_msg = f"OK: {name} saved"

                    toast_until = time.time() + 1.2
                    frame_count += 1

                    # ✅ reset taille crop après chaque screen
                    crop.reset_full_viewport(W, view_h)


    cv2.destroyAllWindows()
    print("Terminé.")

if __name__ == "__main__":
    main()
