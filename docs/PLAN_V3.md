# Plan V3 — Des modèles locaux à la place des clics

## Objectif

Du lien à la vidéo avec **trois gestes seulement** : coller le lien, passer la vérification
Cloudflare, et (facultatif) coller la clé GPT. Tout ce que l'on vérifie aujourd'hui à la
main (texte, type de bulle, qui parle, ton, voix, sons, musique, contrôle de la vidéo)
est décidé par la machine quand elle est sûre, et n'arrive dans le Studio que quand elle
doute. GPT devient un **arbitre de secours**, plus le seul juge.

## Principes

1. **Plusieurs signaux qui se complètent valent mieux qu'un seul qui se trompe.** Chaque
   décision est un vote : une règle sur l'image (forme, position), un modèle local, et GPT
   s'il est là. Le vote donne une **confiance** : au-dessus du seuil, c'est appliqué
   d'office ; en dessous, la ligne arrive dans la file « à faire » du Studio.
2. **Mesurer avant d'adopter.** Les décisions déjà validées sur Myst Might Mayhem ch. 1
   (145 « qui parle », 97 décisions de relecture, les visages rangés, les sons) servent de
   référence. Un nouveau module n'entre que s'il fait mieux que l'actuel sur ce banc.
3. **Licences compatibles avec une chaîne monétisée uniquement** (Apache, MIT, OpenRAIL,
   licences « communauté » gratuites). Ce qui est « recherche » ou « non commercial » est
   exclu, même s'il marche mieux.
4. **6 Go de mémoire vidéo.** Un seul gros modèle chargé à la fois (les travaux du Studio
   passent déjà un par un), ONNX et versions int8 de préférence, modèle libéré après
   l'étape. Les bibliothèques lourdes (torch) vivent dans un venv à part.
