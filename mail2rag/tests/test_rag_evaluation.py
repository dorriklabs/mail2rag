import pytest
import os
from typing import Dict, Any

from config import Config
from services.ragproxy_client import RAGProxyClient
from services.llm_client import get_llm_client

# Définition des cas de test (Questions de plus en plus difficiles)
TEST_CASES = [
    {
        "name": "Niveau 1 - Fait explicite",
        "question": "Quelle est la hauteur maximale autorisée pour une clôture en zone UB ?",
        "criteria": "La réponse doit mentionner une limite de hauteur pour les clôtures, ou indiquer clairement que ce n'est pas réglementé dans le document."
    },
    {
        "name": "Niveau 2 - Comparaison / Synthèse",
        "question": "Quelles sont les différences majeures concernant le stationnement entre les zones UA et UB ?",
        "criteria": "La réponse doit comparer explicitement les règles de stationnement entre les zones UA et UB."
    },
    {
        "name": "Niveau 3 - Cas spécifique / Implantation",
        "question": "Peut-on implanter une piscine en limite séparative dans la zone agricole (A) ?",
        "criteria": "La réponse doit aborder l'implantation des piscines et les distances ou interdictions par rapport aux limites séparatives."
    },
    {
        "name": "Niveau 4 - Implantation en Zone UA (Modifié)",
        "question": "Dans la zone UA, pour un pignon sur rue, est-ce que les décrochés de façade sont autorisés sur la limite d'emprise de la voie ?",
        "criteria": "La réponse doit affirmer que les décrochés de façade sont interdits sur la limite d'emprise de la voie."
    },
    {
        "name": "Niveau 5 - Annexe en Zone UL",
        "question": "Je veux construire un petit cabanon (annexe) de 3 mètres de haut dans mon jardin en Zone UL. Quelles sont les règles d'alignement ou d'implantation pour ce cabanon précis ?",
        "criteria": "La réponse doit préciser de manière explicite que pour les annexes dont la hauteur est inférieure ou égale à 4 mètres en Zone UL, ce n'est pas réglementé."
    },
    {
        "name": "Niveau 6 - Renvoi d'information (Multi-documents)",
        "question": "Quelles sont les règles précises d'aspect extérieur pour les clôtures en zone UA ?",
        "criteria": "La réponse doit indiquer qu'il faut se reporter aux dispositions communes à toutes les zones (partie 1.6 ou équivalent) pour l'aspect extérieur."
    },
    {
        "name": "Niveau 7 - Cas complexe RDC Commercial",
        "question": "Je souhaite transformer un commerce en logement au rez-de-chaussée dans le secteur UA. Est-ce autorisé et y a-t-il des prescriptions sur la façade ou les vitrines ?",
        "criteria": "La réponse doit rechercher les dispositions concernant les changements de destination en rez-de-chaussée dans la zone UA (ou indiquer si le règlement l'interdit pour préserver la vocation commerciale)."
    }
]


@pytest.fixture(scope="module")
def config():
    """Initialise la configuration pour les tests"""
    return Config()


@pytest.fixture(scope="module")
def rag_client(config):
    """Initialise le client RAG Proxy"""
    # En environnement Docker, le proxy est accessible via son nom de service (ex: ragproxy)
    url = os.getenv("RAG_PROXY_URL", "http://ragproxy:8000")
    return RAGProxyClient(base_url=url, timeout=120)


@pytest.fixture(scope="module")
def llm_judge(config):
    """Initialise le client LLM qui va agir en tant que juge"""
    return get_llm_client(config)


