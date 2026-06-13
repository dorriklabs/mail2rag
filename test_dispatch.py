import smtplib
from email.message import EmailMessage
import time

def send_test_email():
    msg = EmailMessage()
    msg.set_content("Bonjour, je souhaite construire un abri de jardin sur mon terrain. Pouvez-vous me fournir le Plan Local d'Urbanisme ? Merci d'avance.")
    msg["Subject"] = "Demande de permis de construire"
    msg["From"] = "accueil@dsiatlantic.com"
    msg["To"] = "accueil@dsiatlantic.com"

    print("Connexion au serveur SMTP...")
    with smtplib.SMTP_SSL("51.91.10.39", 465) as server:
        print("Authentification...")
        server.login("accueil@dsiatlantic.com", "RagT3st-17")
        print("Envoi de l'email...")
        server.send_message(msg)
        print("Email envoyé avec succès !")

if __name__ == "__main__":
    send_test_email()
