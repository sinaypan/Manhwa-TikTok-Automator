"""Télécharge les bruitages et ambiances Sonniss utiles, sans télécharger les archives entières.

Les « GDC Game Audio Bundles » de Sonniss sont gratuits et libres de droits : usage commercial
et vidéos monétisées permis, sans crédit. Deux interdits : redistribuer les sons (ils restent
dans .cache/, jamais commités) et s'en servir pour entraîner une IA (on ne fait que les écouter).

Les archives font 100 Go. On lit leur sommaire à distance (requêtes HTTP partielles), on choisit
d'après le nom des fichiers (coups, lames, sang, ambiances de forêt, de grotte…), et on ne
télécharge que ceux-là ; pour un son long, seulement son début (une ambiance : 25 s).

Source : le miroir officiel que Sonniss indique pour 2015 à 2019 (ftpmirror.your.org). Le site
principal passe par une vérification Cloudflare : on ne la contourne pas.

    python -m manhwa.soundbank --download    télécharge (≈ 2 Go), puis prépare la bibliothèque
"""
import collections
import io
import json
import os
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor

from manhwa.config import ROOT

MIRROR = "https://ftpmirror.your.org/pub/misc/"
YEARS = ("2015", "2016", "2017", "2018", "2019")
AUDIO = (".wav", ".flac")
# bruitages : les packs entiers qui servent, et les noms de fichiers qui parlent de bruitages utiles
PACKS = r"3maze - High Impact|Bottle Rocket Fx - Impact Collection|Just Gore|Just Whoosh 3|Wooden Staffs and Sword Fight"
SFX = (r"punch|fist|body ?hit|kick\b|impact|hit\b|thud|thump|body ?fall|bodyfall|slam|slash|sword|blade|knife|stab|slice|"
       r"unsheath|sheath|clang|clash|blood|gore|splat|squelch|flesh|bone|whoosh|swoosh|swish|woosh|footstep|cloth|fabric|"
       r"door|fire|flame|thunder|lightning|explosion|explode|magic|spell|heartbeat|heart ?beat|glass|shatter|bell|gong|"
       r"laser|energy|coin|paper|book|crack")
EXTRA = (r"stethoscope.*heart|wind,.*(howl|gust|rushing)|wind gust|gusts|metal.*(clang|hit|crash)|chain.*(rattle|hit|move)|"
         r"bodyfall|body fall|cloth.*(move|rustle|flap)|fabric|bell.*(ring|hit)|gong|wood.*(break|crack|snap|hit)")
EXTRA_NOT = r"engine|chainsaw|xylophone|toy|cartoon|construction"
SFX_MAX = 8_000_000  # un bruitage plus gros est sans doute une longue prise : on n'en lit que le début
# ambiances, par thème (6 au plus chacun)
AMBIENCE = ["prison|dungeon|cell", "cave", "interior|room ?tone|roomtone", "castle|temple|hall", "tavern|inn|walla",
            "forest", "wind", "night|insects|cricket", "rain", "storm|thunder", "crowd|market",
            "village|countryside|courtyard", "fireplace|campfire|fire", "mountain", "river|stream|water", "birds"]
AMBIENCE_ANY = (r"ambien|ambiance|room ?tone|roomtone|atmos|interior|forest|wind|rain|crowd|market|tavern|village|night|"
                r"cave|dungeon|prison|cell|courtyard|street|countryside|birds|insects|fireplace|campfire|storm|temple|"
                r"hall|castle|mountain|river|walla")
AMBIENCE_NOT = (r"car |vehicle|engine|sci-?fi|spaceship|robot|laser|gun|drone|train|airport|office|city traffic|highway|"
                r"motorcycle|subway|truck|computer|electr|hum\b|dodge|ferrari|camaro|construction|amsterdam|savannah|"
                r"urban|city|traffic|surreal|dreamscape")


def raw_dir():
    return ROOT / ".cache" / "sonniss" / "raw"


def ambience_dir():
    return ROOT / ".cache" / "sonniss" / "ambience"


class RangeFile(io.RawIOBase):
    """Un fichier distant lu par morceaux (requêtes Range) : zipfile n'en lit que ce qu'il lui faut."""

    def __init__(self, url, session):
        self.url, self.s, self.pos = url, session, 0
        self.size = int(session.head(url, timeout=60).headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def tell(self):
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size or not len(b):
            return 0
        end = min(self.size, self.pos + len(b)) - 1
        data = self.s.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=120).content
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)


def _zip(url):
    import requests

    return zipfile.ZipFile(io.BufferedReader(RangeFile(url, requests.Session()), buffer_size=1 << 22))


