#!/usr/bin/env python3
"""
Mail2RAG - Test All Features
A diagnostic script to validate all components of the Mail2RAG system.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from urllib.parse import urljoin
from pprint import pprint

# Configurations
RAG_PROXY_URL = "http://localhost:9100"
LM_STUDIO_URL = "http://localhost:1234/v1"
TIKA_URL = "http://localhost:9120"
QDRANT_URL = "http://localhost:9110"

def print_header(title):
    print(f"\n{'='*50}")
    print(f"🔍 {title}")
    print(f"{'='*50}")

def print_result(name, success, details=""):
    icon = "✅" if success else "❌"
    color = "\033[92m" if success else "\033[91m"
    reset = "\033[0m"
    print(f"{icon} {color}{name}{reset}: {details}")

def check_http_json(url, name):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return True, data
            return False, f"Status Code: {response.status}"
    except urllib.error.URLError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def test_tika():
    print_header("Tika Document Extraction Service")
    url = f"{TIKA_URL}/tika"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                print_result("Tika HTTP Check", True, "Tika is responding")
            else:
                print_result("Tika HTTP Check", False, f"HTTP {response.status}")
    except Exception as e:
        print_result("Tika HTTP Check", False, str(e))

def test_qdrant():
    print_header("Qdrant Vector Database")
    success, data = check_http_json(f"{QDRANT_URL}/collections", "Qdrant Collections")
    if success:
        collections = data.get("result", {}).get("collections", [])
        names = [c["name"] for c in collections]
        print_result("Qdrant API", True, f"Found collections: {names if names else 'None'}")
    else:
        print_result("Qdrant API", False, str(data))

def test_lm_studio():
    print_header("LM Studio Models API")
    success, data = check_http_json(f"{LM_STUDIO_URL}/models", "LM Studio Models")
    if success:
        models = data.get("data", [])
        model_names = [m["id"] for m in models]
        print_result("LM Studio API", True, f"Loaded models: {model_names}")
        
        # Check against .env
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_file):
            expected_chat = None
            expected_embed = None
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("AI_MODEL_NAME="):
                        expected_chat = line.strip().split("=")[1]
                    elif line.startswith("EMBED_MODEL="):
                        expected_embed = line.strip().split("=")[1]
            
            if expected_chat and expected_chat in model_names:
                print_result("Chat Model Validation", True, f"Found {expected_chat}")
            else:
                print_result("Chat Model Validation", False, f"Expected {expected_chat} but not loaded")
                
            if expected_embed and expected_embed in model_names:
                print_result("Embed Model Validation", True, f"Found {expected_embed}")
            else:
                print_result("Embed Model Validation", False, f"Expected {expected_embed} but not loaded")
    else:
        print_result("LM Studio API", False, str(data))

def test_rag_proxy():
    print_header("RAG Proxy Integrations")
    success, data = check_http_json(f"{RAG_PROXY_URL}/readyz", "RAG Proxy Readiness")
    if success:
        ready = data.get("ready", False)
        deps = data.get("deps", {})
        print_result("RAG Proxy Readiness", ready, "All components connected" if ready else f"Dependencies: {deps}")
        if "models" in data:
            print(f"    Loaded proxy models: {data['models']}")
    else:
        print_result("RAG Proxy API", False, str(data))

def test_rag_chat():
    print_header("RAG Chat Test Generation")
    url = f"{RAG_PROXY_URL}/chat"
    payload = json.dumps({
        "query": "Bonjour, ceci est un test de fonctionnement.",
        "use_bm25": False,
        "max_tokens": 50
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                print_result("Chat Generation", True, "Received response from LLM")
                print(f"    > LLM Reply: {reply.strip()}")
            else:
                print_result("Chat Generation", False, f"Status: {response.status}")
    except Exception as e:
        print_result("Chat Generation", False, str(e))

if __name__ == "__main__":
    print("\n🚀 Starting Mail2RAG Full Feature Validation\n")
    test_tika()
    test_qdrant()
    test_lm_studio()
    test_rag_proxy()
    test_rag_chat()
    print("\n🏁 Validation Complete\n")
