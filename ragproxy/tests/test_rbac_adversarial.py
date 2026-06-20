"""
Tests adversariaux pour valider le contrôle d'accès basé sur les rôles (RBAC).
"""

import pytest

def test_rbac_sql_injection_bypass(client):
    """
    Test qu'une tentative d'injection de type SQL ou NoSQL dans acl_groups
    ne permet pas de contourner les droits d'accès normaux.
    """
    # 1. On insère un document accessible uniquement au groupe "admin_secret_group"
    doc_payload = {
        "text": "SECRET ADMIN DATA",
        "metadata": {
            "acl": ["admin_secret_group"],
            "doc_type": "confidential"
        }
    }
    client.post("/admin/ingest", json=doc_payload)
    
    # 2. On tente une recherche avec un acl_groups manipulé
    payload = {
        "query": "SECRET ADMIN DATA",
        "acl_groups": ["user", "' OR '1'='1", "admin_secret_group'--"],
        "top_k": 5
    }
    response = client.post("/rag", json=payload)
    
    # 3. La recherche doit réussir (200) mais ne doit renvoyer aucun document
    # car les groupes fournis ne correspondent pas littéralement à "admin_secret_group"
    assert response.status_code == 200
    data = response.json()
    chunks = data.get("chunks", [])
    
    # On vérifie qu'aucun chunk retourné n'a le texte secret (s'il y en a)
    for chunk in chunks:
        assert "SECRET ADMIN DATA" not in chunk.get("text", "")


def test_rbac_wildcard_bypass(client):
    """
    Test qu'un wildcard (*) n'est pas autorisé comme groupe ACL.
    """
    payload = {
        "query": "SECRET ADMIN DATA",
        "acl_groups": ["*"],
        "top_k": 5
    }
    response = client.post("/rag", json=payload)
    
    assert response.status_code == 200
    chunks = response.json().get("chunks", [])
    for chunk in chunks:
        assert "SECRET ADMIN DATA" not in chunk.get("text", "")