5. **Comme avant :** modèles téléchargés au premier usage dans `.cache/models/` et
   vérifiés par SHA-256, résultats en cache avec une clé de version, rien dans `inbox/`,
   `.cache/` ni les références de texte (droits d'auteur) n'est commité.

## Licences vérifiées (Hugging Face / PyPI, le 16/10/2026)

| Modèle | Pour quoi | Licence | Verdict |
|---|---|---|---|
| **Magi v1 / v2 / v3** (ragavsachdeva) | cases, bulles, personnages, qui parle | « recherche académique uniquement » | ❌ exclu |
| phonemizer, espeak-ng (pour Kokoro) | prononciation | GPL-3.0 | ⚠️ sans effet sur les vidéos ; à savoir si le programme était distribué |
| **comic-text-and-bubble-detector** (ogkalu, ONNX int8) | bulles et zones de texte | Apache-2.0 | ✅ |
| yolov8m_seg-speech-bubble (kitsumed) | masques de bulles | GPL-3.0 | ❌ évité (contamine le projet) |
| **anime_face / anime_head / anime_person_detection** (deepghs, ONNX) | visages, têtes, corps | MIT | ✅ (exécutés avec onnxruntime, sans la bibliothèque Ultralytics qui est AGPL) |
| **CCIP** (deepghs) | reconnaître un personnage d'anime d'une image à l'autre | OpenRAIL | ✅ |
| **faster-whisper** + modèles Systran small / medium | réécouter la voix | MIT | ✅ |
| **roberta-base-go_emotions** (SamLowe) | émotion du texte (28 émotions) | MIT | ✅ |
| emotion-english-distilroberta (j-hartmann) | émotion du texte | aucune licence indiquée | ❌ |
| **Kokoro-82M** (+ version ONNX) | voix | Apache-2.0 | ✅ (paquet `kokoro-onnx` : licence à confirmer, sinon appel ONNX direct) |
| **Chatterbox** (Resemble AI, + version ONNX) | voix expressives, intensité réglable | MIT | ✅ (filigrane audio inaudible « Perth » intégré) |
| XTTS-v2 (Coqui) | voix | Coqui Public Model License (non commerciale) | ❌ |
| **Florence-2 base / large** (Microsoft, ONNX) | décrire une case | MIT | ✅ |
| Qwen2.5-VL-3B | décrire une case | Qwen Research (non commerciale) | ❌ |
| Qwen2.5-VL-7B | décrire une case | Apache-2.0 | ⚠️ trop lourd pour 6 Go |
| Qwen2.5-7B-Instruct (compressé Q4) | LLM local de secours | Apache-2.0 | essayé puis retiré : GPT reste le seul LLM |
| Qwen2.5-3B-Instruct | LLM local léger | Qwen Research | ❌ |
| Stable Audio Open (small / 1.0) | fabriquer des bruitages manquants | Stability AI Community (gratuit sous 1 M$ de revenus par an) | ⚠️ plus tard, à relire avant usage |
| MusicGen (Meta) | musique | CC-BY-NC | ❌ |

## Chantiers

Chaque chantier dit ce qu'il remplace, comment, où dans le code, et quand il est fini.
Effort : **S** ≈ une séance, **M** ≈ deux ou trois, **L** ≈ une semaine de séances.

### 0. Banc de mesure — prérequis (S)
- `manhwa/bench.py` et `python -m manhwa bench <chapitre> [étape]` : fige les décisions
  que tu as déjà prises sur un chapitre en référence (`.studio/gold_*.json`, jamais
  commité) et note chaque étape : % de types de bulle justes, de « qui parle » justes,
  de corrections de texte retrouvées, de visages bien rangés, de sons identiques aux tiens.
- La première mesure donne le niveau d'aujourd'hui ; chaque chantier doit le dépasser.
- Un champ `confidence` commun à toutes les décisions (bulles, orateur, ton, son), que le
  pilote automatique (chantier J) lira.

#### ✅ Niveau de départ — Myst Might Mayhem ch. 1 (16/10/2026)

Référence figée : 270 bulles, 146 « qui parle », 62 visages rangés, 189 tons, 84 sons
choisis. Ce que la machine fait seule aujourd'hui, sans tes corrections :

| Étape | Mesure | Aujourd'hui | Chantier qui doit l'améliorer |
|---|---|---|---|
| Type de bulle | justes | 100 % (1 erreur, entendue : du charabia lu comme réplique) | B3, C |
| Texte | répliques exactes | 93 % (10 à corriger, 0 corrigées sans GPT) | A1, B |
| Qui parle | justes | 71 % (le bon est dans les 4 proposés : 94 %) | D, E |
| Qui parle | validé d'office | confiance ≥ 0,2 : 37 % des répliques, 79 % justes | E, J |
| Visages | regroupés de zéro | 23 visages sur 62 à déplacer, 68 % des paires retrouvées | D |
| Ton | justes (référence : GPT) | 50 % (tout neutre) | F |
| Sons | même son proposé | 34 % ; dans les 3 proposés : 88 % | H |

Ce qu'on en tire :
- **Qui parle :** la plupart des erreurs proposent le héros (le visage le plus fréquent)
  quand un autre parle. La pointe de la bulle et l'alternance (E) visent exactement ce
  défaut.
- **Type de bulle :** la référence est faible. Seules les bulles signalées par GPT ont
  été revues, donc les 100 % sont trop flatteurs. À compléter quand l'écran des types
  montrera toutes les bulles.

#### ✅ Phase 1 — ce qui a été gardé, et ce qui ne l'a pas été (16/10/2026)

| Chantier | Résultat sur le ch. 1 | Verdict |
|---|---|---|
| **B2–B3 texte** (`textfix.py`) | 3 des 10 erreurs corrigées d'office (mots collés, lettres perdues), 5 si tu acceptes les propositions, **0 bonne phrase abîmée** ; charabia : la seule bulle de charabia est repérée (1 → 0 erreur entendue) | ✅ gardé, dans la chaîne après la lecture |
| **F2 ton** (`emotion.py`) | 56 % d'accord avec le ton de GPT, contre 50 % pour « tout neutre » | ✅ gardé (seulement quand ni GPT ni toi n'avez donné de ton) |
| **H1 sons** | le son mis d'office est le tien 79 fois sur 100, contre 34 ; tu ne choisis presque jamais « aucun son » | ✅ gardé : le 1er proposé va dans la vidéo tant que tu ne choisis pas (`[auto] sounds`) |
| **H2 onomatopées** | aucun effet ici (bruitages coréens illisibles), utile pour les séries aux bruitages traduits | ✅ gardé |
| **G1 voix** | accents alternés, hauteurs décalées, âge du wiki ; les voix du ch. 1 étaient déjà distinctes | ✅ gardé |
| **A1 Whisper** (`listen.py`) | 1 min 20 pour le chapitre (répliques mises bout à bout, processeur) ; sur 10 répliques mal lues, 6 signalées, 0 fausse alerte sur 15 bonnes ; sur le chapitre relu, **4 alertes, toutes réelles** (une fois les noms de la série et les interjections sautés) | ✅ gardé, après le rendu (facultatif) |
| **A2 contrôle** | onglet Vidéo : voix qui ne dit pas le texte, voix manquante, case trop courte ou trop longue | ✅ gardé |
| **E2 alternance** | 71,7 % contre 71 % ; même en connaissant la réplique d'avant : 66,9 % | ❌ abandonné : la case montre souvent celui qui écoute. La pointe de la bulle (E1) devient la priorité de la phase 2 |
| **C2–C3 forme des bulles** | impossible à mesurer : aucune pensée ni narration dans la référence du ch. 1 | ⏸ reporté : il faut une référence (épisode 2 annoté en entier) |

