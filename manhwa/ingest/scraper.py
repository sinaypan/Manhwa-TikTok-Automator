"""Téléchargement des chapitres d'une série vers inbox/<série>/chapter-NNN/pages/.

La vérification anti-robot (Cloudflare) reste manuelle : la fenêtre du navigateur
s'ouvre, tu la passes toi-même, et le téléchargement reprend tout seul.
"""
import mimetypes
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from manhwa.config import inbox_dir
from manhwa.images import dominant_width
from manhwa.project import PAGES_DIR

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)
COMPLETE_MARKER = ".complete"
_CHAPTER_RE = re.compile(r"chap(?:ter|itre)?[\s_\-/.]*(\d+(?:[.\-]\d+)?)", re.IGNORECASE)


# ---------- Numéros de chapitre ----------

def chapter_number(url, text=""):
    """Numéro du chapitre d'après l'URL (prioritaire) ou le texte du lien, sinon None.

    "…/chapter/12" → 12.0 ; "…/chapter-12-5" → 12.5 ; "Chapter 7" → 7.0
    """
    for source in (urlparse(url).path, text or ""):
        matches = _CHAPTER_RE.findall(source)
        if matches:
            return float(matches[-1].replace("-", "."))
    return None


def chapter_dirname(number):
    """12.0 → "chapter-012", 12.5 → "chapter-012.5" (tri correct dans l'explorateur)."""
    whole, _, frac = f"{number:g}".partition(".")
    return f"chapter-{int(whole):03d}" + (f".{frac}" if frac else "")


def unique_chapters(links):
    """[(url, texte)] → [(numéro, url)] triés par numéro, un seul lien par chapitre."""
    by_number = {}
    for url, text in links:
        n = chapter_number(url, text)
        if n is not None and n not in by_number:
            by_number[n] = url
    return sorted(by_number.items())


def parse_selection(spec, numbers):
    """Choix des chapitres : "" (le premier), "all", "latest", "12", "1-5", "1-5,8,10-12"."""
    numbers = sorted(numbers)
    spec = (spec or "").strip().lower()
    if not numbers:
        return []
    if spec == "":
        return numbers[:1]
    if spec == "all":
        return numbers
    if spec == "latest":
        return numbers[-1:]
    chosen = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        lo, sep, hi = part.partition("-")
        try:
            lo = float(lo)
            hi = float(hi) if sep else lo
        except ValueError:
            raise ValueError(f"Sélection invalide : {part!r} (exemples : 12, 1-5, 1-5,8, all, latest)")
        chosen.update(n for n in numbers if lo <= n <= hi)
    return sorted(chosen)


def sanitize_filename(name):
    clean = "".join(c for c in name if c.isalnum() or c in " -_").strip()
    return re.sub(r"\s+", " ", clean) or "Manhwa"


def site_profile(cfg, url):
    sites = cfg["scraper"]["sites"]
    host = urlparse(url).netloc.lower()
    for name, profile in sites.items():
        if name != "default" and any(d.lower() in host for d in profile.get("domains", [])):
            return name, {**sites["default"], **profile}
    return "default", sites["default"]


# ---------- Téléchargement ----------

def create_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def page_stem(index, total):
    """Noms à largeur fixe (001, 002 … 120) : l'ordre alphabétique = l'ordre de lecture."""
    return f"{index:0{max(3, len(str(total)))}d}"


def _existing(folder, stem):
    return any(p.stem == stem for p in folder.iterdir() if not p.name.endswith(".part"))


def download_image(session, url, folder, stem, referer, timeout):
    if _existing(folder, stem):
        return True
    try:
        response = session.get(url, stream=True, timeout=timeout, headers={"Referer": referer})
        if response.status_code != 200:
            print(f"  [!] HTTP {response.status_code} : {url}")
            return False
        if ".webp" in urlparse(url).path.lower():
            ext = ".webp"
        else:
            ctype = (response.headers.get("content-type") or "").split(";")[0].strip()
            ext = mimetypes.guess_extension(ctype) or ".jpg"
        tmp = folder / f"{stem}{ext}.part"
        with open(tmp, "wb") as f:
            for chunk in response.iter_content(65536):
                f.write(chunk)
        os.replace(tmp, folder / f"{stem}{ext}")
        return True
    except Exception as e:
        print(f"  [!] Échec {url} : {e}")
        return False


def smart_scroll(page, max_rounds=60):
    """Descend jusqu'en bas pour charger les images paresseuses (lazy loading)."""
    last_height = page.evaluate("document.body.scrollHeight")
    for _ in range(max_rounds):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            time.sleep(1)
        height = page.evaluate("document.body.scrollHeight")
        if height == last_height:
            return
        last_height = height


IMAGES_JS = """([minWidth, exts]) => Array.from(document.querySelectorAll('img'))
    .map(img => ({src: img.currentSrc || img.src, width: img.naturalWidth, height: img.naturalHeight}))
    .filter(img => img.width > minWidth && img.src.startsWith('http')
        && (exts.length === 0 || exts.some(e => new URL(img.src).pathname.toLowerCase().endsWith(e))))"""


