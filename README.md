# Manhwa to TikTok Automator

Une suite d'outils Python complète pour automatiser la création de vidéos TikTok/Shorts à partir de chapitres de Manhwa/Webtoon.

Ce projet gère le processus de A à Z : Téléchargement, Découpage intelligent, OCR (Extraction de texte), Voix Off (TTS) et Assemblage vidéo synchronisé.

## Fonctionnalités

1.  **Scraper Avancé** : Téléchargement multi-thread (rapide) des chapitres, compatible `.webp`, avec contournement Cloudflare basique.
2.  **Smart Slicer (Découpeur)** : Interface graphique pour découper les longues pages webtoons en format vertical (9:16).
    * *Auto-Resize* : Gère les images trop larges sans crash.
    * *Smart OCR* : Détecte et extrait le texte des bulles (filtre anti-bruit inclus).
3.  **TTS Generator** : Génère des voix off "Neural" de haute qualité (via Microsoft Edge TTS) pour chaque dialogue extrait.
4.  **Auto-Assembler** : Crée une vidéo MP4 où chaque image est parfaitement synchronisée avec sa voix off.

## Pré-requis

* [Python 3.8+](https://www.python.org/downloads/)
* [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (Indispensable pour l'extraction de texte).
    * *Note : Vérifiez que le chemin dans `advanced_slicer.py` correspond bien à votre installation (`C:\Program Files\Tesseract-OCR\tesseract.exe`).*

## Installation

1.  Clonez ce dépôt :
    ```bash
    git clone [https://github.com/VOTRE_NOM_UTILISATEUR/Manhwa-Automator.git](https://github.com/VOTRE_NOM_UTILISATEUR/Manhwa-Automator.git)
    cd Manhwa-Automator
    ```

2.  Installez les dépendances :
    ```bash
    pip install -r requirements.txt
    ```

3.  Installez les navigateurs Playwright :
    ```bash
    playwright install
    ```

Suivez les scripts dans l'ordre :

### 1. Téléchargement (`advanced_scraper.py`)

Télécharge les chapitres bruts.
```bash
python advanced_scraper.py

```

* Entrez l'URL de la série (ex: AsuraScan).
* Les images sont filtrées (pubs supprimées) et sauvegardées proprement.

### 2. Découpage & OCR (`advanced_slicer.py`)

Transforme le strip infini en images TikTok + Extrait le texte.

```bash
python advanced_slicer.py

```

**Contrôles :**

* `Molette Souris` : Scroller.
* `ENTRÉE` : Sauvegarder la frame + Lire le texte (OCR).
* `N` : Image suivante (Passer).
* `B` : Retour arrière.
* `Q` : Quitter.

### 3. Génération Audio (`tts_generator.py`)

Transforme le fichier `transcript.txt` en fichiers `.mp3`.

```bash
python tts_generator.py

```

### 4. Assemblage Vidéo (`assembler_sync.py`)

Crée le fichier final synchronisé.

```bash
python assembler_sync.py

```

* Génère un fichier `IMPORT_ME_IN_CAPCUT.mp4`.

---

## Finition (CapCut)

Pour un résultat professionnel :

1. Ouvrez **CapCut**.
2. Importez le fichier `IMPORT_ME_IN_CAPCUT.mp4` généré.
3. Faites **Clic-droit > Découpage de scène** (ou *Scene Split*).
4. Ajoutez vos transitions et effets !

---

## Disclaimer

Ce projet est destiné à un usage personnel ou éducatif. Veuillez respecter les droits d'auteur des œuvres originales et des plateformes de scanlation.

```

```