Notes :
- Whisper ne tourne pas encore sur la carte graphique : il manque les bibliothèques
  cuBLAS et cuDNN pour CTranslate2, et l'essai reste bloqué. Il tourne donc sur le
  processeur.
- Pour décoder l'audio, on passe par le ffmpeg du rendu : `av` 19 n'accepte plus une
  option de faster-whisper.

#### ✅ Phases 2 à 4 — gardé, abandonné (16/10/2026)

| Chantier | Résultat sur le ch. 1 | Verdict |
|---|---|---|
| **Toutes les bulles** (Relecture) | chaque bulle vérifiée une à une (texte, type) ; GPT et la correction locale ne la touchent plus ; elle sert de référence forte au banc | ✅ — à faire sur l'épisode 2 pour mesurer le type de bulle |
| **C1 + E1** pointe de la bulle (détecteur ogkalu, Apache-2.0) | 134 répliques sur 145 dans une bulle détectée, pointe trouvée sur 104 ; mais « qui parle » ne monte que de 71 % à 72,4 %. La vraie cause, vue sur les images : le visage de celui qui parle n'est souvent pas détecté (Munno), ou la case montre celui qui écoute | ❌ pas gardé (+1 réplique) |
| **D1** têtes et corps (deepghs, MIT) | 263 têtes contre 70 visages (64 des 70 retrouvés) ; mais « qui parle » baisse (65 %) : plus de têtes, ce sont surtout plus de distracteurs | ❌ pas gardé (et 3,7× plus de visages à ranger) |
| **D2–D3** CCIP (deepghs, OpenRAIL) | regroupement de zéro : 14 visages à déplacer au lieu de 23 ; reconnaître un personnage d'un épisode à l'autre : 47 justes au lieu de 43, autant d'erreurs (8) | ✅ CCIP regroupe et reconnaît ; DINOv2 reste pour le wiki (mieux séparé : bon ≈ 0,89, autre ≤ 0,76 ; CCIP : jusqu'à 0,87 pour un faux) |
| **F1** émotion du texte (go_emotions, MIT) | 55,9 % contre 55,2 % pour la ponctuation seule (référence : le ton de GPT) | ❌ pas gardé (+1 réplique pour 125 Mo) ; à revoir avec des tons choisis à la main |
| **B1** double lecture (OCR Windows) | Windows lit mal les bulles isolées (30 / 145 exactes) ; +1 réplique, déjà corrigée en local | ❌ pas gardé |
| **G2** Kokoro (Apache-2.0) | 6 à 8× plus rapide qu'edge-tts (0,17 s par réplique sur la carte) ; 1 à 2 répliques sur 30 mal comprises par Whisper, contre 0 pour edge | ✅ en option par personnage, edge reste le défaut |
| **G3** Chatterbox (MIT, `.venv-tts`) | ≈ 2,6 s par réplique, 3,4 Go de mémoire ; compris sans erreur par Whisper ; l'intensité suit l'émotion | ✅ case « Expressive » par personnage |
| **H3** Florence-2 (MIT) | descriptions utiles (« une main qui tient une faux ») ; mais le son déduit de la description est moins bon : 50 à 62 % contre 79 % pour CLIP | ❌ pas gardé pour les sons ; pourrait servir de contexte au LLM |
| **I** musique selon l'ambiance | combat au début (le grand-père) et pendant l'attaque des brigands (2:33–3:19), calme ailleurs ; nappes générées par ambiance, ou music/<ambiance>/ | ✅ (pas de référence pour mesurer : à juger à l'écoute) |
| **K** LLM local (Qwen2.5-7B Q4, Apache-2.0) | tient sur la carte (13 jetons/s) ; sur le chapitre : 3 erreurs corrigées, 0 phrase abîmée, ≈ 6 min ; avec la correction locale : 4 | ❌ retiré à ta demande : GPT fait le travail de langue ; les modèles locaux, ce qu'ils font aussi bien ou mieux |
| **J** pilote automatique | pendant « Tout faire » : sons d'office, corrections de GPT acceptées d'office, « qui parle » d'office au-dessus d'un seuil (désactivé : 79 % justes à 0,2) | ✅ tout est marqué « d'office » et se change |
| Sous-titres karaoké | groupes de 4 mots, le mot dit en jaune ; instants répartis sur la voix, ou ceux de Whisper | ✅ |
| Parties TikTok | ch. 1 : 6 parties de 64 à 89 s, qui finissent sur « WHAT? », « IS THIS MARTIAL ARTS..? », « A CHANCE...? » | ✅ titre et hashtags par GPT, sinon un modèle simple |

Carte graphique : Whisper (CTranslate2) et onnxruntime-gpu 1.23.2 utilisent les
bibliothèques CUDA 12 installées par paddlepaddle-gpu (`manhwa/gpu.py`). onnxruntime-gpu
≥ 1.24 demande CUDA 13. Le détecteur de bulles passe de 0,6 s à 0,05 s par image.

Prochaine étape : l'épisode 2 annoté en entier (toutes les bulles, qui parle réplique par
réplique, un son par case choisi sans « Valider les propositions »). Il servira à refaire
le banc sur un épisode qui n'a pas servi aux réglages.

