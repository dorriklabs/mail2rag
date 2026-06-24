# Antigravity Project Rules - Mail2Rag

These rules define project-specific constraints for Mail2Rag.

They override or refine global defaults from `GEMINI.md`, except for explicit user instructions, safety, security, and data integrity constraints.

## Architecture

* Use a strict Docker Compose microservices architecture.
* Services:

  * `mail2rag`: email ingestion and processing.
  * `ragproxy`: FastAPI API for RAG, embeddings, and retrieval.
  * `streamlit_admin`: Streamlit dashboard UI.
* Keep service responsibilities separated.
* Do not move logic across services unless explicitly required.
* Apply DRY inside each service first. Share code across services only when the abstraction is stable, clearly owned, and does not increase coupling or deployment complexity.
* All persistent state must live in `/state` or named Docker volumes.
* Do not write runtime state into application source folders.
* Use `logging` in Python and stdout/stderr for Docker-captured logs.

## Python

* Use Python 3.10+.
* Use type hints for all new or modified Python code.
* Prefer explicit dependencies over hidden globals.
* When adding dependencies, update the relevant service `requirements.txt`.
* Do not add dependencies globally if only one service needs them.
* Avoid broad dependency upgrades unless explicitly requested.

### Typage Strict (Pylance/Pyright)
L'analyseur statique est configuré avec des règles de typage très strictes. Pour éviter les faux positifs et les soulignements rouges dans l'IDE :
* **Variables d'environnement (`os.getenv`)** : Elles retournent un type `Optional[str]`. S'il faut les passer à des fonctions exigeant une chaîne stricte (`str`), forcez la conversion via `str(var)` ou `var or ""`.
* **Retours de dictionnaires (`.get()`)** : Étant donné que `.get()` peut retourner `None`, annotez explicitement vos variables avec `| None` (ex: `service: MonService | None = ...`) et vérifiez leur existence (`if service:`) avant d'en utiliser les méthodes.
* **Imports dynamiques ou conflictuels** : Lors d'injections dans le `sys.path` ou en cas de conflits de noms de modules inter-dossiers (ex: plusieurs `app.py`), l'analyse statique peut échouer. Utilisez le commentaire `# type: ignore` en fin de ligne pour faire taire l'analyseur sur ces imports précis.

## Service Rules

* `ragproxy`:

  * FastAPI code is asynchronous.
  * Use `async/await` correctly.
  * Do not block the event loop with synchronous I/O in async routes.
  * Preserve existing endpoint contracts unless explicitly requested.
  * Test changed endpoints through Swagger when practical: `localhost:8000/docs`.

* `streamlit_admin`:

  * Keep UI orchestration separate from reusable domain/service logic where practical.
  * User-facing UI text must be French unless the existing screen clearly uses English.
  * Verify rendering after UI changes when practical: `localhost:8501`.

* `mail2rag`:

  * Preserve the ingestion flow unless explicitly requested.
  * Use `send_test_email.py` to validate email ingestion changes when relevant.
  * Log ingestion failures with useful context, without leaking secrets or sensitive payloads.

## Docker & Env

* Use Docker Compose as the default execution environment.
* Prefer `docker-compose`; use `docker compose` only if needed by the environment.
* Before proposing a final commit after code, dependency, Dockerfile, or env changes, run:

  * `docker-compose up --build`
* If it cannot be run, state why.
* Use `docker-compose down` for clean shutdown.
* Use `.env` for local secrets.
* Update `.env.example` when adding or renaming environment variables.
* Never hardcode secrets or bake them into images.

## State & Data

* Persistent state must be stored only in `/state` or named Docker volumes.
* Prefer idempotent processing for ingestion and indexing flows.
* Do not delete or reset `/state`, volumes, indexes, embeddings, or persisted emails without explicit confirmation.

## Quality, Testing & Workflows

* Use Antigravity workflows instead of manual commands whenever possible to ensure standardization and safety.

* **Linting & Formatting**:
  * Before proposing a commit, run `/lint` to perform syntax checks, type checking, and static analysis (ruff/flake8).
* **Testing**:
  * Use `/test` to execute automated test suites (pytest) within the appropriate Docker containers (`mail2rag`, `ragproxy`, `streamlit_admin`).
  * Use the project-specific `/mail2rag-unit-tests` when creating new functions to ensure complete coverage.
* **Code Lifecycle**:
  * For major refactoring, use `/refactor`.
  * After validated tests and significant changes, always propose `/git-release` to version the code.

* If a required check cannot be run, state the skipped check, the reason, and the safest next action.
