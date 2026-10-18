"""Ce qui est installé, et combien de temps prendra un épisode sur cette machine.

    python -m manhwa doctor

1. La machine : processeur, mémoire, carte graphique, place libre.
2. Chaque morceau du projet : prêt, ou ce qu'il faut faire (relancer Installer.bat…).
3. Une mesure de 10 s : la vitesse du processeur (des images déformées et floutées, comme au
   rendu) et de la carte graphique (calcul et mémoire), comparées à la machine de test.
4. L'estimation : la durée mesurée de chaque étape sur la machine de test, mise à l'échelle de
   cette machine ; une étape qui ne peut pas tourner ici est remplacée (voix de base…) ou sautée.
   C'est une estimation (± 30 %) : le Studio note la vraie durée de chaque étape dans sa console.
"""
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from manhwa.config import ROOT

TEST_MACHINE = "HP Victus 15 : Intel i5-13420H (8 cœurs), 16 Go, NVIDIA RTX 3050 Laptop 6 Go, SSD NVMe"
# la mesure de 10 s sur la machine de test (doctor.bench), pour comparer
REF_CPU = 275   # images par seconde
REF_TFLOPS = 17.2
REF_GBS = 155
MIN_VRAM = 5.5  # Go : les modèles locaux (Qwen, FLUX) sont réglés pour une carte de 6 Go

# (dossier, fichier qui dit « déjà là ») des modèles téléchargés par install/download_models.py
MODELS = {
    "tts": [("qwen3.5-2b", "model.safetensors.index.json"), ("clap-general", "config.json")],
    "qwen": [("qwen3-tts-design", "config.json")],
    "edit": [("flux2-klein-4b", os.path.join("transformer", "config.json"))],
}

# Les étapes de « Tout faire », mesurées sur l'épisode 1 de test (142 cases, 144 répliques) :
# (nom, secondes sur la machine de test, ce qui la ralentit, ce qu'il faut, et sinon : (à la place, secondes, sorte))
# sorte : "cpu" processeur, "gpu" carte graphique, "mix" les deux à moitié, "net" en ligne (GPT, Claude)
STEPS = [
    ("Frames, lecture du texte, filigranes effacés, visages", 100, "mix", "gpu",
     ("lecture du texte par le processeur", 300, "cpu")),
    ("Ce qui se passe dans les cases (Qwen3.5-2B)", 277, "gpu", "tts",
     ("décrit par GPT", 20, "net")),
    ("Relecture, voix, sons, lieux (GPT ou Claude)", 30, "net", "key", None),
    ("Visages qui parlent (FLUX.2 klein, ≈ 22 visages)", 858, "gpu", "edit", None),
    ("Voix (Qwen3-TTS, timbre de chaque personnage, réécoute)", 810, "gpu", "qwen",
     ("voix de base Kokoro, par le processeur", 100, "cpu")),
    ("Rendu de la vidéo (9 min)", 145, "mix", "gpu",
     ("rendu par le processeur", 185, "cpu")),
    ("Réécoute et découpe en parties TikTok", 68, "mix", "gpu",
     ("réécoute par le processeur", 115, "cpu")),
]


# ---------- La machine ----------

def machine():
    """Processeur, fils, mémoire (Go), carte NVIDIA et sa mémoire (Go), place libre (Go)."""
    info = {"cpu": _cpu_name(), "threads": os.cpu_count() or 1, "ram": _ram_gb(), "gpu": None, "vram": 0.0,
            "free": round(shutil.disk_usage(ROOT).free / 1e9)}
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=20).stdout.strip().splitlines()
            if out:
                name, mib = out[0].rsplit(",", 1)
                info["gpu"], info["vram"] = name.strip(), round(int(mib) / 1024, 1)
        except Exception:
            pass
    return info


def _cpu_name():
    if os.name == "nt":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except Exception:
            pass
    import platform

    return platform.processor() or "processeur inconnu"


def _ram_gb():
    if os.name == "nt":
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("avail", ctypes.c_ulonglong), ("pt", ctypes.c_ulonglong), ("pa", ctypes.c_ulonglong),
                        ("vt", ctypes.c_ulonglong), ("va", ctypes.c_ulonglong), ("ve", ctypes.c_ulonglong)]

        s = Status()
        s.length = ctypes.sizeof(Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
        return round(s.total / 2 ** 30, 1)
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1)
    except Exception:
        return 0.0


# ---------- Ce qui est installé ----------

