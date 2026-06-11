<p align="center">
  <img src="https://img.shields.io/badge/Mail2RAG-Email_to_Knowledge-blueviolet?style=for-the-badge&logo=gmail" alt="Mail2RAG"/>
</p>

<h1 align="center">📧 Mail2RAG</h1>

<p align="center">
  <strong>Transform emails into searchable AI knowledge bases</strong>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-features">Features</a> •
  <a href="#️-architecture">Architecture</a> •
  <a href="#-configuration">Configuration</a> •
  <a href="#-version-française">Français</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Version-3.12.0-blue?style=flat-square" alt="Version"/>
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker"/>
  <img src="https://img.shields.io/badge/FastAPI-RAG_Proxy-009688?logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Qdrant-Vector_DB-FF6B6B" alt="Qdrant"/>
  <img src="https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?logo=streamlit&logoColor=white" alt="Streamlit"/>
  <img src="https://img.shields.io/badge/LiteLLM-Multi_Provider-purple" alt="LiteLLM"/>
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License"/>
</p>

---

## ⚡ TL;DR

Mail2RAG monitors your inbox and **automatically**:
1. 📥 Ingests emails + attachments into a vector database (Qdrant)
2. 🔍 Indexes with hybrid search (Vector + BM25 + Cross-Encoder Reranking)
3. 💬 Answers questions via email or Streamlit dashboard using RAG

**Send an email → Get it indexed → Query via email or dashboard**

> 🆕 **v3.12.0**: **Task Scheduler** for background jobs and **Manual Upload**. Plus LiteLLM Gateway with 7 providers!

---

## 🚀 Quick Start

```bash
# 1. Clone & configure
git clone https://github.com/dorriklabs/mail2rag.git
cd mail2rag && cp .env.example .env

# 2. Edit .env with your IMAP/SMTP credentials and LM Studio URL

# 3. Launch
docker-compose up -d

# 4. Access dashboard
open http://localhost:8501
```

