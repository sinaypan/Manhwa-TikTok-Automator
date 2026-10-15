"""Personnages depuis le wiki Fandom de la série (API MediaWiki, lecture seule).

Pour chaque page de la catégorie « Characters » : nom, genre, cheveux, yeux, chapitre
du manhwa où il apparaît, et le début de « Personality » (pour choisir sa voix). Les
passages cachés pour spoiler (spoilerblur, SpoilerHidden) sont retirés.

Le nom d'un groupe de visages est proposé d'après le chapitre d'apparition, la couleur
des cheveux et, si elles ont été téléchargées, les images du wiki (visages comparés).

Les images sont servies par static.wikia.nocookie.net, qui demande une vérification
anti-robot Cloudflare : elles se téléchargent dans une vraie fenêtre de navigateur où
la vérification se passe à la main, une fois (fetch_images), comme pour le scraper.

    inbox/<série>/.wiki/wiki.json     ce qui a été lu
    inbox/<série>/.wiki/<w>-<k>.img   les images d'un personnage
    inbox/<série>/.wiki/faces.npz     la description des visages trouvés sur ces images
"""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

WIKI_DIR = ".wiki"
USER_AGENT = "manhwa-studio/2 (outil local, lecture seule)"
BATCH = 50  # titres par requête (limite de l'API)
MAX_IMAGES = 4  # images gardées par personnage
CHECK_TIMEOUT = 180_000  # ms laissées pour passer la vérification à la main


def wiki_dir(series):
    return Path(series) / WIKI_DIR


def load_wiki(series):
    path = wiki_dir(series) / "wiki.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def save_wiki(series, data):
    folder = wiki_dir(series)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "wiki.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, folder / "wiki.json")


def candidates(series_name):
    """Adresses possibles du wiki d'après le nom de la série (« Myst Might Mayhem » → myst-might-mayhem)."""
    words = re.findall(r"[a-z0-9]+", series_name.lower())
    subs = ["-".join(words), "".join(words)]
    return [f"https://{s}.fandom.com" for s in dict.fromkeys(subs) if s]


class Wiki:
    def __init__(self, base, session=None):
        self.base = base.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def api(self, **params):
        params.update(format="json", formatversion=2)
        for attempt in range(3):
            r = self.session.get(f"{self.base}/api.php", params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            time.sleep(1 + attempt)
        r.raise_for_status()

    def exists(self):
        try:
            return bool(self.sitename())
        except Exception:
            return False

    def sitename(self):
        return self.api(action="query", meta="siteinfo")["query"]["general"]["sitename"]

    def category(self, name="Characters"):
        titles, cont = [], {}
        while True:
            d = self.api(action="query", list="categorymembers", cmtitle=f"Category:{name}", cmlimit=500, cmnamespace=0, **cont)
            titles += [m["title"] for m in d["query"]["categorymembers"]]
            if "continue" not in d:
                return titles
            cont = d["continue"]

    def contents(self, titles):
        out = {}
        for i in range(0, len(titles), BATCH):
            d = self.api(action="query", prop="revisions", rvprop="content", rvslots="main", titles="|".join(titles[i:i + BATCH]))
            for page in d["query"]["pages"]:
                revs = page.get("revisions")
                if revs:
                    out[page["title"]] = revs[0]["slots"]["main"]["content"]
        return out

    def image_urls(self, files, width=400):
        """{nom de fichier: adresse de l'image réduite à `width` px}."""
        out = {}
        for i in range(0, len(files), BATCH):
            d = self.api(action="query", prop="imageinfo", iiprop="url", iiurlwidth=width,
                         titles="|".join(f"File:{f}" for f in files[i:i + BATCH]))
            back = {n["to"]: n["from"] for n in d["query"].get("normalized", [])}
            for page in d["query"]["pages"]:
                info = (page.get("imageinfo") or [{}])[0]
                url = info.get("thumburl") or info.get("url")
                if url:
                    out[back.get(page["title"], page["title"]).split(":", 1)[1]] = url
        return out


# ---------- Lecture du wikitexte ----------

def strip_spoilers(text):
    text = re.sub(r"<span[^>]*spoilerblur[^>]*>.*?</span>", "", text, flags=re.S | re.I)
    # {{SpoilerHidden|…|…}} peut contenir des liens [[…]] : on retire jusqu'aux }} équilibrées
    out, i = [], 0
    while True:
        j = text.find("{{SpoilerHidden", i)
        if j < 0:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:j])
        depth, k = 0, j
        while k < len(text):
            if text.startswith("{{", k):
                depth += 1
                k += 2
            elif text.startswith("}}", k):
                depth -= 1
                k += 2
                if depth == 0:
                    break
            else:
                k += 1
        i = k


