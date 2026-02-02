import os
import time
import requests
import mimetypes
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from playwright.sync_api import sync_playwright

# --- CONFIGURATION LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def sanitize_filename(name):
    return "".join([c for c in name if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).rstrip()

def create_session():
    """Crée une session de téléchargement avec des tentatives automatiques"""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    })
    return session

def smart_scroll(page):
    """Scrolle jusqu'en bas en attendant que les images chargent"""
    last_height = page.evaluate("document.body.scrollHeight")
    while True:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            page.wait_for_load_state("networkidle", timeout=2000)
        except:
            time.sleep(1)
        
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def download_task(url, folder, session, index):
    try:
        response = session.get(url, stream=True, timeout=20)
        if response.status_code == 200:
            # On garde l'extension webp si c'en est une, sinon on devine
            if ".webp" in url:
                ext = ".webp"
            else:
                content_type = response.headers.get('content-type')
                ext = mimetypes.guess_extension(content_type) or ".jpg"

            filename = f"{index:02d}{ext}"
            save_path = os.path.join(folder, filename)

            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            logging.info(f"OK: {filename}")
            return True
    except Exception as e:
        logging.error(f"Echec {url}: {e}")
    return False

def main():
    print("--- SCRAPER STRICT (.WEBP UNIQUEMENT) ---")
    base_url = input("URL de la série : ")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        logging.info(f"Connexion à {base_url}...")
        page.goto(base_url)
        
        try:
            page.wait_for_selector("span.text-xl.font-bold", timeout=5000)
        except:
            input(">>> Passe le Cloudflare et appuie sur ENTRÉE <<<")

        try:
            title_el = page.query_selector("span.text-xl.font-bold")
            manga_title = sanitize_filename(title_el.inner_text())
        except:
            manga_title = "Manhwa_Download"
        
        if not os.path.exists(manga_title): os.makedirs(manga_title)
        logging.info(f"Titre : {manga_title}")

        chapters_elements = page.query_selector_all("a[href*='chapter']")
        chapter_urls = sorted(list(set([urljoin(page.url, ch.get_attribute("href")) for ch in chapters_elements])))
        
        logging.info(f"{len(chapter_urls)} chapitres trouvés.")
        
        choice = input("Combien télécharger ? ('all' ou nombre) [Defaut: 1] : ").strip()
        
        if choice.lower() == 'all':
            pass 
        elif choice == "":
            logging.info("Défaut : 1 chapitre.")
            chapter_urls = chapter_urls[:1]
        else:
            try:
                limit = int(choice)
                chapter_urls = chapter_urls[:limit]
            except ValueError:
                chapter_urls = chapter_urls[:1]

        session = create_session()

        for idx, ch_url in enumerate(chapter_urls):
            logging.info(f"--- Chapitre {idx+1} ---")
            try:
                page.goto(ch_url)
                smart_scroll(page)
                
                # --- LE FILTRE MAGIQUE ICI ---
                # On ne prend QUE les images dont l'URL contient '.webp'
                # et qui font plus de 300px de large (double sécurité)
                image_data = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('img')).map(img => ({
                        src: img.src,
                        width: img.naturalWidth
                    })).filter(img => 
                        img.width > 300 && 
                        img.src.startsWith('http') &&
                        img.src.includes('.webp') 
                    );
                }""")
                # -----------------------------
                
                final_links = []
                seen = set()
                for img in image_data:
                    url = img['src']
                    if url not in seen:
                        final_links.append(url)
                        seen.add(url)

                if len(final_links) == 0:
                    logging.warning("Aucune image .webp trouvée ! Le site a peut-être changé de format.")
                    continue

                logging.info(f"{len(final_links)} images (.webp) détectées.")
                
                chapter_folder = os.path.join(manga_title, f"Chapitre_{idx+1}")
                if not os.path.exists(chapter_folder): os.makedirs(chapter_folder)

                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = []
                    for i, url in enumerate(final_links):
                        futures.append(executor.submit(download_task, url, chapter_folder, session, i+1))
                    for future in futures:
                        future.result()

            except Exception as e:
                logging.error(f"Erreur : {e}")

        browser.close()
        logging.info("Terminé.")

if __name__ == "__main__":
    main()