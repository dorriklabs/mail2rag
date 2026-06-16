# Antigravity Project Rules (Mail2Rag)

These rules define **project-specific constraints**.
They override or refine global rules defined in `GEMINI.md`.

---

## Architecture (Python & Docker)

- **Microservices**: Strict Docker Compose architecture.
  - `mail2rag`: Main App (Email processing).
  - `ragproxy`: FastAPI API (RAG & Embeddings).
  - `streamlit_admin`: Dashboard UI.
- **State**: All persistent state MUST be in `/state` or named Docker volumes.
- **Logs**: Use `logging` (Python) or stdout/stderr for Docker capture.

## Python Standards

- **Versions**: Python 3.10+. Use `type hints` everywhere.
- **Dependencies**: When adding a lib, update `requirements.txt` in the relevant subfolder (`mail2rag/`, `ragproxy/`, etc.).
- **Async**: `ragproxy` (FastAPI) is asynchronous; use `async/await` correctly.

## Deployment & Ops

- **Docker**: Always test via `docker-compose up --build` after modification.
- **Env Vars**: NEVER hardcode secrets. Use `.env` and update `.env.example` if a new variable is added.
- **Cleanup**: Prefer `docker-compose down` to shut down cleanly.

- **RAG Proxy**: Test endpoints via Swagger (`localhost:8000/docs`).
- **UI**: Verify Streamlit rendering (`localhost:8501`).
- **Emails**: Use `send_test_email.py` to validate the ingestion flow.

---

## Quality & Testing

- **Mandatory Linting (Pre-flight)**
  - Every Python file modified must pass `flake8` or `ruff` check if available.
  - No file with syntax errors or typing violations (mypy) should ever leave the local environment.

- **Unit Testing**
  - Use `pytest` for all unit testing.
  - Execute tests within the relevant Docker container (e.g., `docker-compose exec mail2rag pytest`).

