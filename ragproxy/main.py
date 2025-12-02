# main.py

import logging
from typing import List, Dict, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config import (
    USE_BM25_DEFAULT,
    MAX_QUERY_CHARS,
    MAX_TOP_K,
    BM25_INDEX_PATH,
)
from app.pipeline import RAGPipeline

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class RequestModel(BaseModel):
    query: str
    top_k: int = 20
    final_k: int = 5
    use_bm25: Optional[bool] = None  # None -> USE_BM25_DEFAULT


class Chunk(BaseModel):
    text: str
    score: float
    metadata: Dict


class ResponseModel(BaseModel):
    query: str
    chunks: List[Chunk]


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    ready: bool
    deps: Dict[str, bool]


app = FastAPI()
pipeline = RAGPipeline()


@app.post("/rag", response_model=ResponseModel)
def rag_endpoint(req: RequestModel):
    # Validation longueur query (max configurable pour éviter DoS)
    if len(req.query) > MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Query too long (max {MAX_QUERY_CHARS} characters)",
        )

    if not req.query or not req.query.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty")

    if req.top_k <= 0 or req.top_k > MAX_TOP_K:
        raise HTTPException(
            status_code=422,
            detail=f"top_k must be in (0, {MAX_TOP_K}]",
        )
    if req.final_k <= 0 or req.final_k > req.top_k:
        raise HTTPException(
            status_code=422,
            detail="final_k must be in (0, top_k]",
        )

    use_bm25 = req.use_bm25
    if use_bm25 is None:
        use_bm25 = USE_BM25_DEFAULT

    results = pipeline.run(
        query=req.query,
        top_k=req.top_k,
        final_k=req.final_k,
        use_bm25=use_bm25,
    )

    return ResponseModel(
        query=req.query,
        chunks=[Chunk(**x) for x in results],
    )


@app.get("/healthz", response_model=HealthResponse)
def healthz():
    return HealthResponse(status="ok")


@app.get("/readyz", response_model=ReadyResponse)
def readyz():
    deps = pipeline.ready_status()
    ready = all(deps.values())
    return ReadyResponse(ready=ready, deps=deps)


@app.get("/test")
def test_endpoint():
    """
    Endpoint de test complet du pipeline RAG.
    Affichage HTML élégant dans le navigateur.
    """

    results = {"timestamp": datetime.now().isoformat(), "tests": {}}

    # Test 1: Embeddings
    try:
        emb = pipeline.embedder.embed("test query")
        results["tests"]["embeddings"] = {
            "status": "ok",
            "dimension": len(emb),
            "error": None,
        }
    except Exception as e:
        results["tests"]["embeddings"] = {
            "status": "error",
            "dimension": 0,
            "error": str(e),
        }

    # Test 2: Qdrant
    try:
        qdrant_ok = pipeline.vdb.is_ready()
        results["tests"]["qdrant"] = {
            "status": "ok" if qdrant_ok else "error",
            "error": None if qdrant_ok else "Not ready",
        }
    except Exception as e:
        results["tests"]["qdrant"] = {
            "status": "error",
            "error": str(e),
        }

    # Test 3: BM25
    try:
        bm25_ready = pipeline.bm25.is_ready()
        results["tests"]["bm25"] = {
            "status": "ok" if bm25_ready else "not_configured",
            "docs_count": len(pipeline.bm25.docs) if bm25_ready else 0,
            "error": None,
        }
    except Exception as e:
        results["tests"]["bm25"] = {
            "status": "error",
            "docs_count": 0,
            "error": str(e),
        }

    # Test 4: Reranker
    try:
        mock_passages = [
            {"text": "Test document 1", "metadata": {"source": "test"}, "score": 0.9},
            {"text": "Test document 2", "metadata": {"source": "test"}, "score": 0.8},
        ]
        ranked = pipeline.reranker.rerank("test query", mock_passages)
        results["tests"]["reranker"] = {
            "status": "ok",
            "ranked_count": len(ranked),
            "error": None,
        }
    except Exception as e:
        results["tests"]["reranker"] = {
            "status": "error",
            "ranked_count": 0,
            "error": str(e),
        }

    # Résumé global
    results["overall"] = (
        "ok"
        if all(
            t.get("status") in ["ok", "not_configured"]
            for t in results["tests"].values()
        )
        else "error"
    )

    # Générer HTML
    html_content = generate_test_html(results)
    return HTMLResponse(content=html_content)


