import os
import asyncio
import edge_tts

# --- CONFIGURATION ---
VOICE = "en-US-ChristopherNeural"  # Voix Homme (Narrateur style film)
# Autres choix : 
# "en-US-AriaNeural" (Femme)
# "en-US-GuyNeural" (Homme standard)
# "fr-FR-HenriNeural" (Homme Français)
# "fr-FR-DeniseNeural" (Femme Française)

RATE = "+0%"  # Vitesse (+10% pour TikTok par exemple)
VOLUME = "+0%"

async def generate_audio_for_line(text, output_path):
    """Génère l'audio pour une phrase donnée"""
    try:
        communicate = edge_tts.Communicate(text, VOICE, rate=RATE, volume=VOLUME)
        await communicate.save(output_path)
        return True
    except Exception as e:
        print(f"Erreur TTS : {e}")
        return False

def parse_transcript(transcript_path):
    """Lit le fichier transcript et extrait image -> texte"""
    data = []
    if not os.path.exists(transcript_path):
        return data
        
    with open(transcript_path, "r", encoding="utf-8") as f:
        # On sépare par double saut de ligne (comme généré par le Slicer)
        blocks = f.read().split("\n\n")
        
    for block in blocks:
        block = block.strip()
        if not block: continue
        
        # Format attendu : [frame_0001.jpg] : Bla bla bla
        if "]" in block and ":" in block:
            try:
                parts = block.split("]")
                # Nom du fichier image (ex: frame_0001.jpg)
                img_name = parts[0].replace("[", "").strip()
                # Texte (ex: Bla bla bla)
                text = parts[1].split(":", 1)[1].strip()
                
                if text and len(text) > 1:
                    data.append((img_name, text))
            except:
                pass
    return data

async def main():
    print("--- GÉNÉRATEUR DE VOIX (EDGE-TTS) ---")
    
    folder_path = input("Chemin du dossier du chapitre : ").strip('"')
    frames_folder = os.path.join(folder_path, "frames_tiktok")
    transcript_path = os.path.join(frames_folder, "transcript.txt")
    
    if not os.path.exists(transcript_path):
        print("Erreur : Pas de transcript.txt trouvé dans frames_tiktok.")
        return

    # 1. Lire le texte
    dialogues = parse_transcript(transcript_path)
    print(f"-> {len(dialogues)} lignes de texte trouvées.")
    
    # 2. Générer les audios
    count = 0
    for img_filename, text in dialogues:
        # On remplace l'extension .jpg par .mp3 pour le nom du fichier audio
        audio_filename = "audio_" + os.path.splitext(img_filename)[0] + ".mp3"
        output_path = os.path.join(frames_folder, audio_filename)
        
        # Vérif si déjà fait
        if os.path.exists(output_path):
            print(f" [Skip] {audio_filename} existe déjà.")
            continue

        print(f" [TTS] Génération pour {img_filename}...")
        print(f"       Texte : {text[:40]}...")
        
        success = await generate_audio_for_line(text, output_path)
        if success:
            count += 1
    
    print(f"--- TERMINE : {count} fichiers audio générés ---")

if __name__ == "__main__":
    asyncio.run(main())