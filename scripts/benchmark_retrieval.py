#!/usr/bin/env python3
"""
Benchmark Retrieval Script for Mail2RAG (Phase 2)
Evaluates Recall@K and Reranking impact directly against the RAG Proxy.
"""

import sys
import os
import requests
import json
import time
import argparse
import math

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
mail2rag_dir = os.path.join(parent_dir, "mail2rag")
sys.path.insert(0, mail2rag_dir if os.path.exists(mail2rag_dir) else parent_dir)

from tests_framework.data.test_cases import TEST_EMAILS

RAG_PROXY_URL = os.getenv("RAG_PROXY_URL", "http://rag_proxy:8000")

# Mapping of query IDs to expected Target Document UIDs (as defined by ingestion order)
TARGET_MAPPING = {
    "SUPPORT_URBA": 1001,      # INGEST_URBA_CIBLE
    "SUPPORT_VOIRIE": 1007,    # INGEST_VOIRIE_CIBLE_2
    "SUPPORT_EC_1": 1011,      # INGEST_EC_CIBLE_1
    "SUPPORT_EC_2": 1011,      # INGEST_EC_CIBLE_1 (same doc)
    "SUPPORT_ENF_1": 1016,     # INGEST_SOCIAL_CIBLE_1
    "SUPPORT_ENF_2": 1016,     # INGEST_SOCIAL_CIBLE_1
    "SUPPORT_VOIRIE2": 1006,   # INGEST_VOIRIE_CIBLE_1
    "SUPPORT_ASSO": 1018,      # INGEST_SOCIAL_CIBLE_3
    "SUPPORT_SOCIAL_1": 1017,  # INGEST_SOCIAL_CIBLE_2
    "SUPPORT_SOCIAL_2": 1017,  # INGEST_SOCIAL_CIBLE_2
    "SUPPORT_SECU": 1021,      # INGEST_SECU_CIBLE_1
    "SUPPORT_ELEC": 1012,      # INGEST_EC_CIBLE_2
    "SUPPORT_CONVERSATION": 1001, # INGEST_URBA_CIBLE
    # --- AMBIGUOUS ---
    "AMBIGUOUS_1": 1001,
    "AMBIGUOUS_2": 1011,
    "AMBIGUOUS_3": 1006,
    "AMBIGUOUS_4": 1016,
    "AMBIGUOUS_5": 1017,
    # --- TYPO ---
    "TYPO_1": 1011,
    "TYPO_2": 1021,
    "TYPO_3": 1016,
    "TYPO_4": 1001,
    "TYPO_5": 1006,
    # --- ENGLISH ---
    "EN_1": 1001,
    "EN_2": 1011,
    "EN_3": 1021,
    "EN_4": 1016,
    "EN_5": 1006,
    # --- CONVERSATIONAL ---
    "CONV_1": 1016,
    "CONV_2": 1011,
    "CONV_3": 1007,
    "CONV_4": 1018,
    "CONV_5": 1021
}

# Map OOD to None meaning we expect abstention
for i in range(1, 6):
    TARGET_MAPPING[f"OOD_{i}"] = None