### A. Réécouter la voix (Whisper) et contrôler la vidéo (M)
**Remplace :** écouter la vidéo pour trouver les mots dits de travers.
- **A1.** Après la voix, chaque réplique (`frame["segments"]`) est retranscrite par
  faster-whisper (small en int8 ; medium sur la carte graphique si le banc le justifie).
  On compare au texte prévu (mots normalisés, taux d'erreur par réplique). Au-delà d'un
  seuil, la réplique est signalée « La voix a dit : … ». Résultat gardé dans le segment
  (`heard`, `wer`), recalculé seulement quand l'audio change.
- Bonus : un mot du texte que la voix « n'arrive pas à dire » (« MAth », « IDON'T ») est
  souvent une erreur de lecture → envoyé au chantier B comme mot suspect.
- Les temps des mots donnés par Whisper serviront aussi aux sous-titres karaoké quand le
  moteur de voix ne les donne pas (Kokoro, Chatterbox).
- **A2. Contrôle automatique du rendu**, à partir de `steps.render.timeline` et des pistes
  audio : réplique manquante ou coupée, silence trop long, case affichée moins de 0,6 s,
  bruitage qui couvre une voix, durée totale. Liste dans l'onglet Vidéo (« Contrôle »),
  avec le bouton « aller corriger » qui existe déjà.
