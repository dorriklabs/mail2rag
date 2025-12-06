"""
Health check endpoints.
"""

import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.models import HealthResponse
from app.pipeline import RAGPipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

# Pipeline instance (will be set by main.py)
pipeline: RAGPipeline = None


def set_pipeline(p: RAGPipeline):
    """Set the pipeline instance for this router."""
    global pipeline
    pipeline = p


@router.get("/healthz", response_model=HealthResponse)
def healthz():
    """Simple liveness probe."""
    return HealthResponse(status="ok")


@router.get("/health", response_model=HealthResponse)
def health():
    """Alias for healthz."""
    return HealthResponse(status="ok")


@router.get("/readyz")
def readyz():
    """Readiness probe with dependency status."""
    status = pipeline.ready_status()
    deps = status.get("deps", {})
    ready = all(deps.values())
    
    response = {
        "ready": ready,
        "deps": deps
    }
    
    if "bm25_collections" in status:
        response["bm25_collections"] = status["bm25_collections"]
    
    return response


@router.get("/test")
def test_endpoint():
    """
    Diagnostic endpoint testing all pipeline components.
    Returns HTML with results.
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

    # Overall status
    results["overall"] = (
        "ok"
        if all(
            t.get("status") in ["ok", "not_configured"]
            for t in results["tests"].values()
        )
        else "error"
    )

    html_content = _generate_test_html(results)
    return HTMLResponse(content=html_content)


def _generate_test_html(results: Dict[str, Any]) -> str:
    """Generate HTML for test results."""
    overall = results.get("overall", "unknown")
    overall_color = "#10b981" if overall == "ok" else "#ef4444"
    
    tests_html = ""
    for name, data in results.get("tests", {}).items():
        status = data.get("status", "unknown")
        color = "#10b981" if status == "ok" else "#f59e0b" if status == "not_configured" else "#ef4444"
        icon = "✓" if status == "ok" else "⚠" if status == "not_configured" else "✗"
        
        details = []
        for key, val in data.items():
            if key not in ["status", "error"] and val is not None:
                details.append(f"<span>{key}: {val}</span>")
        
        error_html = f'<div style="color:#ef4444;margin-top:5px">{data.get("error")}</div>' if data.get("error") else ""
        
        tests_html += f'''
        <div style="background:#1f2937;border-radius:8px;padding:15px;margin:10px 0">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-weight:bold;text-transform:capitalize">{name}</span>
                <span style="color:{color}">{icon} {status}</span>
            </div>
            <div style="color:#9ca3af;font-size:0.875rem;margin-top:5px">
                {" | ".join(details)}
            </div>
            {error_html}
        </div>
        '''
    
    return f'''<!DOCTYPE html>
<html>
<head>
    <title>RAG Proxy - Diagnostics</title>
    <style>
        body {{ font-family: system-ui; background: #111827; color: #f9fafb; padding: 20px; margin: 0; }}
        .container {{ max-width: 600px; margin: 0 auto; }}
        h1 {{ color: #60a5fa; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 RAG Proxy Diagnostics</h1>
        <p style="color:#9ca3af">{results.get("timestamp", "")}</p>
        <div style="background:{overall_color};color:white;padding:10px 20px;border-radius:8px;text-align:center;font-size:1.25rem;margin:20px 0">
            Overall: {overall.upper()}
        </div>
        {tests_html}
    </div>
</body>
</html>'''