def plain(text):
    """Wikitexte → texte simple."""
    t = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    t = re.sub(r"<br\s*/?>", ", ", t, flags=re.I)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("'''", "").replace("''", "")
    t = re.sub(r"\s*,\s*(,\s*)+", ", ", t)
    return re.sub(r"\s+", " ", t).strip(" ,*")


def field(wikitext, name):
    m = re.search(rf"^\|\s*{name}\s*=(.*?)(?=^\s*\||^\}}\}})", wikitext, re.M | re.S)
    return m.group(1).strip() if m else ""


def gallery_files(value):
    """Fichiers d'une valeur d'infobox : <gallery> (un par ligne) ou [[File:x.png|…]]."""
    files = re.findall(r"\[\[(?:File|Image):([^|\]]+)", value, re.I)
    if "<gallery>" in value:
        inner = value.split("<gallery>", 1)[1].split("</gallery>", 1)[0]
        files += [line.split("|")[0].strip() for line in inner.splitlines() if line.strip()]
    elif not files and re.search(r"\.(png|jpe?g|webp|gif)\b", value, re.I):
        files.append(value.split("|")[0].strip())
    return [f for f in dict.fromkeys(files) if f]


def section(wikitext, title):
    m = re.search(rf"^==+\s*{title}\s*==+\s*$(.*?)(?=^==[^=]|\Z)", wikitext, re.M | re.S | re.I)
    return m.group(1) if m else ""