- **Code :** `manhwa/listen.py` (nouveau), étape `listen` dans `jobs.py` après `tts` ;
  onglet Vidéo.
- **Fini quand :** sur le ch. 1, au moins 80 % des corrections de texte que tu as
  acceptées seraient signalées par Whisper, avec moins de 10 fausses alertes.

### B. Texte : deux lectures, correction locale, charabia (M)
**Remplace :** la plus grande partie de la relecture GPT du texte.
- **B1. Double lecture des bulles douteuses.** Si PaddleOCR est peu sûr (confiance basse
  ou peu de vrais mots), la même zone est relue par l'OCR de Windows (déjà branché,
  30× plus rapide). Les deux lectures sont alignées mot à mot. Si elles sont d'accord, la
  confiance monte. Sinon, on garde la variante qui a le plus de vrais mots. Si on ne peut
  pas trancher, la bulle passe « à vérifier ».
- **B2. Correction guidée.** On ne touche qu'aux mots absents du dictionnaire :
  - mots collés (« IDON'T » → « I DON'T ») : découpage par programmation dynamique sur la
    liste de fréquences de pyspellchecker, déjà installée ;
  - casse (« sO… » → « SO… ») ;
  - une lettre fausse (distance 1 ou 2, mot fréquent).

  Le style tout en majuscules et la ponctuation sont gardés.
- **B3. Charabia.** Un score est calculé : part des lettres dans de vrais mots, rapport
  voyelles / consonnes, chiffres mêlés aux lettres, motifs répétés (« AAA9CAEAAA »).
  Sous le seuil, la bulle passe en « pas du texte », d'office.
- Les corrections locales s'affichent dans l'onglet Relecture comme celles de GPT
  (`by: "local"`), avec la même file et les mêmes boutons A / R / E.
- **Code :** `manhwa/textfix.py` (nouveau), appelé par `bubbles.py`
  (`BUBBLES_VERSION` +1) ; `review.py` accueille les propositions locales.
- **Fini quand :** au moins 70 % des corrections de texte acceptées sur le ch. 1 sont
  retrouvées sans GPT, et aucune correction ne casse une bonne phrase.

### C. Type de bulle par la forme (M)
**Remplace :** la décision « réplique / pensée / narration / bruitage » de GPT.
- **C1. Détecteur de bulles** (comic-text-and-bubble-detector, ONNX int8) : boîtes des
  bulles et des zones de texte. Chaque ligne lue est rattachée à sa bulle. Un texte hors
  de toute bulle est un bruitage ou un encadré.
- **C2. Forme du contour**, à l'intérieur de chaque bulle :
  - encadré rectangulaire = narration : remplissage de la boîte proche de 1, 4 coins
    (`approxPolyDP`), souvent un fond coloré ou noir ;
  - nuage ou pointillés = pensée : beaucoup de creux sur le contour (convexity defects),
    bord en tirets ;
  - ovale avec une pointe = réplique.
- **C3. CLIP** (déjà installé) sur l'image de la bulle, comme troisième avis : « un
  encadré de narration rectangulaire », « une bulle de dialogue ronde », « une bulle de
  pensée en nuage », « des lettres de bruitage dessinées ».
- Les trois avis votent pour donner le type et la confiance.
- **Code :** `manhwa/balloons.py` (nouveau), utilisé par `bubbles.py`.
- **Fini quand :** au moins 90 % des types de bulle du ch. 1 sont d'accord avec la
  référence.

### D. Visages et personnages (M)
**Remplace :** ranger les visages à la main, et les personnages non détectés (ch. 1,
cases 63 à 65).
- **D1. Détecteurs deepghs** (ONNX, MIT) : têtes d'anime (avec les cheveux, comme
  `head_box` aujourd'hui) en plus de YuNet et animeface. Détection des corps entiers pour
  les personnages de dos ou de loin : ils comptent pour « qui parle » même sans visage.
