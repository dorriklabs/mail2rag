# Règles du Projet Mail2Rag

## Architecture (Python & Docker)

- **Microservices** : Architecture Docker Compose stricte.
  - `mail2rag` : App principale (Traitement emails).
  - `ragproxy` : API FastAPI (RAG & Embeddings).
  - `streamlit_admin` : Dashboard UI.
- **État** : Tout état persistant DOIT être dans `/state` ou des volumes Docker nommés.
- **Logs** : Utiliser `logging` (Python) ou stdout/stderr pour que Docker capture les logs.

## Python Standards

- **Versions** : Python 3.10+. Utiliser les `type hints` partout.
- **Dépendances** : Si ajout de lib, mettre à jour `requirements.txt` dans le sous-dossier concerné (`mail2rag/`, `ragproxy/`, etc.).
- **Async** : `ragproxy` (FastAPI) est asynchrone, utiliser `async/await` correctement.

## Deployment & Ops

- **Docker** : Toujours tester via `docker-compose up --build` après modification.
- **Env Vars** : JAMAIS de secrets en dur. Utiliser `.env` et mettre à jour `.env.example` si nouvelle variable.
- **Nettoyage** : Préférer `docker-compose down` pour éteindre proprement.

## Testing & Validation

- **RAG Proxy** : Tester les endpoints via Swagger (`localhost:8000/docs`).
- **UI** : Vérifier le rendu Streamlit (`localhost:8501`).
- **Emails** : Utiliser `send_test_email.py` pour valider le flux d'ingestion.