@pytest.fixture(scope="module", autouse=True)
def setup_and_ingest_plui(config, rag_client):
    """
    Fixture qui gère l'ingestion de bout en bout du fichier PLUI avant les tests.
    S'assure que la collection de test est prête et nettoyée à la fin.
    """
    from pathlib import Path
    from services.processor import DocumentProcessor

    # Le fichier est à la racine du projet (mappé dans /app dans Docker)
    pdf_path = Path("5.1 - Règlement écrit.pdf")
    if not pdf_path.exists():
        pdf_path = Path("/app/5.1 - Règlement écrit.pdf")
    
    if not pdf_path.exists():
        pytest.skip(f"Fichier {pdf_path.name} introuvable à la racine pour le test intégré.")

    collection_name = "test-plui-evaluation"
    
    import os
    import pickle
    
    # Paramètres d'ingestion depuis les variables d'environnement
    chunk_size = int(os.getenv("CHUNK_SIZE", "1500"))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "400"))
    chunking_strategy = os.getenv("CHUNKING_STRATEGY", "recursive")
    
    cache_path = Path("/app/cache_doc.pkl") if Path("/app").exists() else Path("cache_doc.pkl")
    
    if cache_path.exists():
        print(f"\n[SETUP] Chargement rapide du PDF depuis le cache {cache_path}...")
        with open(cache_path, "rb") as f:
            doc = pickle.load(f)
    else:
        print(f"\n[SETUP] Extraction du PDF {pdf_path.name} (long)...")
        config.structured_ingestion_enabled = True
        processor = DocumentProcessor(config)
        doc = processor._process_pdf(pdf_path, return_structured=True)
        assert doc is not None, "L'extraction du PDF a échoué"
        print(f"[SETUP] Sauvegarde du document dans {cache_path}...")
        with open(cache_path, "wb") as f:
            pickle.dump(doc, f)
    
    print(f"[SETUP] Type de document détecté : {doc.source_type}")
    if doc.global_metadata:
        print(f"[SETUP] Métadonnées PDF extraites : {doc.global_metadata}")
    
    print(f"[SETUP] Nettoyage préalable de la collection '{collection_name}'...")
    rag_client.delete_by_metadata(collection=collection_name, filters={"filename": doc.filename})
    
    print(f"[SETUP] Ingestion des {len(doc.pages)} pages dans la collection '{collection_name}'...")
    print(f"[SETUP] Paramètres : chunk_size={chunk_size}, chunk_overlap={chunk_overlap}, strategy={chunking_strategy}")
    result = rag_client.ingest_structured_document(
        collection=collection_name, 
        document=doc,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        chunking_strategy=chunking_strategy
    )
    assert result.get("status") == "ok", f"Erreur d'ingestion : {result.get('message')}"
    
    print("[SETUP] Reconstruction de l'index BM25...")
    rag_client.rebuild_bm25(collection_name)
    
    # On passe le nom de la collection aux tests
    yield collection_name
    
    # Teardown (Nettoyage après les tests)
    print(f"\n[TEARDOWN] Nettoyage de la collection '{collection_name}'...")
    rag_client.delete_by_metadata(collection=collection_name, filters={"filename": doc.filename})


