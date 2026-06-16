---
description: Local High-Quality Development Workflow for Mail2Rag (/dev)
---

This workflow overrides the global `/dev` to provide a Python/Docker optimized autonomous process for applying modifications while ensuring maximum code quality and consistency with Mail2Rag standards.

## Phase 1: Research & Planning
1. **Environment Check**: Verify that the Docker Compose stack is running. If not, suggest running `docker-compose up -d`.
2. **Context Check**: Analyze `PROJECT_RULES.md` in the current project root.
3. **Redundancy & Indexing**: 
   - Run `/dry` to find existing logic.
   - Use `wsl python3 tools/ag_indexer.py query <symbol>` for deep Python symbol exploration if needed.

## Phase 2: Implementation
1. **Apply Changes**: Multi-step implementation respecting Python 3.10+ typing (`typing` module) and asynchronous constraints (`FastAPI`).
2. **Atomic Commits**: Small, logical changes.

## Phase 3: Autonomous Audit (Python & Docker)
- **Linting**: Run `flake8` or `ruff` on modified files to ensure PEP 8 compliance.
- **Typing**: Run `mypy` to verify strict typing.
- **Testing**: Run `pytest` inside the target container (e.g., `docker-compose exec mail2rag pytest` ou `docker-compose exec rag_proxy pytest`).

## Phase 4: Finalization & Sync
- Run `/doc-sync` (update system documentation).
- Generate `walkthrough.md` for user review.
- Suggest `/git-release` (Wait for user confirmation before deploying).

## Usage
Triggered by: "Applique [Changement] avec le workflow quality" or `/dev [Changement]`.