| Service | URL | Description |
|---------|-----|-------------|
| 📊 **Streamlit Admin** | [localhost:8501](http://localhost:8501) | Main dashboard |
| 🔍 **RAG Proxy API** | [localhost:8000/docs](http://localhost:8000/docs) | API documentation |
| 💾 **Qdrant** | [localhost:6333/dashboard](http://localhost:6333/dashboard) | Vector DB |
| 📁 **Archive** | [localhost:8080](http://localhost:8080) | Document archive |

---

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 📥 Email Ingestion
- IMAP monitoring with configurable polling
- Smart routing by sender/subject rules
- Intelligent chunking with overlap
- Multi-format support (PDF, DOCX, images...)

### 📄 Document Analysis
| Engine | Capability |
|--------|------------|
| **Tika** | Text extraction, OCR, metadata |
| **Vision AI** | Image/document description |
| **EXIF** | GPS, camera info, timestamps |
| **Tesseract** | OCR fallback (via Tika) |

</td>
<td width="50%" valign="top">

### 🔍 Hybrid Search
- Vector similarity (Qdrant)
- BM25 keyword matching
- Cross-encoder reranking (local)
- Multi-collection support

### 💬 Chat Mode
Send `Chat: your question` or `Question: your question` by email:
```
Subject: Chat: What are the Q4 highlights?
```
→ Get AI response with source citations

</td>
</tr>
</table>

### 📊 Streamlit Dashboard

| Page | Features |
|------|----------|
| **Overview** | Stats, document counts, collection metrics |
| **Documents** | Browse, search, filter, delete indexed docs |
| **Upload** | Manual document upload and ingestion |
| **Chat** | Test RAG queries directly with sources display |
| **Admin** | Rebuild BM25, delete collections, manage system |

### 🎫 Support Draft Mode (NEW in v3.9.0)

Automatically generate response drafts for support teams:

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Client    │──────►│  Mail2RAG   │──────►│   Support   │
│   Email     │       │  (RAG+AI)   │       │   Inbox     │
└─────────────┘       └─────────────┘       └──────┬──────┘
                                                   │
                                            ▼ Draft in Drafts
                                        ┌─────────────┐
                                        │   Agent     │
                                        │  Reviews &  │
                                        │   Sends     │
                                        └──────┬──────┘
                                               │ BCC
                                               ▼
                                        ┌─────────────┐
                                        │  KB Enriched│
                                        └─────────────┘
```

| Confidence | Template | Action |
|------------|----------|--------|
| **High** (>70%) | 🟢 Green | Ready to send |
| **Medium** (50-70%) | 🔵 Blue | Review suggested |
| **Low** (30-50%) | 🟡 Yellow | Needs completion |
| **None** (<30%) | 🟡 Yellow | Manual response |

**Configuration:** Enable in `workspaces_config.json`:
```json
{
    "support-client": {
        "support_draft": true,
        "response_style": {
            "tone": "professional",
            "greeting": "Bonjour,",
            "signature": "Cordialement,\nL'équipe Support"
        }
    }
}
```

### 🔌 LLM Provider Gateway (NEW in v3.10.0)

Use **any LLM provider** without code changes:

| Provider | Type | Chat | Vision | Embeddings |
|----------|------|------|--------|------------|
| **LM Studio** | Local (default) | ✅ | ✅ | ✅ |
| **Ollama** | Local | ✅ | ✅ | ✅ |
| **OpenAI** | Cloud | ✅ | ✅ | ✅ |
| **Anthropic** | Cloud | ✅ | ✅ | ❌ |
| **Groq** | Cloud (free) | ✅ | ✅ | ❌ |
| **Mistral** | Cloud (EU) | ✅ | ✅ | ✅ |
| **Gemini** | Cloud (free) | ✅ | ✅ | ✅ |

```bash
# Switch provider in .env
LLM_PROVIDER=groq  # or openai, anthropic, mistral, gemini, ollama
GROQ_API_KEY=gsk_...
```

### ⏱️ Automated Tasks Scheduler (NEW in v3.12.0)

A robust scheduling manager for background tasks:
- Automated email ingestion at configurable intervals
- Scheduled BM25 index rebuilding
- Periodic vector database optimization

---

## 🏗️ Architecture

```
                    ┌─────────────┐
                    │ IMAP Server │
                    └──────┬──────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────┐
│                     MAIL2RAG                         │
│  Email Parser → Router → Processor → Ingestion      │
└───────┬──────────────────────────────────┬───────────┘
        │                                  │
        ▼                                  ▼
┌───────────────┐                 ┌────────────────────┐
│     TIKA      │                 │     RAG PROXY      │
│ • OCR         │                 │ • Chunking         │
│ • EXIF        │                 │ • Embeddings       │
│ • Text Extract│                 │ • BM25 Index       │
└───────────────┘                 │ • Cross-Encoder    │
                                  │ • Chat Generation  │
                                  └─────────┬──────────┘
                                            │
        ┌───────────────────────────────────┼───────────────────────┐
        │                                   │                       │
        ▼                                   ▼                       ▼
┌───────────────┐                   ┌───────────────┐       ┌───────────────┐
│    QDRANT     │                   │   LM STUDIO   │       │   STREAMLIT   │
│  Vector DB    │                   │   Local LLM   │       │   Dashboard   │
└───────────────┘                   │ (Embeddings + │       └───────────────┘
                                    │    Chat)      │
                                    └───────────────┘
```

### Services Stack

| Service | Image/Build | Port | Description |
|---------|-------------|------|-------------|
| **qdrant** | `qdrant/qdrant:latest` | 6333, 6334 | Vector database |
| **tika** | `apache/tika:latest-full` | 9998 | Text extraction + OCR |
| **rag_proxy** | Built locally | 8000 | FastAPI: chunking, embeddings, BM25, reranking, chat |
| **mail2rag** | Built locally | - | Main email processing app |
| **streamlit_admin** | Built locally | 8501 | Admin dashboard |
| **archive_server** | `nginx:alpine` | 8080 | Static file server for archived documents |

---

## ⚙️ Configuration

### Minimal `.env`

```bash
# Email
IMAP_SERVER=imap.gmail.com
IMAP_USER=your-email@gmail.com
IMAP_PASSWORD=app-password
SMTP_SERVER=smtp.gmail.com
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=app-password

# LM Studio (local)
AI_API_URL=http://host.docker.internal:1234/v1/chat/completions
AI_MODEL_NAME=qwen/qwen3-vl-8b
LM_STUDIO_URL=http://host.docker.internal:1234
EMBED_MODEL=text-embedding-bge-m3
```

### Key Options

| Variable | Default | Description |
|----------|---------|-------------|
| **Ingestion** |||
| `USE_RAG_PROXY_FOR_SEARCH` | `true` | Enable hybrid search via RAG Proxy |
| `AUTO_REBUILD_BM25` | `true` | Auto-update BM25 after ingestion |
| `CHUNK_SIZE` | `800` | Text chunk size (chars) |
| `CHUNK_OVERLAP` | `100` | Overlap between chunks |
| **Search** |||
| `USE_LOCAL_RERANKER` | `true` | Enable cross-encoder reranking |
| `LOCAL_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model |
| `MULTI_COLLECTION_MODE` | `true` | Auto-detect workspaces |
| **Document Analysis** |||
| `TIKA_ENABLE` | `true` | Enable Apache Tika |
| `VISION_ENABLE_IMAGES` | `true` | Enable Vision AI for images |
| `VISION_ENABLE_PDF` | `true` | Enable Vision AI for PDFs |
| **LLM** |||
| `LLM_CHAT_MODEL` | `qwen/qwen3-vl-8b` | Model for RAG chat |
| `LLM_MAX_CONTEXT_TOKENS` | `6000` | Max context tokens (75% of LM Studio setting) |

> 📄 See [`.env.example`](.env.example) for all 60+ configuration options.

---

## 📁 Project Structure

```
mail2rag/
├── docker-compose.yml          # 6 services orchestration
├── .env.example                 # All configuration variables
├── routing.json                 # Email routing rules
│
├── mail2rag/                    # Main email processing app
│   ├── app.py                   # Application entry point
│   ├── version.py               # Version: 3.10.0
│   ├── config.py                # Configuration management
│   ├── services/
│   │   ├── ingestion_service.py # Document ingestion
│   │   ├── processor.py         # Tika + Vision processing
│   │   ├── ragproxy_client.py   # RAG Proxy client
│   │   ├── chat_service.py      # Email chat handler
│   │   ├── tika_client.py       # Apache Tika client
│   │   ├── router.py            # Email routing logic
│   │   └── ...
│   ├── templates/               # Email HTML templates
│   └── prompts/                 # AI prompts
│
├── ragproxy/                    # FastAPI RAG engine
│   ├── main.py                  # FastAPI entry point
│   └── app/
│       ├── bm25.py              # BM25 keyword search
│       ├── chunker.py           # Intelligent text chunking
│       ├── local_reranker.py    # Cross-encoder reranker
│       ├── embeddings.py        # LM Studio embeddings
│       ├── llm_gateway.py       # LiteLLM multi-provider gateway
│       ├── vectordb.py          # Qdrant operations
│       └── pipeline.py          # Search orchestration
│
└── streamlit_admin/             # Admin dashboard
    ├── app.py                   # Streamlit entry point
    └── pages/
        ├── 1_📊_Overview.py     # System stats
        ├── 2_📄_Documents.py    # Document browser
        ├── 3_💬_Chat.py         # RAG chat interface
        └── 4_⚙️_Admin.py        # Admin operations
```

---

## 🛠️ Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f mail2rag
docker-compose logs -f rag_proxy

# Rebuild after code changes
docker-compose up -d --build

# Rebuild BM25 index for a collection
curl -X POST "http://localhost:8000/rebuild-bm25?collection=default-workspace"

# Check RAG Proxy health
curl http://localhost:8000/health

# Backup
tar -czf backup-$(date +%Y%m%d).tar.gz state/ .env routing.json
```

### API Endpoints (RAG Proxy)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/ingest` | POST | Ingest document (chunking + embedding) |
| `/search` | POST | Hybrid search (vector + BM25 + rerank) |
| `/chat` | POST | RAG chat generation |
| `/rebuild-bm25` | POST | Rebuild BM25 index |
| `/collections` | GET | List all collections |
| `/docs/{id}` | DELETE | Delete document |

> 📄 Full API documentation at [localhost:8000/docs](http://localhost:8000/docs)

---

## 🗺️ Roadmap

- [x] Streamlit Admin Dashboard
- [x] Hybrid search (Vector + BM25)
- [x] Local cross-encoder reranker
- [x] Apache Tika integration
- [x] EXIF metadata extraction
- [x] Vision AI for images/PDFs
- [x] Multi-collection support
- [x] Dynamic context management (LLM token limits)
- [x] Document/collection deletion
- [x] Support Draft Mode
- [x] LiteLLM Gateway (7 providers)
- [x] Manual document upload page
- [x] Automatic tasks scheduling manager
- [ ] Webhook integrations
- [ ] Slack/Teams connectors

---

## 📝 License

MIT License - see [LICENSE](LICENSE)

---

## 🤝 Contributing

1. Fork → 2. Branch → 3. Commit → 4. PR

---

<p align="center">
  <strong>Made with ❤️ by <a href="https://github.com/dorriklabs">dorriklabs</a></strong>
</p>

---

# 🇫🇷 Version Française

## ⚡ En Bref

Mail2RAG surveille votre boîte mail et **automatiquement** :
1. 📥 Ingère emails + pièces jointes dans Qdrant (base vectorielle)
2. 🔍 Indexe avec recherche hybride (Vecteur + BM25 + Reranking Cross-Encoder)
3. 💬 Répond aux questions par email ou via le dashboard Streamlit

> 🆕 **v3.12.0** : **Planificateur de tâches** en arrière-plan et **Page d'upload manuel** dans le dashboard !

---

## 🚀 Démarrage Rapide

```bash
# 1. Cloner & configurer
git clone https://github.com/dorriklabs/mail2rag.git
cd mail2rag && cp .env.example .env

# 2. Modifier .env avec vos identifiants IMAP/SMTP et URL LM Studio

# 3. Lancer
docker-compose up -d

# 4. Accéder au dashboard
open http://localhost:8501
```

| Service | URL | Description |
|---------|-----|-------------|
| 📊 **Streamlit Admin** | [localhost:8501](http://localhost:8501) | Dashboard principal |
| 🔍 **RAG Proxy API** | [localhost:8000/docs](http://localhost:8000/docs) | Documentation API |
| 💾 **Qdrant** | [localhost:6333/dashboard](http://localhost:6333/dashboard) | Base vectorielle |
| 📁 **Archive** | [localhost:8080](http://localhost:8080) | Serveur de fichiers |

---

## ✨ Fonctionnalités

### 📥 Ingestion d'Emails
- Surveillance IMAP avec polling configurable
- Routage intelligent par expéditeur/sujet
- Chunking intelligent avec chevauchement
- Support multi-formats (PDF, DOCX, images...)

### 📄 Analyse Documentaire

| Moteur | Capacité |
|--------|----------|
| **Tika** | Extraction texte, OCR, métadonnées |
| **Vision AI** | Description images/documents |
| **EXIF** | GPS, appareil photo, horodatage |
| **Tesseract** | OCR via Tika |

### 🔍 Recherche Hybride
- Similarité vectorielle (Qdrant)
- Correspondance mots-clés BM25
- Reranking cross-encoder local
- Support multi-collections

### 💬 Mode Chat
Envoyez `Chat: votre question` par email :
```
Sujet: Chat: Quels sont les points clés du T4 ?
```
→ Recevez une réponse IA avec citations des sources

---

## 🏗️ Architecture

### Stack des Services

| Service | Port | Description |
|---------|------|-------------|
| **qdrant** | 6333 | Base de données vectorielle |
| **tika** | 9998 | Extraction texte + OCR |
| **rag_proxy** | 8000 | FastAPI : chunking, embeddings, BM25, reranking, chat |
| **mail2rag** | - | Application principale de traitement email |
| **streamlit_admin** | 8501 | Dashboard d'administration |
| **archive_server** | 8080 | Serveur de fichiers archivés |

---

## ⚙️ Configuration Minimale

```bash
# Email
IMAP_SERVER=imap.gmail.com
IMAP_USER=votre-email@gmail.com
IMAP_PASSWORD=mot-de-passe-application
SMTP_SERVER=smtp.gmail.com
SMTP_USER=votre-email@gmail.com
SMTP_PASSWORD=mot-de-passe-application

# LM Studio (local)
AI_API_URL=http://host.docker.internal:1234/v1/chat/completions
AI_MODEL_NAME=qwen/qwen3-vl-8b
LM_STUDIO_URL=http://host.docker.internal:1234
EMBED_MODEL=text-embedding-bge-m3
```

### Options Clés

| Variable | Défaut | Description |
|----------|--------|-------------|
| `USE_RAG_PROXY_FOR_SEARCH` | `true` | Recherche hybride via RAG Proxy |
| `AUTO_REBUILD_BM25` | `true` | Rebuild auto après ingestion |
| `CHUNK_SIZE` | `800` | Taille des chunks (caractères) |
| `USE_LOCAL_RERANKER` | `true` | Activer le reranker cross-encoder |
| `TIKA_ENABLE` | `true` | Activer Apache Tika |
| `VISION_ENABLE_IMAGES` | `true` | Activer Vision AI pour images |
| `LLM_MAX_CONTEXT_TOKENS` | `6000` | Limite tokens contexte LLM |

> 📄 Voir [`.env.example`](.env.example) pour les 60+ options de configuration.

---

## 🗺️ Feuille de Route

- [x] Dashboard Admin Streamlit
- [x] Recherche hybride (Vecteur + BM25)
- [x] Reranker cross-encoder local
- [x] Intégration Apache Tika
- [x] Extraction métadonnées EXIF
- [x] Vision AI pour images/PDF
- [x] Support multi-collections
- [x] Gestion dynamique du contexte LLM
- [x] Suppression documents/collections
- [x] Mode Brouillon Support
- [x] LiteLLM Gateway (7 providers)
- [x] Page d'upload manuel de documents
- [x] Planificateur automatique de tâches
- [ ] Intégrations webhook
- [ ] Connecteurs Slack/Teams

---

<p align="center">
  <strong>Fait avec ❤️ par <a href="https://github.com/dorriklabs">dorriklabs</a></strong>
</p>