def keep_page_images(found, tolerance=0.10):
    """Garde seulement les pages du chapitre, dans l'ordre, sans doublons.

    Autour du lecteur, la page web contient couverture, bannières et vignettes
    (recommandations, commentaires). Les vraies pages ont toutes la même largeur :
    celle qui couvre le plus de hauteur. On écarte ce qui s'en éloigne de plus de 10 %.
    """
    unique = list({img["src"]: img for img in found}.values())
    width = dominant_width([(img["width"], img["height"]) for img in unique])
    if width is None:
        return []
    return [img["src"] for img in unique if abs(img["width"] - width) <= tolerance * width]


def chapter_images(page, profile):
    found = page.evaluate(IMAGES_JS, [profile["image_min_width"], [e.lower() for e in profile["image_extensions"]]])
    urls = keep_page_images(found)
    if len(urls) < len({img["src"] for img in found}):
        print(f"  {len({img['src'] for img in found}) - len(urls)} images hors chapitre écartées (bannières, vignettes).")
    return urls


def series_title(page, profile):
    try:
        el = page.query_selector(profile["title"])
        text = el.inner_text().strip() if el else ""
        # un vrai titre a des lettres ("98" est une note ou un compteur, pas un titre)
        if sum(c.isalpha() for c in text) >= 3:
            return sanitize_filename(text)
    except Exception:
        pass
    # repli : le titre de l'onglet, avant le premier séparateur
    return sanitize_filename(re.split(r"\s[|\-–]\s", page.title() or "")[0])


def download_series(url, cfg, selection=None, series=None, force=False):
    from playwright.sync_api import sync_playwright

    sc = cfg["scraper"]
    site_name, profile = site_profile(cfg, url)
    print(f"Profil de site : {site_name}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=sc["headless"])
        page = browser.new_context().new_page()
        print(f"Connexion à {url} ...")
        page.goto(url)
        try:
            page.wait_for_selector(profile["chapter_links"], state="attached", timeout=8000)
        except Exception:
            # pas d'Entrée à taper : on reprend tout seul dès que la page de la série est là
            print(">>> Passe la vérification dans la fenêtre du navigateur (j'attends jusqu'à 3 min) <<<")
            try:
                page.wait_for_selector(profile["chapter_links"], state="attached", timeout=180_000)
            except Exception:
                print("Page de la série introuvable : vérification non passée, ou sélecteur chapter_links à revoir.")
                browser.close()
                return []

        title = sanitize_filename(series) if series else series_title(page, profile)
        links = page.eval_on_selector_all(profile["chapter_links"], "els => els.map(e => [e.href, e.innerText])")
        chapters = unique_chapters((urljoin(page.url, href), text) for href, text in links)
        if not chapters:
            print("Aucun chapitre trouvé : vérifie le sélecteur chapter_links dans config.toml.")
            browser.close()
            return []

        numbers = [n for n, _ in chapters]
        print(f"Série : {title} — {len(chapters)} chapitres ({numbers[0]:g} → {numbers[-1]:g}).")
        if selection is None:
            selection = input("Chapitres à télécharger (ex : 12, 1-5, 1-5,8, all, latest) [premier] : ")
        wanted = set(parse_selection(selection, numbers))

        series_dir = inbox_dir(cfg) / title
        session = create_session()
        done = []
        for number, ch_url in chapters:
            if number not in wanted:
                continue
            ch_dir = series_dir / chapter_dirname(number)
            pages_dir = ch_dir / PAGES_DIR
            if (pages_dir / COMPLETE_MARKER).is_file() and not force:
                print(f"--- Chapitre {number:g} : déjà téléchargé, ignoré.")
                done.append(ch_dir)
                continue

            print(f"--- Chapitre {number:g}")
            try:
                page.goto(ch_url)
                smart_scroll(page)
                urls = chapter_images(page, profile)
            except Exception as e:
                print(f"  [!] Erreur de chargement : {e}")
                continue
            if not urls:
                print("  [!] Aucune image trouvée : le site a peut-être changé (voir image_extensions dans config.toml).")
                continue

            if force and pages_dir.is_dir():
                shutil.rmtree(pages_dir)  # sinon les anciennes pages 001… seraient gardées
            pages_dir.mkdir(parents=True, exist_ok=True)
            print(f"  {len(urls)} images.")
            with ThreadPoolExecutor(max_workers=sc["workers"]) as pool:
                results = list(pool.map(
                    lambda item: download_image(session, item[1], pages_dir, page_stem(item[0], len(urls)),
                                                ch_url, sc["timeout_seconds"]),
                    enumerate(urls, start=1),
                ))
            failed = results.count(False)
            if failed:
                print(f"  [!] {failed} images en échec : relance la même commande pour les reprendre.")
            else:
                (pages_dir / COMPLETE_MARKER).write_text(f"{len(urls)}\n", encoding="utf-8")
                print(f"  OK → {ch_dir}")
                done.append(ch_dir)

        browser.close()
    print("Téléchargement terminé.")
    return [Path(d) for d in done]
