# Manhwa TikTok Automator

Transforme un chapitre de manhwa/webtoon en vidéo verticale 9:16 avec voix off.

**État : V3.** Un lien suffit : le Studio (une page web locale) télécharge le chapitre, le
découpe, lit le texte et le corrige, reconnaît les personnages, choisit voix, sons et
musique, crée la vidéo avec sous-titres karaoké, la réécoute, puis la coupe en parties
de 60–90 s pour TikTok avec titre et hashtags. Tout se vérifie et se corrige d'un clic.
Le détail et les mesures sont dans [PLAN_V2.md](PLAN_V2.md) et [PLAN_V3.md](PLAN_V3.md)
(chaque modèle local n'est gardé que s'il fait mieux sur le banc de mesure).

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

**Carte graphique NVIDIA** (facultatif) : la lecture du texte devient environ 26× plus
rapide (0,07 s par case au lieu de 1,7 s sur une RTX 3050), et Whisper, Kokoro et les
détecteurs aussi. Voir [requirements-gpu.txt](requirements-gpu.txt) ;
tout la prend seul quand elle est là.

**Modèles locaux** (facultatifs, chacun dans son environnement pour ne rien casser) :

| Pour | Environnement | Installation |
|---|---|---|
| Voix qui jouent l'émotion (Chatterbox), ce qui se passe dans les cases (Qwen3.5-2B), l'écoute des sons (CLAP) | `.venv-tts` | voir `manhwa/chatterbox_tts.py` et `manhwa/vision.py` |
| Voix décrites et jouées par Qwen3-TTS | `.venv-qwen` | voir `manhwa/qwen_voice.py` |
| Visages qui parlent : bouches et yeux redessinés (FLUX.2 [klein] 4B) | `.venv-edit` | voir `manhwa/edit_worker.py` |

**Bruitages et ambiances pro** (Sonniss, gratuits et utilisables sur une chaîne monétisée,
≈ 2 Go dans `.cache/`, jamais commités) :

```bash
.venv\Scripts\python -m manhwa.soundbank --download
```

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

Le plus simple : double-clique sur `Studio.bat` (ou sur un raccourci vers ce fichier).
Le Studio démarre et s'ouvre dans le navigateur ; fermer la fenêtre noire l'arrête.
S'il tourne déjà, le double-clic rouvre juste la page. En ligne de commande :

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

**Ajouter des chapitres** (en haut à gauche) : colle le lien de la série et les chapitres
voulus ; le Studio télécharge, découpe, lit le texte, cherche les personnages, fait relire
par GPT, choisit les voix et les sons, puis crée la vidéo, tout seul. Si le site demande
une vérification, une fenêtre de navigateur s'ouvre : passe-la, la suite continue.
Sur un chapitre déjà là, **Tout faire** lance les mêmes étapes. Sans clé GPT, les étapes
GPT sont simplement sautées.

**Pilote automatique** (`config.toml` → `[auto]`) : pendant « Tout faire », la machine
décide seule ce qui est sûr. Elle met le son proposé, accepte les corrections de GPT et
peut valider « qui parle » à partir d'une confiance réglable. Rien n'est caché : c'est
marqué « d'office » dans le Studio et se change d'un clic. Un choix fait à la main n'est
jamais remplacé. Le bouton **Mettre à jour la vidéo** apparaît dès qu'un changement n'est
pas encore dans la vidéo.

#### Onglet Vidéo

La vidéo, et à côté la case en cours (qui parle, avec quelle voix, quel son). Un passage
cloche ? Un clic sur la raison (mauvaise voix, texte faux, mauvais son, découpe) au bon
moment. La liste des passages signalés permet de revoir chacun et **Corriger** ouvre
l'onglet qu'il faut, sur la bonne case.

**Contrôle automatique** : après la vidéo, Whisper (local) réécoute chaque réplique et
signale celles où la voix ne dit pas ce qui est écrit (« La voix a dit… »). Il signale
aussi une voix manquante et une case trop courte ou trop longue. Sur le ch. 1, il a
trouvé 4 vraies erreurs, sans fausse alerte.

**Sous-titres karaoké** : la réplique s'affiche par groupes de 4 mots et le mot dit passe
en jaune (`[render] captions…`).

**Parties pour TikTok** : « Découper » coupe la vidéo en parties de 60 à 90 s, de
préférence sur un moment de suspense (une question, un cri, avant une nouvelle scène).
Chaque partie s'ouvre sur « PART 2/5 » et reçoit un titre et des hashtags, que
« Copier » met dans le presse-papiers. Les fichiers sont dans `<chapitre>/parts/`.

#### Onglet Personnages