def run_benchmark():
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=str, help="Export results to JSON file")
    parser.add_argument("--real-data", action="store_true", help="Use real staging data")
    args = parser.parse_args()

    print("="*80)
    print("🎯 BENCHMARK RETRIEVAL (GOLDEN DATASET)")
    print("="*80)

    # We need to compute Recall@K before and after reranking
    metrics = {
        "queries_tested": 0,
        "pre_reranking_hits": 0,
        "post_reranking_hits": 0,
        "mrr_post": 0.0,
        "ndcg_post": 0.0,
        "precision_k": 0.0,
        "parent_child_expansions": 0,
        "abstentions": 0,
        "ood_queries": 0,
        "total_child_tokens": 0,
        "total_parent_tokens": 0
    }

    # First, run ingestion
    print("\n[1/3] Simulation de l'ingestion via RAG Proxy...")
    uid_counter = 1000
    ingested_workspaces = {}
    
    for email in TEST_EMAILS:
        uid_counter += 1
        if email["type"] == "Ingestion":
            # Determine workspace roughly
            workspace = "default-workspace"
            if "urba" in email["sender"]: workspace = "urba"
            elif "voirie" in email["sender"]: workspace = "voirie"
            elif "etat-civil" in email["sender"]: workspace = "etat-civil"
            elif "social" in email["sender"]: workspace = "social"
            elif "police" in email["sender"]: workspace = "police"
            
            doc_payload = {
                "collection": workspace,
                "text": f"Subject: {email['subject']}\n\n{email['body']}",
                "metadata": {
                    "uid": str(uid_counter),
                    "source": email["sender"],
                    "subject": email["subject"]
                }
            }
            try:
                res = requests.post(f"{RAG_PROXY_URL}/admin/ingest", json=doc_payload)
                if res.status_code == 200:
                    ingested_workspaces[str(uid_counter)] = workspace
            except Exception as e:
                print(f"Erreur ingestion {uid_counter}: {e}")

    print("Attente de l'indexation Qdrant (3s)...")
    time.sleep(3)

    print("\n[2/3] Exécution des requêtes de RAG...")
    
    for email in TEST_EMAILS:
        if email["type"] == "Support (RAG)" and email["id"] in TARGET_MAPPING:
            query = email["body"]
            target_uid = str(TARGET_MAPPING[email["id"]]) if TARGET_MAPPING[email["id"]] else None
            
            # Determine workspace mapping for search
            workspace = "default-workspace"
            if "urba" in email["sender"]: workspace = "urba"
            elif "voirie" in email["sender"] or "proprete" in email["sender"]: workspace = "voirie"
            elif "etatcivil" in email["sender"]: workspace = "etat-civil"
            elif "social" in email["sender"] or "asso" in email["sender"] or "parent" in email["sender"] or "ccas" in email["sender"]: workspace = "social"
            elif "fatigue" in email["sender"]: workspace = "police"
            elif "electeur" in email["sender"]: workspace = "etat-civil"
            
            payload = {
                "query": query,
                "top_k": 10,
                "final_k": 3,
                "use_bm25": True,
                "workspace": workspace
            }
            
            try:
                res = requests.post(f"{RAG_PROXY_URL}/rag", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    debug = data.get("debug_info", {})
                    inter = debug.get("intermediate_results", {})
                    
                    pre_uids = inter.get("pre_reranking_uids", [])
                    post_uids = inter.get("post_reranking_uids", [])
                    
                    if target_uid is None:
                        metrics["ood_queries"] += 1
                        if not post_uids or data.get("answer", "").startswith("Je ne"):
                            metrics["abstentions"] += 1
                        hit_pre = hit_post = False
                    else:
                        hit_pre = target_uid in pre_uids
                        hit_post = target_uid in post_uids
                    
                    metrics["queries_tested"] += 1
                    if hit_pre:
                        metrics["pre_reranking_hits"] += 1
                    if hit_post:
                        metrics["post_reranking_hits"] += 1
                        # Calculate MRR
                        rank = post_uids.index(target_uid) + 1
                        metrics["mrr_post"] += 1.0 / rank
                        # Precision@3 and NDCG@3 (simplistic: rel=1 if target else 0)
                        metrics["precision_k"] += 1.0 / len(post_uids) if len(post_uids) > 0 else 0.0
                        metrics["ndcg_post"] += 1.0 / math.log2(rank + 1)
                        
                    # Ratio Parent-Child Bruit/Signal
                    for chunk in data.get("chunks", []):
                        meta = chunk.get("metadata", {})
                        extended = meta.get("extended_text", "")
                        original = chunk.get("text", "")
                        if extended:
                            metrics["parent_child_expansions"] += 1
                            # Rough token estimation by words
                            child_len = len(original.split())
                            parent_len = len(extended.split())
                            metrics["total_child_tokens"] += child_len
                            metrics["total_parent_tokens"] += parent_len
                    
                    status_pre = "✅" if hit_pre else "❌"
                    status_post = "✅" if hit_post else "❌"
                    print(f"[{email['id']}] Target: {target_uid} | Pre-Rerank: {status_pre} | Post-Rerank: {status_post}")
                else:
                    print(f"Erreur `/rag` pour {email['id']}: HTTP {res.status_code}")
            except Exception as e:
                print(f"Exception pour {email['id']}: {e}")

    print("\n[3/4] Test de Génération et Citations (Appel LLM)...")
    citation_passed = False
    citation_reason = "Non testé"
    
    # On va prendre une requête simple pour vérifier les citations
    query = "Quelles sont les règles d'urbanisme pour construire un abri de jardin ?"
    print(f"Envoi au LLM : '{query}'...")
    chat_payload = {
        "query": query + " Merci de citer le document source à la fin avec la syntaxe [Document X].",
        "top_k": 5,
        "final_k": 3,
        "collection": "urba",
        "temperature": 0.1
    }
    try:
        print(f"Envoi au LLM : '{query}'...")
        res = requests.post(f"{RAG_PROXY_URL}/chat", json=chat_payload)
        if res.status_code == 200:
            data = res.json()
            answer = data.get("answer", "")
            if "[Document" in answer:
                citation_passed = True
                citation_reason = "Balises [Document X] détectées !"
                print(f"✅ Citations détectées ! Extrait : {answer[-100:]}")
            else:
                citation_passed = False
                citation_reason = "Aucune balise [Document X] trouvée dans la réponse."
                print(f"❌ Échec citations : {answer[:100]}...")
        else:
            citation_passed = False
            citation_reason = f"Erreur API LLM HTTP {res.status_code}"
            print(f"❌ API LLM Indisponible ({res.status_code})")
    except Exception as e:
        citation_passed = False
        citation_reason = f"Exception : {e}"
        print(f"⚠️ Impossible de tester le LLM : {e}")

    print("\n[4/4] Nettoyage des documents de test...")
    for uid, ws in ingested_workspaces.items():
        requests.delete(f"{RAG_PROXY_URL}/admin/document/{uid}?collection={ws}")

    print("\n" + "="*80)
    print("📊 RESULTATS DU BENCHMARK")
    print("="*80)
    total = metrics["queries_tested"]
    if total > 0:
        recall_pre = (metrics["pre_reranking_hits"] / total) * 100
        recall_post = (metrics["post_reranking_hits"] / total) * 100
        mrr = metrics["mrr_post"] / total
        ndcg = metrics["ndcg_post"] / total
        prec = metrics["precision_k"] / total
        abstention_rate = (metrics["abstentions"] / metrics["ood_queries"]) * 100 if metrics["ood_queries"] > 0 else 0
        
        print(f"Nombre de requêtes    : {total}")
        print(f"Recall@10 (Initial)   : {recall_pre:.1f}%")
        print(f"Recall@3 (Reranké)    : {recall_post:.1f}%")
        print(f"MRR (Post-Reranking)  : {mrr:.3f}")
        print(f"NDCG@3                : {ndcg:.3f}")
        print(f"Precision@3           : {prec:.3f}")
        print(f"Taux d'abstention     : {abstention_rate:.1f}%")
        
        print("\n" + "-"*80)
        if metrics["parent_child_expansions"] > 0:
            ratio = metrics["total_parent_tokens"] / max(1, metrics["total_child_tokens"])
            print(f"Expansions Parent-Child : {metrics['parent_child_expansions']} chunks")
            print(f"Ratio d'expansion (Bruit) : x{ratio:.1f} (Taille enfant estimée x{ratio:.1f})")
        else:
            print("Expansions Parent-Child : Aucune détectée sur ce dataset (Normal si pas de PJ).")
            
        print(f"Test Citations LLM        : {'✅ PASS' if citation_passed else '❌ FAIL'} ({citation_reason})")

        if args.export:
            res_dict = {
                "total_queries": total,
                "recall_10": recall_pre,
                "recall_3": recall_post,
                "mrr": mrr,
                "ndcg_3": ndcg,
                "precision_3": prec,
                "abstention_rate": abstention_rate
            }
            try:
                os.makedirs(os.path.dirname(args.export), exist_ok=True)
            except Exception:
                pass
            with open(args.export, "w") as f:
                json.dump(res_dict, f, indent=4)
            print(f"\nRésultats exportés vers {args.export}")
    else:
        print("Aucune requête traitée.")

if __name__ == "__main__":
    run_benchmark()
