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

## Quality & Safety

- **Cleanup**
  - All debug code (`print`, `pdb`, `breakpoint`)  
    **must be removed before review**.
  - Temporary code is not acceptable in committed changes.

- **Mandatory Linting (Pre-flight)**
  - Every Python file modified must pass `flake8` or `ruff` check if available.
  - No file with syntax errors or typing violations (mypy) should ever leave the local environment.

---

## Workflow & Indexing (IA-Aware)

- **Index Smart**
  - Use `wsl python3 tools/ag_indexer.py query <symbol>` when exploring
    **new or unfamiliar** parts of the codebase.

- **Symbol-First Navigation**
  - Always search by symbol (class/function) before browsing files manually.

- **Skip When Redundant**
  - Do NOT use the indexer if:
    - the file is already open,
    - the location is known from context,
    - or you are continuing work on a recently modified file.

- **No Guessing**
  - Never infer file paths or symbol locations without:
    - querying the indexer, or
    - relying on an explicitly opened file.

- **Mention When Used**
  - Explicitly state *"Interrogation de l'indexeur..."* when a query is performed.