def evaluate_with_llm(llm, question: str, expected_criteria: str, actual_response: str) -> dict:
    """
    Utilise le LLM pour évaluer la réponse en détail (Note, Critique, Suggestion).
    Retourne un dictionnaire contenant les détails de l'évaluation.
    """
    prompt = f"""Tu es un évaluateur expert (LLM-as-a-judge) spécialisé dans les systèmes RAG (Recherche augmentée) pour des documents d'urbanisme.

Question posée : {question}
Critères attendus : {expected_criteria}
Réponse générée par le système : {actual_response}

Instructions :
1. Évalue la "Réponse générée" par rapport aux "Critères attendus" et à la "Question posée".
2. Ne juge pas la véracité absolue (tu n'as pas le document), mais juge la précision, la clarté, et si la réponse répond effectivement à la question ou si elle indique pertinemment que l'information est absente.
3. Fournis ton évaluation STRICTEMENT selon ce format :

NOTE: [Donne une note sur 10. Ex: 8/10]
CRITIQUE: [Explique brièvement ce qui est bien et ce qui manque ou est erroné dans la réponse générée]
SUGGESTION: [Donne un conseil sur la façon d'améliorer le système (ex: meilleur découpage, contexte plus large, prompt plus précis)]
STATUS: [PASS si la note est >= 7/10, sinon FAIL]

Réponds uniquement avec le format demandé, sans texte supplémentaire."""

    messages = [{"role": "user", "content": prompt}]
    
    try:
        evaluation = llm.chat(messages=messages, temperature=0.0, max_tokens=300)
        evaluation_text = evaluation.strip()
        
        # Parsing de la réponse
        result = {
            "note": "N/A",
            "critique": "N/A",
            "suggestion": "N/A",
            "status": "FAIL",
            "raw": evaluation_text
        }
        
        for line in evaluation_text.split('\n'):
            line = line.strip()
            if line.startswith("NOTE:"):
                result["note"] = line.replace("NOTE:", "").strip()
            elif line.startswith("CRITIQUE:"):
                result["critique"] = line.replace("CRITIQUE:", "").strip()
            elif line.startswith("SUGGESTION:"):
                result["suggestion"] = line.replace("SUGGESTION:", "").strip()
            elif line.startswith("STATUS:"):
                result["status"] = line.replace("STATUS:", "").strip()
                
        status_icon = "✅" if "PASS" in result["status"] else "❌"
        print(f"\n{status_icon} [JUGEMENT IA] {result['status']}")
        print(f"   📊 Note       : {result['note']}")
        print(f"   🧐 Critique   : {result['critique']}")
        print(f"   💡 Suggestion : {result['suggestion']}")
        
        return result
    except Exception as e:
        print(f"\n[JUGEMENT IA ERREUR] Impossible d'évaluer : {e}")
        return {"status": "FAIL", "note": "0/10", "critique": f"Erreur LLM: {e}", "suggestion": "Vérifier la connexion au modèle", "raw": ""}


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[tc["name"] for tc in TEST_CASES])
def test_rag_proxy_responses(rag_client, llm_judge, setup_and_ingest_plui, test_case):
    """
    Test intégré : Interroge le RAG Proxy et fait évaluer la réponse par le LLM (Juge).
    """
    collection_name = setup_and_ingest_plui
    question = test_case["question"]
    criteria = test_case["criteria"]
    
    import os
    
    # Paramètres de recherche
    top_k = int(os.getenv("TOP_K", "15"))
    final_k = int(os.getenv("FINAL_K", "5"))
    use_bm25 = os.getenv("USE_BM25", "true").lower() == "true"
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1000"))
    
    print(f"\n\n{'='*60}")
    print(f"📌 TEST : {test_case['name']}")
    print(f"{'='*60}")
    print(f"❓ Question posée : {question}")
    print(f"🎯 Critère attendu : {criteria}\n")
    print(f"⏳ Interrogation (top_k={top_k}, final_k={final_k}, hybrid={use_bm25}, temp={temperature})...")
    
    # Étape 1 : Interroger le système RAG sur la collection de test spécifiquement
    response = rag_client.chat(
        query=question, 
        collection=collection_name, 
        top_k=top_k, 
        final_k=final_k,
        use_bm25=use_bm25,
        temperature=temperature,
        max_tokens=max_tokens
    )
    
    assert "answer" in response, "Le RAG Proxy n'a pas retourné de champ 'answer'"
    
    actual_answer = response["answer"]
    sources = response.get("sources", [])
    
    print(f"\n🤖 Réponse générée par le système RAG :\n{'-'*60}\n{actual_answer}\n{'-'*60}")
    
    if sources:
        print(f"\n📚 Sources utilisées par le RAG ({len(sources)}) :")
        for i, src in enumerate(sources, 1):
            content = src.get('text', '')
            
            # Extraire les métadonnées utiles pour le debug
            meta = src.get('metadata', {})
            page = meta.get('page_number', '?')
            chunk_idx = meta.get('chunk_index', '?')
            chunk_tot = meta.get('chunk_total', '?')
            score = src.get('score', 0)
            
            # Récupérer les autres métadonnées intéressantes (titre, auteur, etc.)
            ignore_keys = {'text', 'page_number', 'page_hash', 'chunk_index', 'chunk_total', 'chunk_size', 'extended_text', 'char_start', 'char_end', 'collection', 'rerank_score'}
            other_meta = {k: v for k, v in meta.items() if k not in ignore_keys}
            
            print(f"\n  [{i}] --- Page {page} | Chunk {chunk_idx}/{chunk_tot} | Score RAG : {score:.3f} ---")
            if other_meta:
                print(f"      Méta : {other_meta}")
            print(f"      Extrait :\n{content}\n  " + "-"*40)
        
    # Si la réponse est en erreur technique, on fail directement
    if "Erreur HTTP" in actual_answer or "Timeout" in actual_answer:
        pytest.fail(f"Erreur technique du RAG Proxy : {actual_answer}")
        
    # Étape 2 : Évaluer la réponse via le LLM Juge en détail
    evaluation_result = evaluate_with_llm(
        llm=llm_judge,
        question=question,
        expected_criteria=criteria,
        actual_response=actual_answer
    )
    
    passed = "PASS" in evaluation_result["status"]
    assert passed, f"Le juge IA a rejeté la réponse (Note: {evaluation_result['note']}). Critique : {evaluation_result['critique']}"
