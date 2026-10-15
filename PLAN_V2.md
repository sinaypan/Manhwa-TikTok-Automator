# Plan V2 — Manhwa TikTok Automator

## Objectif

Transformer un chapitre de manhwa en vidéo 9:16 prête à publier (voix, sous-titres,
mouvement, musique), sans CapCut, avec **moins de 2 minutes de travail humain par vidéo**.

L'humain ne fait plus le travail : il **arbitre** ce dont la machine doute, en cliquant,
dans un **Studio** local. Jamais de saisie au clavier quand un choix peut être proposé.

## Principes

1. **La machine propose, l'humain valide.** Chaque étape produit ses doutes sous forme de
   choix à cliquer, au lieu de deviner en silence ou de tout faire refaire à la main.
2. **Un clic = beaucoup de travail.** On regroupe les décisions similaires, on pré-remplit,
   on ne montre que ce qui est incertain.
3. **Tout est mis en cache, étape par étape.** Modifier une phrase du script ne relance que
   la voix, les sous-titres et le rendu.
4. **Rien n'est perdu.** Chaque action est sauvegardée tout de suite ; on peut arrêter et
   reprendre n'importe quand.
5. **Fournisseurs interchangeables.** LLM, voix et OCR sont derrière une petite interface :
   si une clé expire ou un service ferme, on change une ligne de config.

## Contraintes connues