def short(text, limit=600):
    """Les premières phrases, jusqu'à `limit` caractères."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > limit // 3 else cut.rsplit(" ", 1)[0] + "…").strip()


HAIR_WORDS = [  # mot du wiki → couleur reconnue sur l'image (manhwa/cast.py : hair_colors)
    ("silver", "white"), ("white", "white"), ("grey", "gray"), ("gray", "gray"), ("black", "black"),
    ("blond", "yellow"), ("golden", "yellow"), ("gold", "yellow"), ("yellow", "yellow"), ("brown", "brown"),
    ("red", "red"), ("crimson", "red"), ("orange", "orange"), ("pink", "pink"), ("purple", "purple"),
    ("violet", "purple"), ("blue", "blue"), ("navy", "blue"), ("green", "green"), ("teal", "cyan"), ("cyan", "cyan"),
]


def hair_key(text):
    """La première couleur citée (« Blue (Before), Black (After…) » → "blue")."""
    low = text.lower()
    hits = [(low.find(word), key) for word, key in HAIR_WORDS if word in low]
    return min(hits)[1] if hits else None


def parse_character(title, wikitext):
    text = strip_spoilers(wikitext)
    debut = re.search(r"\d+", plain(field(text, "manhwa_debut")))
    personality = "\n\n".join(p for p in (plain(p) for p in section(text, "Personality").split("\n\n")) if p)
    images = gallery_files(field(text, "image1")) or gallery_files(field(text, "image"))
    return {
        "title": title,
        "name": plain(field(text, "name")) or title,
        "gender": plain(field(text, "gender")),
        "hair": plain(field(text, "hair_color")),
        "hair_key": hair_key(plain(field(text, "hair_color"))),
        "eyes": plain(field(text, "eye_color")),
        "debut": int(debut.group()) if debut else None,
        "personality": short(personality),
        "images": images[:MAX_IMAGES],
        "url": f"/wiki/{quote(title.replace(' ', '_'))}",
    }


# ---------- Import ----------

def find_wiki(series_name, session=None):
    for base in candidates(series_name):
        wiki = Wiki(base, session)
        if wiki.exists():
            return wiki
    return None


def fetch(series, base=None, session=None):
    """Lit les personnages du wiki de la série. Renvoie (et enregistre) wiki.json."""
    series = Path(series)
    wiki = Wiki(base, session) if base else find_wiki(series.name, session)
    if wiki is None or not wiki.exists():
        raise RuntimeError(f"Aucun wiki Fandom trouvé pour « {series.name} »")
    titles = wiki.category()
    pages = wiki.contents(titles)
    old = {c["title"]: c for c in (load_wiki(series) or {}).get("characters", [])}
    # les ids restent stables d'une mise à jour à l'autre : un personnage nommé reste lié
    next_id = max((int(c["id"][1:]) for c in old.values()), default=0) + 1
    chars = []
    for title in (t for t in titles if t in pages):
        c = parse_character(title, pages[title])
        before = old.get(title)
        if before:
            c["id"] = before["id"]
        else:
            c["id"], next_id = f"w{next_id}", next_id + 1
        # images déjà téléchargées : gardées tant que la page cite les mêmes fichiers
        c["files"] = before.get("files", []) if before and before.get("images") == c["images"] else []
        chars.append(c)
    data = {"base": wiki.base, "sitename": wiki.sitename(), "fetched": time.strftime("%Y-%m-%d"), "characters": chars}
    save_wiki(series, data)
    return data


# ---------- Images (vérification Cloudflare passée à la main) ----------

def _is_challenge(page):
    try:
        return "just a moment" in page.title().lower()
    except Exception:
        return False


def fetch_images(series, progress=None, say=print):
    """Télécharge les images des personnages dans une fenêtre de navigateur visible.

    Si Cloudflare demande une vérification, on attend qu'elle soit passée à la main dans
    cette fenêtre (jusqu'à 3 min), puis la même fenêtre récupère les images une à une.
    """
    from playwright.sync_api import sync_playwright

    series = Path(series)
    data = load_wiki(series)
    if not data:
        raise RuntimeError("Lis d'abord le wiki (noms des personnages)")
    wiki = Wiki(data["base"])
    files = sorted({f for c in data["characters"] for f in c.get("images", [])})
    urls = wiki.image_urls(files)
    todo = [(c, k, urls[f]) for c in data["characters"] for k, f in enumerate(c.get("images", []), 1) if f in urls]
    folder = wiki_dir(series)
    folder.mkdir(parents=True, exist_ok=True)
    saved = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_context().new_page()
        try:
            for i, (c, k, url) in enumerate(todo, 1):
                response = page.goto(url)
                if _is_challenge(page):
                    say(">>> Passe la vérification Cloudflare dans la fenêtre du navigateur (j'attends jusqu'à 3 min) <<<")
                    page.wait_for_function("!document.title.toLowerCase().includes('just a moment')", timeout=CHECK_TIMEOUT)
                    response = page.goto(url)
                if response and response.ok and response.headers.get("content-type", "").startswith("image/"):
                    name = f"{c['id']}-{k}.img"
                    (folder / name).write_bytes(response.body())
                    saved.setdefault(c["id"], []).append(name)
                if progress:
                    progress(i, len(todo))
        finally:
            browser.close()
    for c in data["characters"]:
        c["files"] = saved.get(c["id"], [])
    save_wiki(series, data)
    return sum(map(len, saved.values()))


def embed_wiki_faces(series, progress=None):
    """Repère les visages sur les images du wiki et les décrit comme ceux des chapitres."""
    import cv2
    import numpy as np

    from manhwa.faces import detect, embed, head_box
    from manhwa.images import read_image

    data = load_wiki(series)
    if not data:
        return 0
    folder = wiki_dir(series)
    owners, vecs = [], []
    files = [(c["id"], f) for c in data["characters"] for f in c.get("files", [])]
    for i, (cid, name) in enumerate(files, 1):
        img = read_image(folder / name)
        if img is not None:
            h, w = img.shape[:2]
            if w < 600:  # les détecteurs sont réglés pour des cases de manhwa (≈ 800 px de large)
                img = cv2.resize(img, (800, round(h * 800 / w)), interpolation=cv2.INTER_CUBIC)
                h, w = img.shape[:2]
            for box in detect(img):
                x, y, bw, bh = head_box(box, w, h)
                owners.append(cid)
                vecs.append(embed(img[y:y + bh, x:x + bw]))
        if progress:
            progress(i, len(files))
    tmp = folder / "faces.part.npz"
    np.savez(tmp, owners=np.array(owners), vecs=np.stack(vecs) if vecs else np.zeros((0, 384), np.float32))
    os.replace(tmp, folder / "faces.npz")
    return len(owners)


def wiki_vectors(series):
    """(personnage du wiki de chaque visage, vecteurs) : vide si les images n'ont pas été lues."""
    import numpy as np

    path = wiki_dir(series) / "faces.npz"
    if not path.is_file():
        return [], None
    with np.load(path) as z:
        return z["owners"].tolist(), z["vecs"]
