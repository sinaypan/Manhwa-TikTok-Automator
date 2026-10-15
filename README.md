# Manhwa TikTok Automator

Transforme un chapitre de manhwa/webtoon en vidéo verticale 9:16 avec voix off.

**État : V2, phase 1.** Les chapitres arrivent dans `inbox/`, la découpe en cases est
automatique et se retouche en quelques clics dans le **Studio** (une page web locale),
puis OCR → voix → vidéo. La suite (OCR local, GPT-4.1, sous-titres, bruitages…) est
décrite dans [PLAN_V2.md](PLAN_V2.md).

## Installation

Pré-requis : [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) et
[uv](https://docs.astral.sh/uv/) (ou Python 3.12 + pip).

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python -m playwright install chromium
```

Tesseract est cherché dans le PATH puis dans `C:\Program Files\Tesseract-OCR\`.
Sinon, indique son chemin dans `config.toml` → `[ocr] tesseract_cmd`.

Copie `.env.example` en `.env` pour les clés d'API (utilisées à partir de la phase 3).
`.env` n'est jamais commité.

## Utilisation

Toutes les commandes s'écrivent `.venv\Scripts\python -m manhwa <commande>`.

### 1. Mettre des chapitres dans `inbox/`

Un chapitre = un dossier `inbox/<série>/<chapitre>/`. Deux façons :

- **À la main** : mets les images dans le dossier du chapitre, par exemple
  `inbox/Solo Leveling/chapter-012/`. L'ordre suit les numéros des fichiers
  (`2.jpg` passe bien avant `10.jpg`).
- **Avec le scraper** :

  ```bash
  .venv\Scripts\python -m manhwa download "https://site/series/ma-serie" --chapters 1-5
  ```

  Sélection possible : `12`, `1-5`, `1-5,8,10-12`, `all`, `latest`. Sans `--chapters`,
  la commande te demande. Si une vérification anti-robot s'affiche, passe-la dans la
  fenêtre du navigateur puis appuie sur Entrée. Relancer la même commande reprend
  là où ça s'était arrêté ; les chapitres déjà complets sont ignorés.

  Les sélecteurs CSS de chaque site sont dans `config.toml` → `[scraper.sites.*]`.

### 2. Le Studio

```bash
.venv\Scripts\python -m manhwa studio
```

Ouvre `http://127.0.0.1:8765/` dans le navigateur (rien n'est accessible depuis
l'extérieur). À gauche, les séries et leurs épisodes avec leur avancement ; au centre,
le chapitre avec la découpe déjà proposée :

| Geste | Effet |
|---|---|
| Clic sur une ligne | Supprimer la coupe |
| Clic dans une case | Ajouter une coupe (aimantée sur la marge la plus proche) |
| Glisser une ligne | L'ajuster |
| Survol d'une case | Aperçu de sa frame 9:16 |
| Ctrl+Z | Annuler |

Les lignes en pointillés et les badges orange (case très haute) sont les endroits à
vérifier ; « Tout est bon » les valide d'un coup. **Créer la vidéo** lance frames →
texte → voix → rendu en arrière-plan, et la vidéo s'affiche dans le Studio à la fin.

#### Onglet Personnages

Une fois la vidéo créée, l'onglet **Personnages** cherche tout seul les visages dans les
frames et les range par personnage (≈ 20 s pour un chapitre, sur le processeur). Les
modèles (≈ 90 Mo) sont téléchargés au premier usage dans `.cache/models/`.

| Geste | Effet |
|---|---|
| Écrire dans le champ d'un groupe | Nommer le personnage (pour toute la série) ; la liste propose les noms du wiki |
| Clic sur un nom « Wiki : … » | Nommer d'après le wiki (genre, cheveux, caractère affichés) |
| « Ne parle pas » | Ranger le personnage à part : il n'est plus jamais proposé pour une réplique |
| Survol d'un visage ou d'une image | La case d'où il vient, en grand |
| Clic sur des visages, puis sur un personnage dans la barre du bas | Les ranger (ou « Nouveau personnage », « Pas un visage ») |
| Clic sur le nombre d'un groupe | Sélectionner tous ses visages (pour fusionner deux groupes) |
| Clic sur une tête dans l'image d'une réplique, ou sur sa pastille | Dire qui parle |
| « Valider les N propositions » | Accepter d'un coup le personnage proposé (en pointillés) |

Le personnage proposé est celui dont le visage est le plus proche de la bulle ; sans
visage dans la case, celui des cases voisines.

**Wiki** : « Noms depuis le wiki » lit le wiki Fandom de la série (trouvé d'après son
nom) : noms, genre, cheveux, chapitre d'apparition et caractère, sans les passages
marqués spoiler. Un nom est proposé à un groupe d'après la couleur des cheveux et le
chapitre d'apparition (jamais un personnage qui n'apparaît que plus tard). « Images du
wiki » ouvre une fenêtre de navigateur : si Cloudflare demande une vérification, tu la
passes à la main une fois, puis les images se téléchargent et leurs visages affinent
les propositions. Tout est rangé dans `inbox/<série>/.wiki/`.