@app.post("/admin/build-bm25")
def build_bm25_index():
    """Reconstruit l'index BM25 depuis Qdrant (admin uniquement)."""
    import pickle
    from pathlib import Path
    from rank_bm25 import BM25Okapi

    try:
        logger.info("Building BM25 index from Qdrant...")

        # Vérifier que Qdrant est accessible
        if not pipeline.vdb.is_ready():
            return {
                "status": "error",
                "message": "Qdrant n'est pas accessible. Vérifiez que le conteneur Qdrant est démarré.",
            }

        # Récupérer tous les documents via l'interface abstraite
        try:
            all_docs = pipeline.vdb.get_all_documents()
        except Exception as e:
            error_msg = str(e)
            if "Not found: Collection" in error_msg or "doesn't exist" in error_msg:
                return {
                    "status": "error",
                    "message": "La collection Qdrant 'documents' n'existe pas encore.\n\n"
                    "📧 Pour créer l'index BM25, vous devez d'abord :\n"
                    "1. Envoyer un email avec pièce jointe à Mail2RAG\n"
                    "2. Attendre que Mail2RAG traite et upload dans Qdrant\n"
                    "3. Revenir ici et cliquer sur 'Construire Index'\n\n"
                    "ℹ️ La collection sera créée automatiquement lors du premier upload.",
                }
            else:
                raise

        docs = []
        meta = []

        for doc_item in all_docs:
            text = doc_item.get("text", "")
            if text:
                docs.append(text)
                meta.append(doc_item.get("metadata", {}))

        if not docs:
            return {
                "status": "error",
                "message": "La collection existe mais ne contient aucun document.\n\n"
                "📧 Pour créer l'index BM25 :\n"
                "1. Envoyez des emails avec pièces jointes à Mail2RAG\n"
                "2. Attendez que les documents soient traités\n"
                "3. Revenez ici et cliquez sur 'Construire Index'\n\n"
                f"📊 Documents actuels : 0",
            }

        # Tokenization
        tokenized = [pipeline.bm25._tokenize(doc) for doc in docs]

        # Créer index BM25
        bm25 = BM25Okapi(tokenized)

        # Sauvegarder
        index_path = Path(BM25_INDEX_PATH)
        index_path.parent.mkdir(parents=True, exist_ok=True)

        with index_path.open("wb") as f:
            pickle.dump((bm25, docs, meta), f)

        # Recharger dans le pipeline
        pipeline.bm25.bm25 = bm25
        pipeline.bm25.docs = docs
        pipeline.bm25.meta = meta

        logger.info(f"BM25 index built successfully: {len(docs)} documents")

        return {
            "status": "ok",
            "docs_count": len(docs),
            "index_size_kb": index_path.stat().st_size / 1024,
            "message": f"✅ Index créé avec succès !\n{len(docs)} documents indexés",
        }

    except Exception as e:
        logger.error(f"Failed to build BM25 index: {e}")
        return {
            "status": "error",
            "message": f"Erreur inattendue lors de la création de l'index:\n{str(e)}",
        }


@app.delete("/admin/delete-bm25")
def delete_bm25_index():
    """Supprime l'index BM25."""
    import os
    from pathlib import Path

    try:
        index_path = Path(BM25_INDEX_PATH)

        if index_path.exists():
            os.remove(index_path)

            # Vider le pipeline
            pipeline.bm25.bm25 = None
            pipeline.bm25.docs = []
            pipeline.bm25.meta = []

            logger.info("BM25 index deleted")
            return {"status": "ok", "message": "Index deleted"}
        else:
            return {"status": "ok", "message": "Index does not exist"}

    except Exception as e:
        logger.error(f"Failed to delete BM25 index: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/admin/auto-rebuild-bm25")
