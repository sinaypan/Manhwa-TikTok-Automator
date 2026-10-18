# Manhwa TikTok Automator

**Un lien de chapitre en entrée, une vidéo verticale doublée en sortie, déjà coupée en parties pour TikTok et YouTube Shorts.**

Le Studio, une page web qui tourne sur ton PC, fait tout le travail : il télécharge le chapitre, lit le texte, reconnaît les
personnages, leur donne une voix qui joue l'émotion, fait bouger leur bouche, ajoute les bruitages, l'ambiance et la musique.
Il fait ensuite défiler la planche comme sur un téléphone, avec des sous-titres karaoké. Quand il est sûr, il décide seul.
Quand il doute, il te demande, un clic à la fois.

Tout tourne en local et gratuitement. GPT ou Claude, facultatifs, aident pour la relecture et le choix des voix et des sons.
Chaque modèle a une licence qui permet une chaîne monétisée (voir [Modèles et licences](#modèles-et-licences)).

**Sommaire :** [Ce que ça fait](#ce-que-ça-fait) · [Installation](#installation) · [Premier épisode](#premier-épisode) ·
[Combien de temps](#combien-de-temps) · [Comment c'est rangé](#comment-cest-rangé) · [Modèles et licences](#modèles-et-licences) ·
[Guide complet du Studio](docs/GUIDE.md)

## Ce que ça fait

| | Étape | Avec quoi |
|---|---|---|
| 1 | **Télécharge le chapitre** depuis le lien de la série. Une vérification anti-robot se passe à la main, une fois. | Playwright (Chromium) |
| 2 | **Découpe la planche** en cases et repère les bulles. | Règles d'image, détecteur de bulles |
| 3 | **Lit le texte**, recolle les mots, écarte filigranes et onomatopées, puis le fait relire. | PaddleOCR, correction locale, GPT |
| 4 | **Reconnaît les personnages** d'une case à l'autre et d'un épisode à l'autre, avec leurs noms tirés du wiki. | Détecteurs deepghs, CCIP, wiki Fandom |
| 5 | **Comprend chaque case** (« il est projeté contre un mur, du sang gicle »). | Qwen3.5-2B |
| 6 | **Donne une voix à chaque personnage**, qui joue l'émotion de chaque réplique, puis la réécoute pour vérifier. | Qwen3-TTS, Chatterbox, Whisper |
| 7 | **Ajoute bruitages, ambiances et musique**, au bon volume, selon le lieu et la force du moment. | GPT, CLAP, sons Sonniss |
| 8 | **Fait parler les visages** : la bouche bat à chaque syllabe et les yeux clignent. | FLUX.2 [klein] 4B |
| 9 | **Monte la vidéo** : la planche défile, relief, tremblement sur les coups, sous-titres karaoké. | Depth Anything V2, rendu sur la carte graphique |
| 10 | **Coupe en parties de 60 à 90 s** sur un moment de suspense, avec un titre et des hashtags. | Rythme du récit, GPT |

## Installation

**Il te faut :**
- Windows 10 ou 11 ;
- une connexion internet ;
- de la place sur le disque : environ **50 Go** pour l'installation complète, **5 Go** pour la légère ;
- conseillé : une carte graphique **NVIDIA de 6 Go ou plus**. Sans elle, tout marche quand même, en profil léger.

Pas besoin d'installer Python ni autre chose : l'installateur s'en occupe.

### En une ligne

Ouvre **PowerShell** (touche Windows, tape « PowerShell », Entrée), colle cette ligne, puis Entrée :

```powershell
irm https://raw.githubusercontent.com/sinaypan/Manhwa-TikTok-Automator/main/install/get.ps1 | iex
```

Ensuite, plus rien à faire :
- le projet se télécharge dans `C:\Users\<toi>\Manhwa Studio` (hors OneDrive, pour ne pas synchroniser 28 Go de modèles) ;
- le profil qui convient à ta carte graphique est choisi tout seul (voir le tableau plus bas) ;
- tout s'installe, puis le Studio s'ouvre.

Pour **mettre à jour**, relance la même ligne. Ce que fait le script est lisible dans [install/get.ps1](install/get.ps1).

### Ou en trois gestes

1. **Télécharge le projet** : bouton vert **Code** → **Download ZIP**, puis extrais-le où tu veux. Si tu as Git :
   ```bash
   git clone https://github.com/sinaypan/Manhwa-TikTok-Automator.git
   ```
2. **Double-clique sur `Installer.bat`**, puis choisis un profil (Entrée prend celui qui convient à ta carte) :

   | | Complet | Léger |
   |---|---|---|
   | Pour qui | Une carte NVIDIA de 6 Go ou plus | N'importe quel PC |
   | Voix | Voix décrites qui jouent l'émotion (Qwen3-TTS) | Voix de base (Kokoro, edge-tts) |
   | Visages qui parlent | Oui | Non |
   | Ce qui se passe dans les cases | Regardé en local (Qwen3.5-2B) | Par GPT, si tu as une clé |
   | Bruitages pro (Sonniss) | Oui | Sons de base |
   | Place sur le disque | ≈ 50 Go | ≈ 5 Go |

3. **Double-clique sur « Manhwa Studio »**, sur le Bureau. Le Studio s'ouvre dans le navigateur.
   Si tu as une clé GPT ou Claude (facultatif), colle-la dans les **Réglages** (roue dentée en haut à gauche).

**Combien de temps dure l'installation :** surtout le téléchargement. Le profil complet télécharge environ **36 Go** :
5 Go de bibliothèques, 28 Go de modèles et 2 Go de bruitages.

| Connexion | Complet | Léger |
|---|---|---|
| 100 Mb/s | ≈ 55 min | ≈ 5 min |
| 300 Mb/s | ≈ 20 min | ≈ 3 min |
| Fibre 1 Gb/s | ≈ 12 min | ≈ 2 min |

Une fois les fichiers téléchargés, l'installation elle-même prend environ 1 min. C'est mesuré sur une copie neuve du projet,
dans les deux profils.

**Mettre à jour :** relance la ligne PowerShell, ou télécharge la nouvelle version (ou `git pull`) et relance `Installer.bat`. Tes chapitres (`inbox/`),
ta clé (`.env`) et les modèles déjà téléchargés (`.cache/`) sont gardés.

**Vérifier que tout est prêt** (l'installateur le fait à la fin) :

```bash
.venv\Scripts\python -m manhwa doctor
```

La commande affiche ta machine et ce qui est installé, avec ce qu'il faut faire pour ce qui manque. Elle mesure aussi en 10 s la
vitesse de ton processeur et de ta carte, puis estime **combien de temps prendra un épisode chez toi**.

<details>
<summary>Options de l'installateur, et installation à la main</summary>

```bash
Installer.bat -Profil complet
```
```bash
Installer.bat -Profil leger
```
```bash
Installer.bat -SansModeles
```
```bash
Installer.bat -SansSons
```

- `-Profil` choisit sans poser la question.
- `-SansModeles` : les modèles se téléchargent au premier usage, plutôt que pendant l'installation.
- `-SansSons` : sans la bibliothèque Sonniss.
- `-SansCarte` : installe comme sur un PC sans carte NVIDIA.

Les versions exactes de chaque environnement sont dans [install/](install/), figées sur la machine de test. À la main, avec
[uv](https://docs.astral.sh/uv/) :

```bash
uv venv --python 3.12 .venv
uv pip sync --python .venv\Scripts\python.exe install\lock-main-gpu.txt --extra-index-url https://www.paddlepaddle.org.cn/packages/stable/cu126/ --index-strategy unsafe-best-match
.venv\Scripts\python -m playwright install chromium
```

Sans carte NVIDIA, la deuxième ligne devient `uv pip install --python .venv\Scripts\python.exe -r requirements.txt` (puis
`uv pip install --no-deps kokoro-onnx==0.6.1`). Les modèles locaux vivent chacun dans leur environnement (`.venv-tts`,
`.venv-qwen`, `.venv-edit`), pour que leurs bibliothèques ne se gênent pas. Chacun s'installe avec `uv venv` puis
`uv pip sync install\lock-<nom>.txt --extra-index-url https://download.pytorch.org/whl/cu124 --index-strategy unsafe-best-match`.

Tesseract est facultatif : c'est un troisième moteur de lecture, `[ocr] engine = "tesseract"`.
</details>

## Premier épisode

1. Dans le Studio, **Ajouter des chapitres** (en haut à gauche) : colle le lien de la série et le numéro du chapitre. Si le site
   affiche une vérification anti-robot, passe-la dans la fenêtre qui s'ouvre. La suite continue toute seule.
2. Le Studio enchaîne **Tout faire** : texte, personnages, voix, sons, visages qui parlent, vidéo, parties. Compte environ
   40 min sur la machine de test (voir [Combien de temps](#combien-de-temps)). Tu peux fermer le navigateur : le travail continue
   tant que la fenêtre noire du Studio reste ouverte.
3. Réponds à ce que le Studio te demande, s'il doute :
   - qui parle ;
   - un son ;
   - un visage animé : **C'est bon**, **Pas animé** ou **Redessiner**.

   Tout ce qu'il a décidé seul est marqué « d'office » et se change d'un clic.
4. **Onglet Vidéo** : regarde la vidéo. Un passage cloche ? Un clic sur la raison au bon moment, puis **Corriger** ouvre le bon
   onglet sur la bonne case.
5. **Découper** : les parties TikTok sont dans `<chapitre>/parts/`. **Copier** met le titre et les hashtags dans le
   presse-papiers.

Le mode d'emploi détaillé, onglet par onglet, est dans le **[Guide du Studio](docs/GUIDE.md)**.

## Combien de temps

### La machine de test

| | |
|---|---|
| Ordinateur | HP Victus 15 (portable) |
| Processeur | Intel Core i5-13420H, 8 cœurs / 12 fils |
| Mémoire | 16 Go |
| Carte graphique | NVIDIA GeForce RTX 3050 Laptop, **6 Go** |
| Disque | SSD NVMe |
| Système | Windows 11 |

### Mesuré : un épisode complet

Un épisode neuf de 142 cases et 144 répliques, en profil complet avec « Tout faire ». Il donne une vidéo de 9 min, coupée en
8 parties.

| Étape | Durée |
|---|---|
| Frames, lecture du texte, visages | ≈ 1 min |
| Ce qui se passe dans les cases (Qwen3.5-2B, 6 cases à la fois) | ≈ 4,5 min |
| Relecture, voix, sons, lieux (GPT ou Claude) | < 1 min |
| Visages qui parlent (22 visages, 4 dessins chacun) | ≈ 14 min |
| Voix (Qwen3-TTS, puis le timbre de chaque personnage, réécoute comprise) | ≈ 13,5 min |
| Rendu de la vidéo (images calculées et encodées par la carte graphique) | ≈ 2,5 min |
| Réécoute et découpe en parties | ≈ 1 min |
| **Total** | **≈ 38 min** |

Les modèles se téléchargent une fois, à l'installation. Chaque étape garde ce qu'elle a fait : relancée, elle ne refait que ce
qui a changé, et une étape coupée en route reprend là où elle s'était arrêtée. Le Studio note la vraie durée de chaque étape
dans sa console.

### Estimé : d'autres machines

Ces chiffres ne sont **pas mesurés** : ce sont les durées de la machine de test, mises à l'échelle de la vitesse de chaque carte
et processeur (± 30 %). Pour ta machine, `doctor` fait le même calcul à partir d'une vraie mesure de 10 s.

| Machine | Profil | Un épisode |
|---|---|---|
| RTX 3050 Laptop 6 Go (la machine de test) | Complet | **≈ 38 min** (mesuré) |
| RTX 3060 12 Go, RTX 4060 8 Go | Complet | ≈ 22 min |
| RTX 4070 12 Go | Complet | ≈ 14 min |
| RTX 4090 24 Go | Complet | ≈ 11 min |
| Carte NVIDIA de 4 Go (GTX 1650…) | Léger | ≈ 10 min |
| Sans carte NVIDIA, processeur récent | Léger | ≈ 12 min |

Le profil léger va plus vite parce qu'il saute ce qui prend le plus de temps : les voix qui jouent l'émotion et les visages qui
parlent. La vidéo est plus simple, mais elle est bien là.

## Comment c'est rangé

```
Installer.bat          installe ou met à jour (install/install.ps1)
Studio.bat             lance le Studio (le raccourci du Bureau pointe ici)
config.toml            tous les réglages, commentés
install/               l'installateur et les versions exactes de chaque environnement
manhwa/                le programme (ci-dessous)
manhwa/studio/         le Studio : serveur local (FastAPI) et page web
tests/                 les tests (pytest)
docs/                  le guide du Studio, les plans et leurs mesures
inbox/<série>/<ch>/    tes chapitres et tout ce que le Studio en fait (jamais commité)
.cache/                modèles et sons téléchargés (jamais commité)
```

| Rôle | Modules (`manhwa/`) |
|---|---|
| Récupérer | `ingest/scraper.py` (chapitres), `ingest/wiki.py` (personnages du wiki Fandom) |
| Découper | `panels.py` (cases), `slicer.py` (découpe à la main), `images.py` |
| Lire | `ocr.py`, `ocr_engines.py`, `bubbles.py`, `textfix.py`, `review.py` (relecture GPT), `llm.py` |
| Personnages | `faces.py` (visages), `cast.py` (qui parle) |
| Comprendre | `vision.py` (ce qui se passe), `scene.py`, `emotion.py`, `places.py` (lieux), `moods.py` (ambiance) |
| Voix | `voices.py`, `qwen_voice.py`, `chatterbox_tts.py`, `kokoro_tts.py`, `tts.py`, `rhythm.py`, `listen.py` (réécoute) |
| Sons | `sfx.py`, `soundbank.py`, `sonniss.py`, `sound_memory.py`, `ambient.py` |
| Vidéo | `render.py`, `scroll.py`, `scroll_gpu.py`, `motion.py`, `captions.py`, `talk.py` (visages qui parlent), `parts.py` |
| Outils | `cli.py`, `doctor.py`, `bench.py`, `ocr_bench.py`, `pilot.py`, `progress.py`, `project.py`, `config.py`, `gpu.py` |

Les gros modèles (Qwen, FLUX, Chatterbox, CLAP) tournent dans de petits programmes à part (`*_worker.py`), avec leur propre
environnement. Un seul est chargé à la fois, ce qui fait tenir tout le projet sur une carte de 6 Go.

## Modèles et licences

Un modèle n'est gardé que s'il fait mieux sur le banc de mesure et si sa licence permet une chaîne monétisée. Le détail des
mesures est dans [docs/PLAN_V3.md](docs/PLAN_V3.md).

| Modèle | Pour quoi | Licence | Taille |
|---|---|---|---|
| PaddleOCR (PP-OCR) | lire le texte | Apache 2.0 | 0,15 Go |
| comic-text-and-bubble-detector | bulles | Apache 2.0 | 0,2 Go |
| anime face / head / person (deepghs) | visages, têtes, corps | MIT | 0,1 Go |
| CCIP (deepghs) | reconnaître un personnage | OpenRAIL | 0,15 Go |
| DINOv2 small | regrouper les visages | Apache 2.0 | 0,08 Go |
| CLIP ViT-B/32 | ce que montrent les cases | MIT | 0,15 Go |
| roberta-base-go_emotions | le ton des répliques | MIT | 0,12 Go |
| Depth Anything V2 Small | relief de la caméra | Apache 2.0 | 0,05 Go |
| Qwen3.5-2B | ce qui se passe dans les cases | Apache 2.0 | 4,3 Go |
| Qwen3-TTS 1.7B VoiceDesign | voix qui jouent l'émotion | Apache 2.0 | 4,2 Go |
| Chatterbox (Resemble AI) | timbre de chaque personnage, voix de secours | MIT | ≈ 3 Go |
| Kokoro-82M | voix de base, locales | Apache 2.0 | 0,34 Go |
| faster-whisper small | réécouter les voix | MIT | 0,5 Go |
| CLAP (LAION) | écouter et ranger les sons | Apache 2.0 | 0,7 Go |
| SigLIP 2 | les sons appris de tes choix | Apache 2.0 | 0,18 Go |
| FLUX.2 [klein] 4B | visages qui parlent | Apache 2.0 | 14,9 Go |
| Sons Sonniss (GDC bundles) | bruitages et ambiances | libres de droits, usage commercial permis | 2,2 Go |
| GPT-4.1 ou Claude (en ligne, facultatif) | relecture, voix, sons, lieux, titres | selon ton abonnement | — |

Les sons Sonniss ne doivent être ni redistribués ni utilisés pour entraîner une IA. Ils restent donc dans `.cache/`, qui n'est
jamais commité. espeak-ng (la prononciation de Kokoro) est sous GPL-3.0, ce qui ne change rien pour les vidéos.

## Tests

```bash
.venv\Scripts\python -m pytest
```

## Pour aller plus loin

- [Guide du Studio](docs/GUIDE.md) : chaque onglet, chaque geste, la ligne de commande, les réglages.
- [Plan V2](docs/PLAN_V2.md) et [Plan V3](docs/PLAN_V3.md) : comment le projet a été construit, avec les mesures de chaque choix.

## Avertissement

Projet destiné à un usage personnel ou éducatif. Les manhwas appartiennent à leurs auteurs. Avant de publier, vérifie que tu
as le droit d'utiliser l'œuvre, et respecte les règles des plateformes : droits d'auteur, contenu réutilisé, label
« contenu généré par IA ».
