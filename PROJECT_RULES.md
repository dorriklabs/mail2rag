# Mail2Rag Project Rules

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

## Testing & Validation

- **RAG Proxy**: Test endpoints via Swagger (`localhost:8000/docs`).
- **UI**: Verify Streamlit rendering (`localhost:8501`).
- **Emails**: Use `send_test_email.py` to validate the ingestion flow.
