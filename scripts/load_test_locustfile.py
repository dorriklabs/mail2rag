import random
import time
from locust import HttpUser, task, between

# Liste de requêtes variées pour éviter le cache sémantique
QUERIES = [
    "Qu'est-ce que le PLUI ?",
    "Comment obtenir un passeport ?",
    "Quels sont les horaires de la piscine municipale ?",
    "Combien coûte la cantine scolaire ?",
    "Je veux renouveler ma carte d'identité.",
    "Qui est le maire de la ville ?",
    "Quelles sont les dates des prochaines élections ?",
    "Comment inscrire mon enfant à la crèche ?",
    "Où déposer mes encombrants ?",
    "Quels sont les documents à fournir pour un mariage ?"
]

class RAGUser(HttpUser):
    # Simule un temps de réflexion de 1 à 3 secondes entre chaque requête d'un même utilisateur
    wait_time = between(1, 3)

    @task(3)
    def test_rag_only(self):
        """
        Test de charge sur le endpoint /rag uniquement.
        Ceci sollicite Qdrant et le modèle d'embedding (bge-m3).
        """
        payload = {
            "query": random.choice(QUERIES),
            "top_k": 5,
            "final_k": 3
        }
        with self.client.post("/rag", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Échec RAG - Code: {response.status_code}")

    @task(1)
    def test_chat_full(self):
        """
        Test de charge sur le endpoint /chat complet.
        Ceci sollicite Qdrant, bge-m3 ET le LLM (LM Studio).
        (Pondération plus faible pour ne pas saturer instantanément le GPU local)
        """
        payload = {
            "query": random.choice(QUERIES),
            "top_k": 5,
            "final_k": 3,
            "history": []
        }
        with self.client.post("/chat", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                # Vérifier si on n'a pas renvoyé l'erreur catch-all "Désolé..."
                data = response.json()
                if data.get("answer", "").startswith("Désolé"):
                    response.failure("Échec Chat - Erreur LLM ou technique remontée dans la réponse")
                else:
                    response.success()
            elif response.status_code == 400:
                # Si par hasard une injection était détectée, on marque en échec
                response.failure("Échec Chat - Code 400")
            else:
                response.failure(f"Échec Chat - Code: {response.status_code}")