Une fois la vidéo créée, l'onglet **Personnages** cherche tout seul les visages dans les
frames et les range par personnage (≈ 20 s pour un chapitre). CCIP, un modèle fait pour
reconnaître un personnage d'anime, les regroupe et reconnaît ceux de la série d'un
épisode à l'autre : sur le ch. 1, il y a 14 visages à déplacer au lieu de 23. Les modèles
sont téléchargés au premier usage dans `.cache/models/` et vérifiés par leur empreinte.

| Geste | Effet |
|---|---|
| Écrire dans le champ d'un groupe | Nommer le personnage (pour toute la série) ; la liste propose les noms du wiki |
| Clic sur un nom « Wiki : … » | Nommer d'après le wiki (genre, cheveux, caractère affichés) |
| « Ne parle pas » | Ranger le personnage à part : il n'est plus jamais proposé pour une réplique |
| Survol d'un visage ou d'une image | Le chapitre autour, en grand (la case de la vidéo encadrée en pointillés) |
| Clic sur des visages, puis sur un personnage dans la barre du bas | Les ranger (ou « Nouveau personnage », « Pas un visage ») |
| Clic sur le nombre d'un groupe | Sélectionner tous ses visages (pour fusionner deux groupes) |
| Clic sur une tête dans l'image d'une réplique, ou sur sa pastille | Dire qui parle |
| « Valider les N propositions » | Accepter d'un coup le personnage proposé (en pointillés) |