def archives():
    """Les zips du miroir officiel."""
    import requests

    urls = []
    for year in YEARS:
        html = requests.get(f"{MIRROR}sonniss{year}/", timeout=60).text
        urls += [f"{MIRROR}sonniss{year}/{h}" for h in re.findall(r'href="([^"]+\.zip)"', html)]
    return urls


def catalog(progress=None):
    """[(zip, fichier, taille compressée)] de toutes les archives (le sommaire seulement, quelques Mo)."""
    urls = archives()

    def one(u):
        try:
            return [(u, i.filename, i.compress_size) for i in _zip(u).infolist() if not i.is_dir()]
        except Exception as e:
            print(f"  [!] Sommaire illisible : {u.rsplit('/', 1)[-1]} ({e})")
            return []

    out = []
    with ThreadPoolExecutor(4) as ex:
        for k, files in enumerate(ex.map(one, urls)):
            out += files
            if progress:
                progress(k + 1, len(urls))
    return out


def choose(files):
    """{"sfx": [...], "ambience": [...]} : ce qui vaut la peine d'être téléchargé."""
    def base(n):
        return n.rsplit("/", 1)[-1].lower()

    seen, sfx = set(), []
    for u, n, c in files:
        low = n.lower()
        if not low.endswith(AUDIO) or base(n) in seen:
            continue
        pack = n.split("/")[0]
        hit = re.search(PACKS, pack) or re.search(SFX, base(n))
        extra = re.search(EXTRA, low) and not re.search(EXTRA_NOT, low)
        if (hit and c <= SFX_MAX) or extra:
            seen.add(base(n))
            sfx.append((u, n, c))
    amb = [(u, n, c) for u, n, c in files if n.lower().endswith(AUDIO) and re.search(AMBIENCE_ANY, n.lower())
           and not re.search(AMBIENCE_NOT, n.lower()) and 8e6 <= c <= 70e6]
    chosen, used = [], set()
    for theme in AMBIENCE:
        hits = [x for x in sorted(amb, key=lambda x: x[2]) if re.search(theme, x[1].lower()) and base(x[1]) not in used][:6]
        used.update(base(h[1]) for h in hits)
        chosen += hits
    return {"sfx": sfx, "ambience": chosen}


def _safe(name):
    return "".join(ch if ch.isalnum() or ch in " ._-()&" else "_" for ch in name).strip()


def _read_start(z, name, seconds):
    """Le début d'un .wav (seconds), sans décompresser le reste : ffmpeg lit un .wav coupé sans souci."""
    with z.open(name) as f:
        head = f.read(64)
        rate = int.from_bytes(head[24:28], "little")
        bits = int.from_bytes(head[34:36], "little")
        ch = int.from_bytes(head[22:24], "little")
        if not (8000 <= rate <= 192000 and ch in (1, 2, 4, 6) and bits in (16, 24, 32)):  # en-tête BWF : on ne sait pas
            rate, ch, bits = 96000, 2, 24
        return head + f.read(min(int(seconds * rate * ch * bits / 8), 20_000_000))


def fetch(items, folder, seconds=None, progress=None):
    """Télécharge les fichiers choisis (ou leur début) dans folder/<pack>/. Renvoie le nombre de fichiers prêts."""
    by = collections.defaultdict(list)
    for u, n, c in items:
        by[u].append((n, c))
    done = [0]

    def one(u):
        z = _zip(u)
        for n, c in by[u]:
            dest = folder / _safe(n.split("/")[0]) / _safe(n.split("/")[-1])
            if dest.is_file():
                done[0] += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = _read_start(z, n, seconds or 12) if seconds or c > SFX_MAX else z.read(n)
            except Exception as e:
                print(f"  [!] {n.rsplit('/', 1)[-1]} : {e}")
                continue
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            done[0] += 1
            if progress:
                progress(done[0], len(items))

    with ThreadPoolExecutor(4) as ex:
        list(ex.map(one, list(by)))
    return done[0]


def download(progress=None):
    """Tout : le sommaire, le choix, les bruitages (12 s au plus pour une longue prise) et les ambiances (25 s)."""
    print("  Lecture des sommaires Sonniss…")
    picked = choose(catalog())
    (ROOT / ".cache" / "sonniss").mkdir(parents=True, exist_ok=True)
    (ROOT / ".cache" / "sonniss" / "choisis.json").write_text(json.dumps(picked, ensure_ascii=False), encoding="utf-8")
    print(f"  {len(picked['sfx'])} bruitages et {len(picked['ambience'])} ambiances à télécharger")
    n = fetch(picked["sfx"], raw_dir(), progress=progress)
    m = fetch(picked["ambience"], ambience_dir(), seconds=25, progress=progress)
    return n, m