def auto_rebuild_bm25():
    """
    Reconstruction automatique intelligente de l'index BM25.
    Vérifie si Qdrant a plus de documents que BM25, et reconstruit si nécessaire.
    Appelé automatiquement par Mail2RAG après chaque ingestion.
    """
    try:
        logger.info("Auto-rebuild BM25: checking if rebuild needed...")

        # Vérifier que Qdrant est accessible
        if not pipeline.vdb.is_ready():
            logger.warning("Auto-rebuild BM25: Vector DB not ready")
            return {
                "status": "skipped",
                "reason": "Vector DB not ready",
                "rebuilt": False,
            }

        # Compter les documents dans la DB via l'interface abstraite
        try:
            db_count = pipeline.vdb.count_documents()
        except Exception as e:
            logger.warning(f"Auto-rebuild BM25: Failed to count docs: {e}")
            return {
                "status": "error",
                "reason": f"Failed to count docs: {str(e)}",
                "rebuilt": False,
            }

        # Compter les documents dans BM25
        bm25_count = len(pipeline.bm25.docs) if pipeline.bm25.is_ready() else 0

        logger.info(f"Auto-rebuild BM25: DB={db_count}, BM25={bm25_count}")

        # Décider si reconstruction nécessaire
        if db_count == 0:
            logger.info("Auto-rebuild BM25: No documents in DB, skipping")
            return {
                "status": "skipped",
                "reason": "No documents in DB",
                "db_count": 0,
                "bm25_count": bm25_count,
                "rebuilt": False,
            }

        if db_count == bm25_count and pipeline.bm25.is_ready():
            logger.info("Auto-rebuild BM25: Index already up-to-date")
            return {
                "status": "ok",
                "reason": "Index already up-to-date",
                "db_count": db_count,
                "bm25_count": bm25_count,
                "rebuilt": False,
            }

        # Reconstruction nécessaire
        logger.info(
            f"Auto-rebuild BM25: Rebuilding (DB={db_count} > BM25={bm25_count})"
        )
        result = build_bm25_index()

        if result.get("status") == "ok":
            logger.info(
                f"Auto-rebuild BM25: Successfully rebuilt with {result.get('docs_count')} documents"
            )
            return {
                "status": "ok",
                "reason": "Index rebuilt",
                "db_count": db_count,
                "bm25_count": result.get("docs_count"),
                "rebuilt": True,
                "index_size_kb": result.get("index_size_kb"),
            }
        else:
            logger.error(f"Auto-rebuild BM25: Failed - {result.get('message')}")
            return {
                "status": "error",
                "reason": result.get("message"),
                "rebuilt": False,
            }

    except Exception as e:
        logger.error(f"Auto-rebuild BM25: Unexpected error - {e}")
        return {
            "status": "error",
            "reason": str(e),
            "rebuilt": False,
        }