def side_python(name):
    return ROOT / f".venv-{name}" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _side_env(name):
    """(prêt ?, détail) d'un environnement à part : là, torch voit la carte, modèles téléchargés."""
    exe = side_python(name)
    if not exe.is_file():
        return False, "absent : relance Installer.bat (profil complet)"
    try:
        out = subprocess.run([str(exe), "-c", "import torch; print(torch.cuda.is_available())"],
                             capture_output=True, text=True, timeout=120).stdout.strip()
    except Exception as e:
        return False, f"ne démarre pas ({e})"
    if out != "True":
        return False, "torch ne voit pas la carte graphique"
    missing = [f for f, marker in MODELS[name] if not (ROOT / ".cache" / "models" / f / marker).is_file()]
    return True, ("prêt" if not missing else f"prêt, modèles téléchargés au premier usage ({', '.join(missing)})")


def status():
    """Chaque morceau : {clé: (prêt ?, nom, détail)}."""
    from manhwa.config import load_env

    load_env()
    found = {}
    with ThreadPoolExecutor(max_workers=3) as pool:  # les trois environnements démarrent ensemble (≈ 5 s chacun)
        sides = {name: pool.submit(_side_env, name) for name in MODELS}
        try:
            from manhwa import scroll_gpu

            gpu = scroll_gpu.available()
        except Exception:
            gpu = False
        found["gpu"] = (gpu, "Carte graphique pour le texte et le rendu (Paddle CUDA)",
                        "prête" if gpu else "absente : tout passe par le processeur, en plus lent")
        try:
            from manhwa.render import encoder

            nvenc = encoder("auto") == "h264_nvenc"
        except Exception:
            nvenc = False
        found["nvenc"] = (nvenc, "Encodage vidéo par la carte (NVENC)", "prêt" if nvenc else "par le processeur (x264)")
        browsers = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
        chromium = os.path.isdir(browsers) and any(n.startswith("chromium") for n in os.listdir(browsers))
        found["browser"] = (chromium, "Navigateur pour télécharger les chapitres (Chromium)",
                            "prêt" if chromium else "absent : .venv\\Scripts\\python -m playwright install chromium")
        labels = {"tts": "Ce qui se passe dans les cases, sons, voix de secours (.venv-tts)",
                  "qwen": "Voix qui jouent l'émotion, Qwen3-TTS (.venv-qwen)",
                  "edit": "Visages qui parlent, FLUX.2 klein (.venv-edit)"}
        for name, job in sides.items():
            ok, detail = job.result()
            found[name] = (ok, labels[name], detail)
    bank = (ROOT / ".cache" / "soundbank" / "index.json").is_file()
    found["sounds"] = (bank, "Bruitages et ambiances pro (Sonniss)",
                       "prêts" if bank else "absents : .venv\\Scripts\\python -m manhwa.soundbank --download")
    key = bool(os.environ.get("DAILY_OPENAI_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
    found["key"] = (key, "Clé GPT ou Claude", "présente" if key else "absente : à coller dans les Réglages du Studio (roue dentée)")
    return found


# ---------- La mesure de 10 s ----------

def bench_cpu(seconds=3.0):
    """Images 1080×1920 déformées puis floutées par seconde, sur autant de fils que le rendu."""
    import cv2
    import numpy as np

    img = np.random.default_rng(0).integers(0, 255, (1920, 1080, 3), dtype=np.uint8)
    warp = np.float32([[1.03, 0.01, -12], [-0.01, 1.03, -20]])
    threads = max(1, min(8, (os.cpu_count() or 2) - 2))  # comme render.run_render

    def one(_):
        out = cv2.warpAffine(img, warp, (1080, 1920), flags=cv2.INTER_LINEAR)
        return int(cv2.GaussianBlur(out, (9, 9), 0)[0, 0, 0])

    before = cv2.getNumThreads()
    cv2.setNumThreads(1)
    try:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            list(pool.map(one, range(threads)))  # mise en route
            done, start = 0, time.perf_counter()
            while time.perf_counter() - start < seconds:
                done += len(list(pool.map(one, range(threads * 4))))
            return done / (time.perf_counter() - start)
    finally:
        cv2.setNumThreads(before)


def bench_gpu():
    """(TFLOPS en 16 bits, Go/s de mémoire) de la carte, par Paddle ; None sans carte."""
    try:
        from manhwa import scroll_gpu

        if not scroll_gpu.available():
            return None
        import paddle

        paddle.set_device("gpu:0")
        a = paddle.randn([4096, 4096]).astype("float16")
        for _ in range(30):  # mise en route : la carte monte en fréquence
            paddle.matmul(a, a)
        paddle.device.synchronize()
        n, start = 20, time.perf_counter()
        for _ in range(n):
            paddle.matmul(a, a)
        paddle.device.synchronize()
        tflops = n * 2 * 4096 ** 3 / (time.perf_counter() - start) / 1e12
        x = paddle.zeros([64 * 2 ** 20], dtype="float32")  # 256 Mo, lus puis écrits
        (x * 1.5).numpy()[:1]
        paddle.device.synchronize()
        n, start = 20, time.perf_counter()
        for _ in range(n):
            y = x * 1.5
        paddle.device.synchronize()
        gbs = n * 2 * x.numel().item() * 4 / (time.perf_counter() - start) / 1e9
        del a, x, y
        return tflops, gbs
    except Exception:
        return None


def factors(cpu_speed, gpu_speed):
    """(processeur, carte) : combien de fois plus vite que la machine de test (carte : None sans carte)."""
    cpu = cpu_speed / REF_CPU
    if not gpu_speed:
        return cpu, None
    tflops, gbs = gpu_speed
    return cpu, ((tflops / REF_TFLOPS) * (gbs / REF_GBS)) ** 0.5  # calcul et mémoire comptent autant


# ---------- L'estimation ----------

def estimate(found, cpu, gpu, vram):
    """[(étape, secondes ou None si sautée, comment)] pour un épisode comme celui de test."""
    big = gpu is not None and vram >= MIN_VRAM

    def scale(seconds, kind):
        if kind == "net":
            return seconds
        if kind == "cpu" or gpu is None:
            return seconds / cpu
        if kind == "gpu":
            return seconds / gpu
        return seconds * (0.5 / cpu + 0.5 / gpu)

    rows = []
    for name, seconds, kind, needs, instead in STEPS:
        if needs == "gpu":
            ready = found["gpu"][0]
        elif needs == "key":
            ready = found["key"][0]
        else:
            ready = found[needs][0] and big and (needs != "qwen" or found["tts"][0])  # la voix passe aussi par .venv-tts
        if ready:
            rows.append((name, scale(seconds, kind), "ici"))
        elif instead and (instead[2] != "net" or found["key"][0]):
            rows.append((name, scale(instead[1], instead[2]), instead[0]))
        else:
            rows.append((name, None, "sautée"))
    return rows


def _minutes(seconds):
    m = seconds / 60
    return f"≈ {m:.0f} min" if m >= 1.5 else ("≈ 1 min" if m >= 0.75 else "< 1 min")


def main(bench=True):
    import warnings

    os.environ.setdefault("GLOG_minloglevel", "2")  # Paddle : pas ses messages de démarrage
    warnings.filterwarnings("ignore")
    info = machine()
    print("Machine")
    print(f"  Processeur   {info['cpu']} ({info['threads']} fils)")
    print(f"  Mémoire      {info['ram']:.0f} Go")
    print(f"  Carte        {info['gpu'] + f', {info['vram']:.0f} Go' if info['gpu'] else 'pas de carte NVIDIA'}")
    print(f"  Disque       {info['free']} Go libres")
    print()
    print("Installé")
    found = status()
    for ok, label, detail in found.values():
        print(f"  {'✔' if ok else '✘'} {label} : {detail}")
    if not bench:
        return
    print()
    print("Vitesse (mesurée en 10 s, comparée à la machine de test)")
    cpu, gpu = factors(bench_cpu(), bench_gpu())
    print(f"  Processeur   {cpu:.2f} ×")
    print(f"  Carte        {f'{gpu:.2f} ×' if gpu else '—'}")
    print()
    print("Un épisode de ≈ 140 cases avec « Tout faire », estimé pour cette machine")
    rows = estimate(found, cpu, gpu, info["vram"])
    for name, seconds, how in rows:
        when = _minutes(seconds) if seconds is not None else "—"
        print(f"  {name:<58} {when:>10}   {'' if how == 'ici' else how}")
    total = sum(s for _, s, _ in rows if s is not None)
    ref = sum(s for _, s, _, _, _ in STEPS)
    print(f"  {'Total':<58} {_minutes(total):>10}   (machine de test : {_minutes(ref)})")
    print(f"\n  Machine de test : {TEST_MACHINE}.")
    print("  La première fois, ajoute le téléchargement des modèles (≈ 28 Go en profil complet).")