Le personnage proposé est celui dont le visage est le plus proche de la bulle ; sans
visage dans la case, celui des cases voisines. Un personnage secondaire sans groupe ?
« Autre… » → **Figurant** (voix d'homme ou de femme, réglables dans la carte Figurants) ou
**+ Nouveau personnage…** (il garde son nom pour la série). Si tu choisis quelqu'un d'autre
que le visage encadré, le Studio propose de corriger ce visage (toutes les répliques suivent).

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

Pour mesurer tout ce que la machine décide seule (types de bulle, texte, qui parle,
visages, ton, sons) par rapport à tes choix, utilise `python -m manhwa bench <chapitre>`.
`--freeze` fige d'abord tes décisions actuelles comme référence, dans
`.studio/gold.json`, qui n'est jamais commité. Chaque passage est gardé dans
`.studio/bench_history.json`, et l'écart avec le passage précédent s'affiche
(voir PLAN_V3.md).

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

#### Voix

Avec Qwen3-TTS installé (`[tts] engine = "qwen"`), chaque personnage a une voix **décrite**
(« jeune homme, voix basse, froide, sans émotion ») : GPT l'écrit d'après sa fiche, Qwen
joue chaque réplique avec son émotion, puis la voix est ramenée au timbre du personnage pour
rester la même d'une réplique à l'autre. ▶ fait entendre la voix, **Autre voix** en
redemande une, **Modifier** pour l'écrire toi-même. Whisper réécoute chaque réplique : une
réplique mal dite est refaite, puis dite par la voix de secours.

Sans Qwen, **Proposer les voix** laisse GPT-4.1 choisir une voix d'après le
genre, le caractère (wiki) et les répliques. Sans GPT, les accents alternent, les hauteurs
sont décalées, et un personnage âgé selon le wiki parle plus grave. ▶ pour écouter, la
liste pour changer, − / + pour une voix plus grave ou plus aiguë, **Valider**.

La liste mêle les voix edge-tts (en ligne, les plus claires) et les 28 voix **Kokoro**
(locales, 6 à 8 fois plus rapides). **Expressive** fait rejouer la voix par Chatterbox
(local) avec l'émotion de chaque réplique. Il demande l'environnement `.venv-tts`, voir
`manhwa/chatterbox_tts.py`. Le narrateur lit les encadrés de narration et les répliques
sans personnage. Chaque réplique a son ton : celui de GPT, le tien, sinon il est deviné
sur la ponctuation (« ?! » donne surpris…).

#### Onglet Relecture (GPT-4.1)

**Relire le chapitre** : GPT corrige les erreurs de lecture (« IDON'T THINK CAN » →
« I DON'T THINK I CAN »), dit si une bulle est une réplique, une pensée, de la narration ou
un bruitage, propose qui parle et note le ton de chaque réplique. Rien ne change sans ton
accord, sauf le ton, modifiable sur chaque réplique de l'onglet Personnages. Environ
3 minutes pour un chapitre. Les propositions arrivent une à une : **Accepter** (`A`),
**Refuser** (`R`) ou **Corriger moi-même** (`E`, ta version est gardée même si GPT relit
à nouveau) ; la suivante prend sa place. « Déjà décidées », en bas, pour changer d'avis.

Avant GPT, une **correction locale** recolle les mots collés (« IDON'T » → « I DON'T »),
retire les lettres perdues et repère le charabia, sans jamais toucher aux noms de la
série. Les cas moins sûrs (« AWAK » → « AWAKE ») attendent ici, marqués « Correction
locale ».

**Toutes les bulles** (deuxième onglet) : chaque bulle du chapitre, une à une. Tu
corriges le texte, choisis le type (réplique, pensée, narration, bruitage, pas du texte),
puis **C'est bon** (ou Entrée). Une bulle vérifiée n'est plus touchée par GPT, et elle
sert de référence au banc de mesure.

#### Onglet Sons

En haut, **la bande-son de l'épisode** : chaque case qui peut avoir un son, dans l'ordre
(violet : à choisir, vert : choisi, gris : sans son). Dessous, une case à la fois, en grand :
**ce qui se passe** (« Personnage poussé, sang »), le son proposé (un ou deux sons ensemble)
et pourquoi. **Valider** (Entrée), **Aucun son** (N), **Écouter avec la voix** (Espace),
← → pour passer d'une case à l'autre ; « + » à côté d'une idée met les deux sons ensemble.
La case suivante arrive au bout de 2 s, son bouton au même endroit (la souris qui bouge sur
la case la retient).

Pour proposer : un modèle local (Qwen3.5-2B) décrit chaque case, puis GPT choisit les sons
d'après l'histoire, la force du moment (le volume suit) et ce qu'on doit entendre ; CLAP, un
modèle qui écoute, prend dans la bibliothèque pro la prise la plus proche. Tes propres sons se
rangent dans `sfx/<catégorie>/`.

**Les sons appris de tes choix** : SigLIP 2 (local) compare chaque case à celles où tu as déjà
choisi un son, dans tous tes épisodes. Avant chaque proposition, cette mémoire se teste sur tes
choix (chaque case devinée par les autres) : elle ne sert que si elle fait mieux que la
proposition habituelle. Avec un seul épisode, elle attend (46 % contre 83 % sur l'épisode 1).

**Visages qui parlent** (onglet Personnages) : pour chaque personnage qui parle, l'IA
(FLUX.2 [klein] 4B, Apache 2.0, 7 à 9 s par dessin sur une carte de 6 Go) redessine dans le style
de la case trois bouches et les yeux fermés ; dans la vidéo, la bouche bat à chaque syllabe et
les yeux clignent. Un aperçu animé par visage : **C'est bon**, **Pas animé**, ou **Redessiner**
(l'IA le refait autrement). Réglé par `[render] talk`.

**Les lieux** : GPT coupe l'épisode en lieux (prison, marché, forêt…) ; chacun a une ambiance
de fond, très basse, et les voix y résonnent comme dans le lieu. **L'image réagit** aux
coups : zoom « punch », tremblement, flash ; pendant chaque case, la caméra glisse en relief
(le premier plan bouge plus que le fond). Tout se règle dans `[render]` : `effects`, `depth`,
`ambience`, `voice_space`, `loudness`.

La **musique suit l'ambiance** : calme, tension, combat ou tristesse, d'après ce que
montrent les cases et le ton des répliques. Elle change avec la scène, en fondu, et
baisse quand on parle. Tes morceaux vont dans `music/calm/`, `music/tension/`,
`music/combat/` et `music/sad/` ; sans eux, une nappe générée, libre de droits, est
utilisée. Pour garder un seul morceau, mets son chemin dans `[render] music`. Au rendu, une case plus haute que l'écran défile en pleine largeur, les autres
zooment très légèrement, et chaque case pousse la précédente vers le haut comme un
webtoon qu'on fait défiler (`[render]` dans config.toml : `zoom`, `pan`, `transition`,
`music_volume`…).

#### Clé GPT

La roue dentée en haut à gauche ouvre les **Réglages** : adresse du proxy, modèle et clé,
enregistrés dans `.env` (jamais commité). La clé change chaque jour : colle la nouvelle
ici, « Enregistrer et tester » vérifie qu'elle marche. Une clé **Claude** (Anthropic,
console.anthropic.com) peut s'y ajouter : sans clé GPT, ou quand elle a expiré, Claude
(Haiku 5.5) prend le relais.

### Combien de temps

Mesuré sur un épisode neuf de 142 cases et 144 répliques (RTX 3050 6 Go), avec « Tout faire » :

| Étape | Durée |
|---|---|
| Frames, lecture du texte, visages, ce que montrent les cases | ≈ 1,5 min |
| Ce qui se passe dans les cases (Qwen3.5-2B, 6 à la fois) | ≈ 5 min |
| Relecture, voix, sons, lieux (GPT ou Claude) | quelques secondes chacune |
| Visages qui parlent (22 visages, 4 dessins chacun) | ≈ 10 min |
| Voix (Qwen3-TTS, puis le timbre de chaque personnage) | ≈ 12 min |
| Rendu de la vidéo (8 min) | ≈ 3,5 min |
| Réécoute et découpe en parties | ≈ 1 min |

Chaque étape garde ce qu'elle a fait : relancée, elle ne refait que ce qui a changé (une
étape coupée en route reprend là où elle s'était arrêtée). Le Studio note la durée de
chaque étape dans sa console.

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
