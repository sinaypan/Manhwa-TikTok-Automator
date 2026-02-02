import os
import glob
# Import compatible MoviePy v2+
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

def assemble_synced_video():
    print("--- ASSEMBLAGE SYNCHRONISÉ V3 (ANTI-CRASH) ---")
    
    folder_path = input("Chemin du dossier du chapitre : ").strip('"')
    frames_folder = os.path.join(folder_path, "frames_tiktok")
    
    if not os.path.exists(frames_folder):
        print("Erreur : Dossier frames_tiktok introuvable.")
        return

    image_files = sorted(glob.glob(os.path.join(frames_folder, "frame_*.jpg")))
    clips = []
    
    print(f"Traitement de {len(image_files)} scènes...")

    for img_path in image_files:
        filename = os.path.basename(img_path)
        audio_filename = "audio_" + os.path.splitext(filename)[0] + ".mp3"
        audio_path = os.path.join(frames_folder, audio_filename)
        
        audio_valid = False
        audio_clip = None

        # 1. Vérification de sécurité du fichier audio
        if os.path.exists(audio_path):
            # Vérifier si le fichier n'est pas vide (0 octet)
            if os.path.getsize(audio_path) > 100:
                try:
                    # On tente de charger l'audio
                    audio_clip = AudioFileClip(audio_path)
                    audio_valid = True
                except Exception as e:
                    print(f" [!] Fichier audio corrompu détecté : {audio_filename} (Erreur ignorée)")
                    audio_valid = False
            else:
                print(f" [!] Fichier audio vide détecté : {audio_filename}")
        
        # 2. Création du clip vidéo
        if audio_valid and audio_clip:
            duration = audio_clip.duration + 0.2
            # Syntaxe MoviePy v2
            video_clip = ImageClip(img_path).with_duration(duration)
            video_clip = video_clip.with_audio(audio_clip)
            clips.append(video_clip)
            print(f" [OK] {filename} synchro ({duration:.2f}s)")
        else:
            # Mode Muet (Fallback)
            print(f" [Mute] {filename} (Pas d'audio valide)")
            video_clip = ImageClip(img_path).with_duration(2.0)
            clips.append(video_clip)

    if not clips:
        print("Rien à assembler.")
        return

    print("Rendu de la vidéo finale... (Patience)")
    
    output_path = os.path.join(folder_path, "IMPORT_ME_IN_CAPCUT.mp4")
    
    try:
        final_video = concatenate_videoclips(clips, method="compose")
        final_video.write_videofile(
            output_path, 
            fps=24, 
            codec="libx264", 
            audio_codec="aac",
            preset="ultrafast",
            threads=4
        )
        print(f"\n--- TERMINE ! ---")
        print(f"Fichier créé : {output_path}")
    except Exception as e:
        print(f"Erreur lors du rendu final : {e}")

if __name__ == "__main__":
    assemble_synced_video()