- **LLM : GPT-4.1 via un proxy compatible OpenAI, texte seulement** (pas d'images).
  La clé (`DAILY_OPENAI_*`) change souvent → lue depuis `.env`, jamais dans le code,
  réponses mises en cache sur disque, message clair si la clé a expiré (401).
  Pour la bibliothèque `openai`, la base URL s'arrête à `/v1` (sans `/chat/completions`).
- **PC : RTX 3050 6 Go, 16 Go de RAM** → toute la « vision » tourne en local.
- Les bibliothèques de ML suivent mal les Python très récents → venv en **Python 3.12**.

## Pipeline

```
inbox/ ─► 1. Découpe auto ─► 2. OCR local ─► 3. Description locale (option)
                                   │                     │
                                   └── texte + positions ┘
                                              ▼
              4. GPT-4.1 (texte) + novel + bible : nettoie, ordonne, attribue, écrit
                                              ▼
              5. Voix (+ timing des mots) ─► 6. Sous-titres ─► 7. Rendu ffmpeg
```

### 0. Source : `inbox/`
- Chaque chapitre est un dossier `inbox/<série>/<chapitre>/`, avec les images dans
  `pages/` (scraper) ou directement à la racine (téléchargement à la main).
- Le scraper remplit `inbox/` : vrais numéros de chapitre, plages (`12-20`), reprise,
  sélecteurs par site dans `config.toml`. La vérification Cloudflare reste manuelle.

### 1. Découpe automatique des cases
- Assemblage du chapitre en un long strip, détection des **gouttières** (bandes de
  couleur quasi uniforme) par variance des lignes de pixels, fusion des petits morceaux.
- Une case plus haute qu'un écran 9:16 n'est pas coupée : elle sera parcourue en
  défilement au rendu.
- Correction dans le Studio : clic sur une ligne = supprimer, clic entre deux lignes =
  ajouter une coupe **aimantée sur la gouttière la plus proche**, glisser = ajuster.

### 2. OCR local (GPU)
- Détection des zones de texte : `comic-text-detector`.
- Lecture : **PaddleOCR** (plan B : EasyOCR).
- Pour chaque bulle : texte, position, note de confiance.

### 3. Description locale des cases (option)
- Petit modèle de vision local (Florence-2 ou Qwen2.5-VL 3B via Ollama) : une phrase par
  case, surtout pour les cases d'action sans texte.

### 4. GPT-4.1 + novel + bible
- Entrée texte : par case, les bulles (texte, position, confiance) et la description.
- Sortie JSON validée (pydantic) : texte corrigé, ordre de lecture, type
  (dialogue / pensée / narration / SFX), personnage probable, script.
- **Bible de série** (`bible.json`) : personnages (noms, alias, genre, visages), résumé
  des chapitres, position atteinte dans le novel. Remplie au départ depuis le **wiki
  Fandom** de la série (API MediaWiki).
- **Novel (option)** : import `.txt`/`.epub`, découpe en chapitres, alignement :
  1. fenêtre de recherche à partir de la dernière position et d'un ratio mesuré ;
  2. ancrages exacts (fenêtres « système », noms rares) via BM25 ;
  3. alignement **ordonné** des répliques (programmation dynamique) ;
  4. embeddings multilingues locaux (`bge-m3`) pour les reformulations ;
  5. confirmation par GPT-4.1 sur le passage retenu ;
  6. score de confiance ; si trop faible, on continue sans le novel.
  Interdiction d'utiliser ce qui vient après le passage aligné (pas de spoilers).
- Modes : `recap` (narration, accroche automatique dans les 3 premières secondes) et
  `dub` (lecture fidèle, une voix par personnage).

### 5. Voix
- edge-tts par défaut, avec le timing de chaque mot. Moteur interchangeable.
- Narrateur + une voix par personnage, attribuée selon le genre (wiki), variée en
  hauteur et vitesse. Réglée une fois par série.

### 6. Sous-titres
- `.ass` style karaoké (2 à 4 mots, mot prononcé surligné), incrustés au rendu.

### 7. Rendu
- ffmpeg : défilement vertical des cases hautes, léger zoom sinon, fond flouté,
  transitions courtes, musique qui baisse sous la voix, 1080×1920 à 30 fps.

## Le Studio

Application web **locale** (serveur FastAPI + page HTML), ouverte dans le navigateur ;
accessible aussi depuis le téléphone sur le même Wi-Fi. Rien n'est mis en ligne.

**Style** : celui des extensions Chrome (`Documents\Chrome Extensions`) — sobre façon
Apple/iOS, police système, gris iOS (`#1c1c1e`, `#2c2c2e`, `#f2f2f7`, `#8e8e93`),
séparateurs fins, icônes au trait fin, clair/sombre automatique. Sombre par défaut,
accent indigo (`#5e5ce6`). Pas de points ni de combos : le côté « studio magique »
vient du fait de **voir le travail se faire en direct** (cases qui se découpent,
vignettes qui se remplissent, léger reflet animé sur ce qui est en calcul, vidéo finale
lue dans le Studio).

**Disposition** : barre latérale **Séries → Épisodes**, chacun avec sa barre de
progression ; au centre, la tâche en cours.

**Écrans** :
| Écran | Geste |
|---|---|
| Découpe | Clic sur une ligne de coupe / entre deux lignes (aimantée) / glisser |
| Texte douteux | Choisir parmi 2–3 versions (OCR, novel, corrigée par GPT) |
| Type de bulle | Dialogue / pensée / narration / SFX |
| Qui parle | Bulle surlignée sur l'image, colonne de visages triés par probabilité, clic sur une tête |
| Voix | Écouter, « changer » si besoin |
| Vidéo | La regarder ; valider ou signaler un passage |

Les visages viennent du manhwa lui-même (détecteur de visages style anime), les noms du
wiki. Les réponses humaines enrichissent la bible et servent à mesurer la précision de
l'automatique (« le matching a raison 87 % du temps »).

## Phases

| # | Phase | Fini quand… |
|---|---|---|
| 0 | **Remise à plat** : bugs V1, structure `manhwa/`, venv, `.env`, `config.toml`, `project.json`, scraper corrigé vers `inbox/` | Un chapitre téléchargé arrive dans `inbox/` et en ressort en vidéo V1 |
| 1 | **Studio de base** (style, séries/épisodes, progression) + découpe auto + écran Découpe | Un chapitre découpé en quelques clics |
| 2 | **OCR local** + écrans Texte douteux et Type de bulle | Plus aucune bulle à retaper |
| 3 | **Bible (wiki) + visages + GPT-4.1 + novel** + écran Qui parle | Toutes les répliques attribuées en cliquant sur des têtes |
| 4 | **Voix multiples + sous-titres karaoké** + écran Voix | Narrateur + une voix par perso, réglées une fois |
| 5 | **Rendu final** + écran Vidéo | Un MP4 publiable, < 2 min de travail humain |
| 6 | **Confort** : téléphone, plusieurs séries, mode YouTube long, description locale | — |

## Décisions en attente

- Langue des vidéos (anglais ou français).
- Format : shorts 60–90 s, YouTube long, ou les deux.
- Premier manhwa (sert à trouver son wiki et son novel).

## Risques

- Droits d'auteur et rémunération TikTok : le recap narré passe mieux que la lecture,
  mais le risque de retrait reste.
- Cases sans gouttière → écran Découpe.
- edge-tts peut s'arrêter → moteur de voix interchangeable.
- Clé de proxy temporaire → cache des réponses LLM, fournisseur interchangeable
  (repli possible sur un modèle texte local via Ollama).
