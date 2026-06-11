#!/usr/bin/env python3
"""
Script de test avancé pour Mail2RAG (Vision, PDF, DOCX)
Télécharge des fichiers exemples (Image, PDF, DOCX) et les envoie par email.
"""

import os
import smtplib
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

FILES_TO_DOWNLOAD = {
    "sample_image.jpg": "https://raw.githubusercontent.com/QwenLM/Qwen-VL/master/assets/demo.jpg",
    "sample_doc.pdf": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
    # Fetching a reliable sample docx file
    "sample_word.docx": "https://file-examples.com/wp-content/storage/2017/02/file-sample_100kB.docx"
}

def download_files():
    downloaded = []
    print("📥 Téléchargement des fichiers de test...")
    
    # Use a generic user agent for file-examples.com
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for filename, url in FILES_TO_DOWNLOAD.items():
        filepath = Path(filename)
        if not filepath.exists():
            try:
                print(f"   Téléchargement de {filename}...")
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as response, open(filepath, 'wb') as out_file:
                    out_file.write(response.read())
                downloaded.append(filepath)
            except Exception as e:
                print(f"   ❌ Erreur pour {filename}: {e}")
                # Fallback for DOCX if the first one fails
                if filename.endswith(".docx"):
                    fallback_url = "https://raw.githubusercontent.com/python-openxml/python-docx/master/tests/test_files/test.docx"
                    try:
                        print(f"   Essai url alternative pour DOCX...")
                        req = urllib.request.Request(fallback_url, headers=headers)
                        with urllib.request.urlopen(req, timeout=15) as response, open(filepath, 'wb') as out_file:
                            out_file.write(response.read())
                        downloaded.append(filepath)
                    except Exception as e2:
                        print(f"   ❌ Échec définitif pour {filename}: {e2}")
        else:
            downloaded.append(filepath)
            print(f"   ✅ {filename} déjà présent.")
    return downloaded

def send_advanced_test(files):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)
    imap_user = os.getenv("IMAP_USER")
    
    if not all([smtp_server, smtp_user, smtp_password, imap_user]):
        print("❌ Erreur : Variables d'environnement SMTP/IMAP manquantes dans .env")
        return False
        
    print(f"\n📧 Préparation de l'email de test...")
    
    msg = MIMEMultipart()
    msg['From'] = smtp_from
    msg['To'] = imap_user
    msg['Subject'] = f"[TEST MULTIMEDIA] Mail2RAG Vision & Docs - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    body = """Bonjour,

Ceci est un email de test avancé pour valider la capacité multimodale de Mail2RAG.

Pièces jointes incluses :
1. Une Image JPG (test Vision / OCR)
2. Un document PDF (test Tika PDF)
3. Un document Word DOCX (test Tika DOCX)

Le système doit pouvoir extraire le texte de tous ces formats.
"""
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    for filepath in files:
        if filepath.exists():
            with open(filepath, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={filepath.name}')
            msg.attach(part)
            print(f"   📎 Ajouté : {filepath.name}")

    try:
        print(f"\n📤 Envoi en cours...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        print(f"✅ Email multimédia envoyé avec succès !")
        return True
    except Exception as e:
        print(f"❌ Erreur d'envoi : {e}")
        return False

if __name__ == "__main__":
    files = download_files()
    if files:
        send_advanced_test(files)
        # Nettoyage
        for f in files:
            f.unlink()
            print(f"🧹 Nettoyé : {f.name}")
    else:
        print("❌ Aucun fichier n'a pu être téléchargé.")