def generate_test_html(results: dict) -> str:
    """Génère le HTML pour la page de test."""

    # Préparer les données pour le template
    timestamp = results["timestamp"]
    overall = results["overall"]
    tests = results["tests"]

    # Construire le HTML statique (pas de f-string avec JavaScript)
    html = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAG Proxy - Test Status</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 800px;
            width: 100%;
            padding: 40px;
        }
        h1 {
            color: #2d3748;
            margin-bottom: 10px;
            font-size: 2.5em;
        }
        .timestamp {
            color: #718096;
            font-size: 0.9em;
            margin-bottom: 30px;
        }
        .overall-status {
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 30px;
            text-align: center;
            font-size: 1.2em;
            font-weight: bold;
        }
        .overall-ok {
            background: #c6f6d5;
            color: #22543d;
            border: 2px solid #48bb78;
        }
        .overall-error {
            background: #fed7d7;
            color: #742a2a;
            border: 2px solid #fc8181;
        }
        .test-card {
            background: #f7fafc;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            border-left: 4px solid #cbd5e0;
            transition: transform 0.2s;
        }
        .test-card:hover {
            transform: translateX(5px);
        }
        .test-card.ok {
            border-left-color: #48bb78;
            background: #f0fff4;
        }
        .test-card.error {
            border-left-color: #f56565;
            background: #fff5f5;
        }
        .test-card.not-configured {
            border-left-color: #ed8936;
            background: #fffaf0;
        }
        .test-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .test-name {
            font-size: 1.3em;
            font-weight: 600;
            color: #2d3748;
        }
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
            text-transform: uppercase;
        }
        .status-ok {
            background: #48bb78;
            color: white;
        }
        .status-error {
            background: #f56565;
            color: white;
        }
        .status-not-configured {
            background: #ed8936;
            color: white;
        }
        .test-details {
            color: #4a5568;
            margin-top: 8px;
            font-size: 0.95em;
        }
        .error-message {
            background: #fff5f5;
            border: 1px solid #fc8181;
            padding: 10px;
            border-radius: 6px;
            margin-top: 10px;
            color: #742a2a;
            font-family: monospace;
            font-size: 0.9em;
        }
        .icon {
            font-size: 1.5em;
            margin-right: 10px;
        }
        .btn {
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9em;
            transition: background 0.3s;
            margin-right: 10px;
        }
        .btn-success {
            background: #48bb78;
        }
        .btn-success:hover {
            background: #38a169;
        }
        .btn-danger {
            background: #f56565;
        }
        .btn-danger:hover {
            background: #e53e3e;
        }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 1em;
            cursor: pointer;
            margin-top: 20px;
            transition: background 0.3s;
        }
        .refresh-btn:hover {
            background: #5a67d8;
        }
        .bm25-actions {
            margin-top: 15px;
            display: flex;
            gap: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 RAG Proxy Test</h1>
        <div class="timestamp">⏰ """ + timestamp + """</div>
        
        <div class="overall-status overall-""" + overall + """">
            """ + (
        "✅ Tous les systèmes opérationnels"
        if overall == "ok"
        else "❌ Certains systèmes ont des erreurs"
    ) + """
        </div>
        
        <!-- Test Embeddings -->
        <div class="test-card """ + tests["embeddings"]["status"] + """">
            <div class="test-header">
                <div class="test-name">
                    <span class="icon">🧠</span>Embeddings (LM Studio)
                </div>
                <span class="status-badge status-""" + tests["embeddings"][
        "status"
    ] + """">
                    """ + tests["embeddings"]["status"] + """
                </span>
            </div>
            <div class="test-details">
                """ + (
        f"Dimension: {tests['embeddings']['dimension']}"
        if tests["embeddings"]["status"] == "ok"
        else ""
    ) + """
            </div>
            """ + (
        f'<div class="error-message">{tests["embeddings"]["error"]}</div>'
        if tests["embeddings"]["error"]
        else ""
    ) + """
        </div>
        
        <!-- Test Qdrant -->
        <div class="test-card """ + tests["qdrant"]["status"] + """">
            <div class="test-header">
                <div class="test-name">
                    <span class="icon">🗄️</span>Qdrant Vector DB
                </div>
                <span class="status-badge status-""" + tests["qdrant"][
        "status"
    ] + """">
                    """ + tests["qdrant"]["status"] + """
                </span>
            </div>
            """ + (
        f'<div class="error-message">{tests["qdrant"]["error"]}</div>'
        if tests["qdrant"].get("error")
        else ""
    ) + """
        </div>
        
        <!-- Test BM25 -->
        <div class="test-card """ + tests["bm25"]["status"] + """">
            <div class="test-header">
                <div class="test-name">
                    <span class="icon">📊</span>BM25 Index
                </div>
                <span class="status-badge status-""" + tests["bm25"][
        "status"
    ].replace(
        "_", "-"
    ) + """">
                    """ + tests["bm25"]["status"] + """
                </span>
            </div>
            <div class="test-details">
                """ + (
        f"Documents indexés: {tests['bm25']['docs_count']}"
        if tests["bm25"]["status"] != "error"
        else ""
    ) + """
                """ + (
        " (optionnel)"
        if tests["bm25"]["status"] == "not_configured"
        else ""
    ) + """
            </div>
            """ + (
        f'<div class="error-message">{tests["bm25"]["error"]}</div>'
        if tests["bm25"].get("error")
        else ""
    ) + """
            
            <div class="bm25-actions">
                <button onclick="buildBM25()" class="btn btn-success">
                    🔨 Construire Index
                </button>
                <button onclick="deleteBM25()" class="btn btn-danger" """ + (
        "disabled" if tests["bm25"]["status"] != "ok" else ""
    ) + """>
                    🗑️ Supprimer Index
                </button>
            </div>
        </div>
        
        <!-- Test Reranker -->
        <div class="test-card """ + tests["reranker"]["status"] + """">
            <div class="test-header">
                <div class="test-name">
                    <span class="icon">🎯</span>Reranker (LM Studio)
                </div>
                <span class="status-badge status-""" + tests["reranker"][
        "status"
    ] + """">
                    """ + tests["reranker"]["status"] + """
                </span>
            </div>
            <div class="test-details">
                """ + (
        f"Test réussi avec {tests['reranker']['ranked_count']} documents mockés"
        if tests["reranker"]["status"] == "ok"
        else ""
    ) + """
            </div>
            """ + (
        f'<div class="error-message">{tests["reranker"]["error"]}</div>'
        if tests["reranker"].get("error")
        else ""
    ) + """
        </div>
        
        <button class="refresh-btn" onclick="location.reload()">🔄 Rafraîchir</button>
    </div>
    
    <script>
        async function buildBM25() {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Construction...';
            
            try {
                const response = await fetch('/admin/build-bm25', { method: 'POST' });
                const data = await response.json();
                
                if (data.status === 'ok') {
                    alert('✅ Index BM25 créé !\\n' + data.docs_count + ' documents indexés\\nTaille: ' + data.index_size_kb.toFixed(2) + ' KB');
                    location.reload();
                } else {
                    alert('❌ Erreur: ' + data.message);
                }
            } catch (e) {
                alert('❌ Erreur: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.textContent = '🔨 Construire Index';
            }
        }
        
        async function deleteBM25() {
            if (!confirm('Êtes-vous sûr de vouloir supprimer l\\'index BM25 ?')) return;
            
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Suppression...';
            
            try {
                const response = await fetch('/admin/delete-bm25', { method: 'DELETE' });
                const data = await response.json();
                
                if (data.status === 'ok') {
                    alert('✅ Index BM25 supprimé');
                    location.reload();
                } else {
                    alert('❌ Erreur: ' + data.message);
                }
            } catch (e) {
                alert('❌ Erreur: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.textContent = '🗑️ Supprimer Index';
            }
        }
    </script>
</body>
</html>"""

    return html
