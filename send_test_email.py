#!/usr/bin/env python3
"""
Script de test pour Mail2RAG
Envoie un email de test avec une pièce jointe pour valider toute la chaîne de traitement
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

def create_test_document():
    """Crée un document texte de test"""
    test_content = f"""# Document de Test Mail2RAG
    
Date de création : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Objectif
Ce document est un test automatique pour valider la chaîne complète de traitement Mail2RAG.

## Composants testés
1. **Réception IMAP** : Récupération de l'email depuis le serveur
2. **Parsing** : Extraction du sujet, corps et pièces jointes
3. **Routage** : Détermination du workspace cible
4. **Upload AnythingLLM** : Envoi du document vers AnythingLLM
5. **Embeddings** : Création des vecteurs dans Qdrant
6. **BM25** : Reconstruction automatique de l'index BM25
7. **Archive** : Sauvegarde dans l'archive locale
8. **Notification** : Envoi d'un email de confirmation

## Informations de test
- Workspace attendu : finance-factures (ou default-workspace selon votre routing.json)
- Type de document : Texte simple (.txt)
- Taille : ~1 KB

## Contenu de test
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor 
incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis 
nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.

Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore 
eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt 
in culpa qui officia deserunt mollit anim id est laborum.

## Vérifications attendues
✓ Email reçu et traité par Mail2RAG
✓ Document extrait et uploadé dans AnythingLLM
✓ Embeddings créés dans Qdrant
✓ Index BM25 reconstruit
✓ Archive créée avec un ID sécurisé
✓ Email de confirmation reçu avec lien vers l'archive

---
Généré automatiquement par send_test_email.py
"""
    
    test_file = Path("test_document_mail2rag.txt")
    test_file.write_text(test_content, encoding='utf-8')
    return test_file


def send_test_email():
    """Envoie un email de test avec pièce jointe"""
    
    # Récupérer les paramètres SMTP depuis .env
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)
    
    # Adresse de destination (même adresse que IMAP_USER pour le test)
    imap_user = os.getenv("IMAP_USER")
    
    if not all([smtp_server, smtp_user, smtp_password, imap_user]):
        print("❌ Erreur : Variables d'environnement SMTP/IMAP manquantes dans .env")
        return False
    
    print(f"📧 Préparation de l'email de test...")
    print(f"   Serveur SMTP : {smtp_server}:{smtp_port}")
    print(f"   De : {smtp_from}")
    print(f"   À : {imap_user}")
    
    # Créer le document de test
    test_file = create_test_document()
    print(f"✅ Document de test créé : {test_file}")
    
    # Créer le message
    msg = MIMEMultipart()
    msg['From'] = smtp_from
    msg['To'] = imap_user
    msg['Subject'] = f"[TEST] Mail2RAG - Validation complète - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    # Corps du message
    body = """Bonjour,

Ceci est un email de test automatique pour valider la chaîne complète de traitement Mail2RAG.

📎 Pièce jointe : test_document_mail2rag.txt

🔍 Vérifications attendues :
1. Réception et parsing de l'email
2. Extraction de la pièce jointe
3. Upload dans AnythingLLM
4. Création des embeddings dans Qdrant
5. Reconstruction de l'index BM25
6. Archivage du document
7. Envoi d'un email de confirmation

⏱️ Temps de traitement attendu : 10-30 secondes

Vous devriez recevoir un email de confirmation de Mail2RAG avec :
- Le statut de l'ingestion
- Un lien vers l'archive du document
- Les détails du workspace utilisé

---
Email généré automatiquement par send_test_email.py
"""
    
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    # Attacher le fichier
    with open(test_file, 'rb') as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
    
    encoders.encode_base64(part)
    part.add_header(
        'Content-Disposition',
        f'attachment; filename= {test_file.name}'
    )
    msg.attach(part)
    
    # Envoyer l'email
    try:
        print(f"\n📤 Connexion au serveur SMTP...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        
        print(f"🔐 Authentification...")
        server.login(smtp_user, smtp_password)
        
        print(f"📨 Envoi de l'email...")
        server.send_message(msg)
        server.quit()
        
        print(f"\n✅ Email de test envoyé avec succès !")
        print(f"\n📊 Prochaines étapes :")
        print(f"   1. Surveillez les logs de mail2rag : docker compose logs -f mail2rag")
        print(f"   2. Vérifiez votre boîte mail pour l'email de confirmation")
        print(f"   3. Consultez http://localhost:8000/test pour voir l'état du RAG Proxy")
        print(f"   4. Vérifiez http://localhost:3001 pour voir le document dans AnythingLLM")
        print(f"\n⏱️  Temps de traitement estimé : 10-30 secondes")
        
        # Nettoyer le fichier de test
        test_file.unlink()
        print(f"\n🧹 Fichier de test local supprimé")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Erreur lors de l'envoi : {e}")
        # Nettoyer le fichier de test même en cas d'erreur
        if test_file.exists():
            test_file.unlink()
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("🚀 MAIL2RAG - TEST COMPLET DE LA CHAÎNE DE TRAITEMENT")
    print("=" * 70)
    print()
    
    success = send_test_email()
    
    print()
    print("=" * 70)
    if success:
        print("✅ Test lancé avec succès !")
    else:
        print("❌ Le test a échoué")
    print("=" * 70)