- **D2. CCIP** à la place de DINOv2 pour décrire une tête. CCIP est entraîné à
  reconnaître le même personnage d'anime, alors que DINOv2 est généraliste. Les seuils
  (`MATCH`, `NOT_FACE_MATCH`) sont recalés sur le banc, avec tes regroupements du ch. 1
  comme référence.
- **D3.** La comparaison avec les images du wiki (noms proposés) passe aussi par CCIP.
- Tes corrections restent des modèles (déjà le cas) : `FACES_VERSION` +1, les visages
  rangés à la main sont gardés.
- **Code :** `faces.py` (modèles, `detect`, `embed`), `cast.py` (seuils),
  `ingest/wiki.py`.
- **Fini quand :** au moins 95 % des visages du ch. 1 sont dans le bon groupe dès la
  première analyse, et la personne des cases 63 à 65 est trouvée.

### E. Qui parle : pointe de la bulle et alternance (M)
**Remplace :** valider chaque réplique.
- **E1. La pointe.** On prend le contour de la bulle (C1/C2) et on cherche le point le
  plus éloigné de l'ellipse qui l'entoure : c'est la pointe. Sa direction donne un rayon.
  Chaque candidat (tête, visage, corps) est noté selon l'angle et la distance à ce rayon.
- **E2. L'alternance.** Dans une même scène, deux personnages qui se répondent alternent.
  Deux bulles collées dans la même case viennent du même orateur. Un encadré revient au
  narrateur. On garde la meilleure suite d'orateurs sur la scène (un calcul de type
  Viterbi sur les répliques).
