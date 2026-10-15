# Manhwa TikTok Automator

Transforme un chapitre de manhwa/webtoon en vidéo verticale 9:16 avec voix off.

**État : V2, phase 0.** Le pipeline V1 (découpe manuelle → OCR → voix → vidéo) tourne
maintenant d'une seule commande, sur un dossier `inbox/`. La suite (découpe auto,
Studio, OCR local, GPT-4.1, sous-titres…) est décrite dans [PLAN_V2.md](PLAN_V2.md).

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

### 2. Fabriquer les vidéos

```bash
.venv\Scripts\python -m manhwa make
```

Pour chaque chapitre de `inbox/` (ou seulement celui indiqué en argument) :
découpe (si pas encore faite) → OCR → voix → `video.mp4` dans le dossier du chapitre.
Chaque étape est mise en cache : relancer `make` ne refait que ce qui a changé.

Voir où en est chaque chapitre :

```bash
.venv\Scripts\python -m manhwa status
```

Les étapes existent aussi séparément : `slice`, `ocr`, `tts`, `render`
(avec `--force` pour refaire même si c'est à jour).

### Contrôles de la découpe

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
inbox/<série>/chapter-012/
  pages/          images source (ou directement à la racine du chapitre)
  frames/         frames 9:16
  audio/          une voix par frame
  project.json    état de chaque étape
  video.mp4       résultat
```

## Configuration

Tout se règle dans [config.toml](config.toml) : voix et vitesse (`[tts]`), fond des
frames (`[slicer]`), durée des frames sans texte (`[render]`), sites du scraper…

## Tests

```bash
.venv\Scripts\python -m pytest
```

## Disclaimer

Projet destiné à un usage personnel ou éducatif. Respecte les droits d'auteur des
œuvres originales et les conditions des plateformes où tu publies.
