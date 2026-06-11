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
  <img src="https://img.shields.io/badge/Version-3.16.0-blue?style=flat-square" alt="Version"/>
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker"/>
  <img src="https://img.shields.io/badge/FastAPI-RAG_Proxy-009688?logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Qdrant-v1.10+-FF6B6B" alt="Qdrant"/>
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

> 🆕 **v3.14.0**: **Native Qdrant Hybrid Search (Dense+Sparse)** and **Parent-Child Context Retrieval**!

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
- Native Qdrant Dense Vectors
- Native Qdrant Sparse Vectors (FastEmbed)
- Parent-Child Context Retrieval (Sliding window)
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
| **Admin** | Manage collections, system monitoring |

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

### 🧠 Semantic Router / Dispatch IA (NEW in v3.15.0)

Automatically forward public inbox emails (e.g. `contact@...`) to the right department email addresses based on AI semantic understanding. The original email is then archived in IMAP.

**Configuration:** Enable in `.env`:
```env
ENABLE_SEMANTIC_DISPATCH=true
SEMANTIC_DISPATCH_MAPPING=Urbanisme:urba@mairie.fr,Etat-Civil:etat-civil@mairie.fr,Police:police@mairie.fr
```
*(If the AI doesn't know where to route the email, it safely leaves it in the INBOX)*

### 🔒 Strict Routing & Access Control (ACL) (NEW in v3.16.0)

Enforce strict security boundaries between workspaces. When enabled, users cannot bypass their assigned workspace by typing `Workspace: xxx` in their emails, **unless explicitly allowed via ACLs**.

**Configuration:** Enable in `.env`:
```env
ENFORCE_STRICT_ROUTING=true
```

**ACL Definition (`routing.json`):**
```json
{
    "type": "sender",
    "value": "mayor@city.gov",
    "workspace": "public_workspace",
    "allowed_workspaces": ["*", "hr_workspace"]
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
│ • Text Extract│                 │ • Sparse Vectors   │
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

```

### Secure Architecture for Production (Dual Box Strategy)

When deploying to a public environment (like a City Hall), **never connect the AI with full Chat/Ingestion permissions directly to the public inbox (`contact@...`)**. Instead, run two parallel Docker instances of Mail2RAG:

1. **Instance 1: Internal Assistant (`rag@domain.com`)**
   - **Access**: Internal network only
   - **Features**: Ingestion (`USE_RAG_PROXY_FOR_SEARCH=true`), Chat Mode
   - **Role**: AI assistant for employees

2. **Instance 2: Public Sorter (`contact@domain.com`)**
   - **Access**: Public
   - **Features**: Semantic Dispatch (`ENABLE_SEMANTIC_DISPATCH=true`), Support Draft Mode
   - **Role**: Silent sorter. Forwards emails to departments and prepares Drafts. **Zero risk** of sending an hallucinated email to a citizen.

### Services Stack

| Service | Image/Build | Port | Description |
|---------|-------------|------|-------------|
| **qdrant** | `qdrant/qdrant:latest` | 6333, 6334 | Vector database |
| **tika** | `apache/tika:latest-full` | 9998 | Text extraction + OCR |
| **rag_proxy** | Built locally | 8000 | FastAPI: chunking, embeddings, hybrid search, reranking, chat |
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
| `/search` | POST | Hybrid search (vector + sparse + rerank) |
| `/collections` | GET | List all collections |
| `/docs/{id}` | DELETE | Delete document |

> 📄 Full API documentation at [localhost:8000/docs](http://localhost:8000/docs)

---

## 🗺️ Roadmap

- [x] Streamlit Admin Dashboard : Interface Streamlit pour la supervision (recherche, stats, suppression).
- [x] Smart Ingestion Filter : (Optionnel) L'IA filtre les e-mails sans valeur documentaire ("Merci", "C'est noté") avant l'ingestion pour garder une base de connaissances propre.
- [x] Native Qdrant Hybrid search (Dense + Sparse)
- [x] Parent-Child Context Retrieval
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

> 🆕 **v3.14.0** : **Recherche Hybride Qdrant Native** et **Contexte Parent-Enfant** !

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
- Similarité vectorielle Dense (Qdrant)
- Vecteurs Creux (Sparse Vectors / FastEmbed) natifs
- Parent-Child Context Retrieval (Extension de contexte)
- Reranking cross-encoder local
- Support multi-collections

### 💬 Mode Chat
Envoyez `Chat: votre question` par email :
```
Sujet: Chat: Quels sont les points clés du T4 ?
```
→ Recevez une réponse IA avec citations des sources

### 🧠 Routeur Sémantique / Dispatch IA (NOUVEAU v3.15.0)

Transfère (Forward SMTP) automatiquement les e-mails de la boîte de réception publique (ex: `contact@...`) vers les vraies adresses e-mails des services concernés grâce à la compréhension sémantique de l'IA. L'e-mail original est ensuite archivé.

**Configuration :** Activer dans le `.env` :
```env
ENABLE_SEMANTIC_DISPATCH=true
SEMANTIC_DISPATCH_MAPPING=Urbanisme:urba@mairie.fr,Etat-Civil:etat-civil@mairie.fr
```
*(Si l'IA ne sait pas où classer l'e-mail, elle le laisse en sécurité dans l'INBOX)*

### 🔒 Routage Strict & Contrôle d'Accès (ACL) (NOUVEAU v3.16.0)

Garantissez le cloisonnement strict de vos données. Une fois activé, les utilisateurs ne peuvent plus contourner le routage automatique en tapant `Workspace: xxx` dans leurs e-mails, **sauf s'ils y sont explicitement autorisés via des ACL**.

**Configuration :** Activer dans le `.env` :
```env
ENFORCE_STRICT_ROUTING=true
```

**Définition des ACL (`routing.json`) :**
```json
{
    "type": "sender",
    "value": "maire@mairie.fr",
    "workspace": "public_workspace",
    "allowed_workspaces": ["*", "rh_workspace"]
}
```

---

## 🏗️ Architecture

### Architecture Sécurisée pour la Production (Stratégie à 2 Boîtes)

Lors du déploiement dans un environnement public (comme une Mairie), **ne connectez jamais l'IA avec tous les droits (Chat/Ingestion) directement sur la boîte publique (`contact@...`)**. À la place, lancez deux instances Docker parallèles de Mail2RAG :

1. **Instance 1 : Assistant Interne (`rag@domaine.fr`)**
   - **Accès** : Réseau interne uniquement
   - **Fonctions** : Ingestion (`USE_RAG_PROXY_FOR_SEARCH=true`), Mode Chat
   - **Rôle** : Assistant IA pour les agents

2. **Instance 2 : Trieur Public (`contact@domaine.fr`)**
   - **Accès** : Public
   - **Fonctions** : Routeur Sémantique (`ENABLE_SEMANTIC_DISPATCH=true`), Mode Brouillon Support
   - **Rôle** : Trieur silencieux. Transfère les e-mails aux services et prépare les brouillons. **Zéro risque** d'envoyer un e-mail halluciné à un citoyen.

### Stack des Services

| Service | Port | Description |
|---------|------|-------------|
| **qdrant** | 6333 | Base de données vectorielle |
| **tika** | 9998 | Extraction texte + OCR |
| **rag_proxy** | 8000 | FastAPI : chunking, embeddings, recherche hybride, reranking, chat |
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
| `CHUNK_SIZE` | `800` | Taille des chunks (caractères) |
| `USE_LOCAL_RERANKER` | `true` | Activer le reranker cross-encoder |
| `TIKA_ENABLE` | `true` | Activer Apache Tika |
| `VISION_ENABLE_IMAGES` | `true` | Activer Vision AI pour images |
| `LLM_MAX_CONTEXT_TOKENS` | `6000` | Limite tokens contexte LLM |

> 📄 Voir [`.env.example`](.env.example) pour les 60+ options de configuration.

---

## 🗺️ Feuille de Route

- [x] Dashboard Admin Streamlit
- [x] Recherche Hybride Native Qdrant (Dense + Sparse)
- [x] Parent-Child Context Retrieval
- [x] Reranker cross-encoder local
- [x] Intégration Apache Tika
- [x] Extraction métadonnées EXIF
- [x] Vision AI pour images/PDF
- [x] Support multi-collections
- [x] Gestion dynamique du contexte LLM
- [x] Suppression documents/collections
- [x] Routeur Sémantique (Dispatch IA) pour tri IMAP
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