- **E3. Le vote** : pointe, visage le plus proche (l'actuel), alternance, et GPT s'il est
  là. Une réplique est validée d'office si l'écart avec le deuxième candidat est net.
- **Code :** `manhwa/speakers.py` (nouveau), appelé par `cast.lines()` pour la
  `suggestion` et sa confiance.
- **Fini quand :** au moins 90 % des 145 « qui parle » du ch. 1 sont justes sans clic
  (on mesure d'abord le niveau du plus proche visage seul).

### F. Ton (émotion) (S → M)
**Remplace :** le ton donné par GPT (et le « neutre » partout quand il n'y a pas de clé).
- **F1. Émotion du texte** : roberta go_emotions (ONNX, version int8). Ses 28 émotions
  sont ramenées aux nôtres (`EMOTIONS` : colère, tristesse, peur, joie, surprise,
  réflexion…).
- **F2. Ponctuation** : « ! » et « ?! » vers la colère ou la surprise, « … » vers
  l'hésitation ou la tristesse, réplique très courte et exclamée vers un cri. Le tout en
  majuscules est ignoré, car un manhwa est toujours en majuscules.
- **F3. Visage de l'orateur** : CLIP (déjà là) sur sa tête : « un visage en colère »,
  « en larmes », « effrayé », « souriant », « neutre ».
- Les trois avis votent. Un ton choisi par toi (`emotion_by: user`) n'est jamais écrasé.
- **Code :** `manhwa/emotion.py` (nouveau), à la place de l'émotion GPT dans
  `review.effective()` quand GPT n'en a pas donné.
- **Fini quand :** au moins 70 % d'accord avec les tons validés du ch. 1, et aucun
  « en colère » sur une réplique calme (écoute de contrôle).

### G. Voix vraiment différentes et plus expressives (M → L)
**Remplace :** le constat « toutes les voix se ressemblent ».
- **G1. Règle sans modèle** (S), dans `voices.auto_voice` et les propositions :
  - les personnages principaux n'ont jamais la même voix de base ;
  - deux voix proches sont séparées par l'accent (US, UK, IE, AU, IN, NG) et d'au moins
    8 Hz de hauteur ;
  - l'âge tiré du wiki (cheveux blancs, « old », « elder ») donne une voix plus grave et
    plus lente.
- **G2. Kokoro** (M) : un deuxième moteur de voix dans `tts.py`, derrière la même
  interface qu'edge-tts.
  - Petit (82 M de paramètres), rapide même sans carte graphique, une cinquantaine de
    voix anglaises.
  - Pas de réglage de hauteur : on choisit la voix, ou on décale l'audio après coup.
  - Les temps des mots viennent de Whisper (A1).
- **G3. Chatterbox** (L) : voix expressives avec une intensité réglable (le ton du
  chantier F commande l'intensité), et une voix de référence de 10 s par personnage.
  - Il demande torch 2.6 et des versions figées de ses bibliothèques. Il tourne donc dans
    un venv à part (`.venv-tts`), comme un petit service local appelé par le Studio, ou
    via sa version ONNX si elle suffit.
  - Environ 3 à 4 Go de mémoire vidéo : jamais en même temps que l'OCR (les travaux sont
    déjà en file).
- Dans Personnages, chaque carte gagne un choix de moteur (edge / Kokoro / Chatterbox),
  avec le même bouton ▶.
- **Fini quand :** à l'écoute, tu reconnais chaque personnage principal les yeux fermés,
  et la voix du ch. 1 se fait en moins de 10 minutes sur la 3050.

### H. Sons sans clic (M)
**Remplace :** choisir les sons case par case.
- **H1. Pilote des sons** (S) : à « Tout faire », les propositions sûres (CLIP au-dessus
  de son seuil, GPT, bruitage reconnu) vont d'office dans la vidéo ; le reste attend dans
  la file.
- **H2. Bruitage dessiné → son** (S) : un dictionnaire d'onomatopées (BAM, THUD, CRACK,
  SLASH, SWOOSH, BOOM, KNOCK, DRIP…), avec une recherche floue sur le texte lu. Les
  bruitages coréens, rarement lisibles, restent à CLIP.
- **H3. Florence-2** (M, ONNX) : une phrase qui décrit chaque case (« un homme lève une
  faux dans un village en feu »), calculée une fois par chapitre. Ses mots clés renforcent
  le choix du son. La même description sert de contexte aux chantiers C, E et F.
- **H4. Seuils par catégorie** (S), calés sur tes choix du ch. 1 ; un CLIP plus grand
  (ViT-B/16 ou L/14) seulement si le banc montre un gain.
- **H5. Plus tard :** fabriquer avec Stable Audio Open les catégories absentes (pluie,
  foule, oiseaux, épées qui s'entrechoquent). Ils sont fabriqués **une fois** et ajoutés
  à la bibliothèque, pas à chaque vidéo. La licence est à relire avant.
- **Code :** `scene.py`, `sfx.py`, et `manhwa/describe.py` (nouveau, Florence-2).
- **Fini quand :** au moins 70 % des sons choisis d'office sont ceux que tu aurais pris.

### I. Musique selon l'ambiance (M)
**Remplace :** la même nappe sur tout l'épisode.
- Des dossiers `music/<ambiance>/` (calme, tension, combat, tristesse, mystère). Sans
  fichier, une nappe générée par ambiance, comme `ambient.py` aujourd'hui, pour que ça
  marche tout de suite.
- L'ambiance de chaque passage vient du chantier H (feu, sang, combat), du ton des
  répliques (chantier F) et des changements de scène. La musique change aux changements
  de scène, avec un fondu enchaîné.
- Pour TikTok : de la musique libre (CC0) ou à toi, pour éviter les réclamations de
  droits.
- **Code :** `ambient.py`, `render._music_track` (plusieurs morceaux), étape `mood`.
- **Fini quand :** le ch. 1 a au moins deux ambiances qui changent à des endroits qui ont
  du sens.

### J. Pilote automatique (M) — la pièce qui relie tout
- Chaque décision porte sa confiance. Une section `[auto]` dans `config.toml` donne les
  seuils, avec deux réglages tout faits : prudent et confiant.
- « Tout faire » applique tout ce qui est sûr. Les files du Studio ne montrent plus que
  les vrais doutes, marqués « décidé par la machine » avec un bouton Annuler.
- **Fini quand :** du lien à la vidéo sans aucun clic, et moins de 15 doutes par chapitre
  dans le Studio.

### K. LLM local de secours (M, facultatif)
- Qwen2.5-7B-Instruct compressé (Q4, Apache-2.0) via llama.cpp ou Ollama, branché sur
  `llm.chat()` quand la clé GPT manque ou a expiré.
- Lent sur la 3050 (une partie reste en mémoire vive) : on ne lui donne que les cas
  douteux des chantiers B, C et E, jamais tout le chapitre.

## Mémoire vidéo : un modèle à la fois

| Modèle | Taille | Où il tourne |
|---|---|---|
| CLIP ViT-B/32 int8 (déjà là) | ≈ 150 Mo | processeur |
| Détecteur de bulles int8, YOLO deepghs | petits (à mesurer) | processeur ou carte |
| CCIP | à mesurer | processeur ou carte |
| Whisper small / medium | 244 M / 769 M paramètres | processeur (int8) ou carte |
| roberta go_emotions | 125 M paramètres | processeur |
| Kokoro | 82 M paramètres | processeur ou carte |
| Florence-2 base / large | 0,23 / 0,77 milliard | carte |
| Chatterbox | ≈ 0,5 milliard, 3–4 Go | carte, seul |

## Phases

| # | Phase | Contenu | Fini quand… |
|---|---|---|---|
| 0 | ✅ **Banc** | chantier 0 : `python -m manhwa bench <chapitre> [--freeze]`, confiance de « qui parle » | Le niveau d'aujourd'hui est mesuré sur le ch. 1 (voir plus haut) |
| 1 | ✅ **Gains rapides, sans nouveau gros modèle** (E2 abandonné, C2–C3 reporté : voir plus haut) | A1 Whisper, A2 contrôle, B2–B3 texte, C2–C3 forme + CLIP, E2 alternance, F2 ponctuation, G1 voix distinctes, H1 pilote des sons, H2 onomatopées | Moins de la moitié des clics d'aujourd'hui sur le ch. 1 |
| 2 | ✅ **Nouveaux modèles ONNX légers** (CCIP et Kokoro gardés ; pointe, têtes, émotion, double lecture : mesurés, pas gardés) | C1 bulles → E1 pointe, D1–D3 deepghs + CCIP, F1 émotion du texte, B1 double lecture, G2 Kokoro | « Qui parle » ≥ 90 %, types ≥ 90 %, visages ≥ 95 % |
| 3 | ✅ **Modèles lourds** (Chatterbox et musique gardés ; LLM local retiré, GPT reste ; Florence-2 pas gardé pour les sons) | G3 Chatterbox (venv à part), H3 Florence-2, I musique, K LLM local | Voix reconnaissables les yeux fermés, ambiances qui changent |
| 4 | ✅ **Pilote automatique** | J | Lien → vidéo sans clic, < 15 doutes par chapitre |

Les sous-titres karaoké et la découpe en parties de 60–90 s (PLAN_V2, phases 4–5)
peuvent se faire en parallèle : ils ne dépendent que de A1 pour les temps des mots
(Kokoro, Chatterbox) ; edge-tts les donne déjà.

## Décisions à prendre

- Le moteur de voix par défaut, après une écoute à l'aveugle : edge-tts, Kokoro ou
  Chatterbox.
- Les seuils du pilote : prudent (plus de doutes dans le Studio) ou confiant (moins de
  clics, plus d'erreurs possibles).
- La musique : tes morceaux rangés par ambiance, ou les nappes générées.

## Risques

- **Modèles entraînés sur du manga noir et blanc** : le webtoon en couleur peut les
  dérouter. Le banc tranche ; on garde ce qui marche aujourd'hui en repli.
- **Bibliothèques lourdes** (torch pour Chatterbox, Florence-2 hors ONNX) → venv à part,
  pour ne jamais casser le Studio.
- **6 Go de mémoire vidéo** → un modèle à la fois, libéré après l'étape ; sinon le
  processeur, plus lent.
- **Les licences peuvent changer** → revérifiées à l'ajout de chaque modèle, empreinte
  SHA-256 figée.
- **La référence du banc contient le texte du chapitre** (droits d'auteur) → dans
  `.studio/`, jamais commitée, comme `ocr_gold.json`.