### 3. Ou tout en ligne de commande

```bash
.venv\Scripts\python -m manhwa make
```

Pour chaque chapitre de `inbox/` (ou seulement celui indiqué en argument) :
découpe automatique (si pas encore faite) → OCR → voix → `video.mp4` dans le dossier
du chapitre. Chaque étape est mise en cache : relancer `make` ne refait que ce qui a
changé. `make --manual` ouvre l'ancienne fenêtre de découpe à la main.

Voir où en est chaque chapitre :

```bash
.venv\Scripts\python -m manhwa status
```

Les étapes existent aussi séparément : `cut` (découpe auto), `slice` (à la main),
`ocr`, `tts`, `render` (avec `--force` pour refaire même si c'est à jour).

### Lecture du texte (OCR)

Le texte est lu par **PaddleOCR** (local, gratuit), puis regroupé en bulles dans l'ordre de
lecture. Les onomatopées (coréennes ou anglaises), les filigranes du site, les crédits et
les titres de chapitre sont repérés et **ne sont pas lus** par la voix ; les SFX sont gardés
pour les bruitages. Le moteur se change dans `config.toml` (`[ocr] engine` : `paddle`,
`windows` ou `tesseract`) ou ponctuellement avec `ocr --engine windows`.

Pour comparer les moteurs sur un chapitre, mets une référence lue à la main dans
`<chapitre>/.studio/ocr_gold.json` puis lance `python -m manhwa ocr-bench <chapitre>`.

### Contrôles de la découpe à la main (`slice`)

| Touche | Action |
|---|---|
| Molette, ↑ ↓ (← → pour un petit pas) | Faire défiler le chapitre |
| Souris : glisser le centre / un coin | Déplacer / redimensionner le cadre |
| `I` `J` `K` `L` | Déplacer le cadre |
| `+` / `-` | Agrandir / réduire le cadre |
| `Entrée` | Garder la frame (la vue avance à la suite) |
| `Retour arrière` | Annuler la dernière frame |
| `R` | Cadre plein écran |
| `M` | Changer le fond (flou / noir / gris) |
| `O` | Tester l'OCR sur le cadre |
| `H` | Afficher/masquer l'aide |
| `Q` / `Échap` | Terminer |

## Dossier d'un chapitre

```
inbox/<série>/characters.json   personnages de la série (noms)
inbox/<série>/chapter-012/
  pages/          images source (ou directement à la racine du chapitre)
  frames/         frames 9:16
  audio/          une voix par réplique
  .studio/        cache du Studio (profil du chapitre, vignettes, visages)
  project.json    état de chaque étape (coupes, crops, textes…)
  video.mp4       résultat
```

## Configuration

Tout se règle dans [config.toml](config.toml) : voix (`[tts]`), rythme de la vidéo (`[render] speed`, 1,25 par défaut), fond des
frames (`[slicer]`), durée des frames sans texte (`[render]`), sites du scraper…

## Tests

```bash
.venv\Scripts\python -m pytest
```

## Disclaimer

Projet destiné à un usage personnel ou éducatif. Respecte les droits d'auteur des
œuvres originales et les conditions des plateformes où tu publies.
