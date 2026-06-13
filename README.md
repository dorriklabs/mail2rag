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
  <img src="https://img.shields.io/badge/Version-3.22.1-blue?style=flat-square" alt="Version"/>
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
- **Protocoles supportés :** IMAP classique ou Microsoft Graph API (OAuth2)
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
| **Users** | Manage access rules and passwords |
| **Audit** | View centralized search logs and activity |
| **My Account** | Secure user password management |

### 📊 AI Observability & Audit Logs (NEW in v3.17.0)

Mail2RAG now features enterprise-grade observability:
- **Structured JSON Logging**: All backend and proxy logs are emitted in strict JSONL format (`timestamp`, `level`, `message`, `exception`). This makes debugging instantly parsable by AI maintenance agents or monitoring stacks (Datadog, Splunk).
- **Centralized Audit Log**: Every search query (from Email or Dashboard) is recorded with its source, the user, the target workspaces, and the exact query.
- **Admin Audit Interface**: A dedicated Streamlit page allows administrators to filter, monitor, and clear search activity in real-time.

### 🧠 Advanced Conversational RAG & Smart Rewriting (NEW in v3.18.0)

Turn multi-turn conversations into highly accurate RAG queries without losing context:
- **Zero-Hallucination Query Rewriting**: Uses a strict Few-Shot prompt to transform pronoun-heavy follow-up questions ("What is it?", "How much was it?") into standalone search queries ("What is the PLUI?", "What is the Norauto invoice amount?").
- **Full Conversational Memory**: The final AI prompt dynamically receives the conversation history, allowing it to provide highly natural, fluid, and context-aware responses without repeating previously stated definitions.
- **Dynamic Context Safety**: Automatically calculates text chunks token size before sending them to the LLM. It guarantees the LLM will never crash due to memory overflow, strictly enforcing the `LLM_MAX_CONTEXT_TOKENS` limit.
- **Semantic Cache Isolation**: Responses are cached with exactly 1.000 similarity matching. The cache system is now cleanly isolated from user searches to prevent recursive pollution, and the Streamlit UI visually groups citations by their source collection (Workspace).

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

**UX Improvements & Notifications:**
- **Universal Webhooks (Teams, Slack, Google Chat):** Native integration to alert support channels when an AI draft is ready or an email is semantically dispatched.
- **Safe Visual Banners:** AI drafts include a prominent dashed red banner (`⚠️ À EFFACER AVANT ENVOI`) to prevent accidental internal notes leakage.
- **Seamless Replies (IMAP Combined Email):** Instead of fragile IMAP draft creation, the system forwards a combined email (AI Draft + Original Email) to the support team. It automatically injects the `Reply-To` header and `Message-ID` so agents can simply click "Reply" and target the citizen natively, perfectly preserving the thread.

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

**Bloquer les expéditeurs externes (`ALLOWED_DOMAINS`) :**
Si vous n'avez pas le contrôle sur votre serveur de messagerie pour bloquer les e-mails entrants, vous pouvez restreindre l'utilisation de Mail2RAG (Ingestion et Chat) aux seuls expéditeurs de votre organisation. Tout autre expéditeur sera silencieusement ignoré.
```env
ALLOWED_DOMAINS=mairie.fr, dsialantic.com
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

**Multi-Workspace & Global Search:**
- **Comma-separated search:** Users can search across multiple allowed workspaces by separating them with a comma (e.g., `Workspace: police, hr`). The RAG Proxy will query all of them and use the **Cross-Encoder Reranker** to fuse and keep the best absolute results regardless of their origin collection.
- **Wildcard search (`*`):** A user can ask for `Workspace: *`. The router will automatically expand this to all workspaces they have access to. If they have the absolute `["*"]` ACL, it dynamically expands to all collections in the Qdrant database. If they don't have access to a requested workspace, the system safely ignores it and adds a warning to the final response.
- **High-Performance Concurrency:** When querying multiple workspaces, Mail2RAG uses **Multi-Threading** to fetch vectors concurrently from Qdrant, dropping response times to mere milliseconds. A **Dynamic Top-K Limiter** automatically protects the AI Reranker from being overwhelmed when querying dozens of collections simultaneously, ensuring sub-second speeds.

### 🧠 Custom AI Prompts per Workspace (NEW in v3.17.0)

Define specific behaviors, tones, or business rules for each workspace individually. 
When a user queries a specific workspace (e.g., `HR` or `Legal`), the AI adopts the corresponding system prompt (e.g., *"Answer like a lawyer, cite articles"*) instead of the global default.
Easily configurable directly from the Streamlit Admin Dashboard.

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
- [x] Custom AI Prompts per Workspace
- [x] Streamlit Audit Dashboard & User Password Management
- [x] Structured JSON Logging for AI Observability
- [x] Advanced Conversational RAG & Smart Query Rewriting
- [x] Streamlit UI Source Grouping & Semantic Cache improvements
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

**Bloquer les expéditeurs externes (`ALLOWED_DOMAINS`) :**
Si vous ne maîtrisez pas les règles de votre serveur de messagerie, vous pouvez interdire l'accès à Mail2RAG aux expéditeurs externes directement au niveau applicatif. Leurs e-mails seront silencieusement ignorés, protégeant la base de données.
```env
ALLOWED_DOMAINS=mairie.fr, dsialantic.com
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

**Recherche Multi-Workspaces & Globale :**
- **Recherche multiple (virgule) :** Les utilisateurs peuvent chercher dans plusieurs workspaces en les séparant par des virgules (ex: `Workspace: police, rh`). Le RAG Proxy interrogera toutes les bases concernées et utilisera le **Reranker Cross-Encoder** pour fusionner et conserver les meilleurs résultats absolus, peu importe leur collection d'origine.
- **Recherche Globale (`*`) :** Un utilisateur peut demander `Workspace: *`. Le routeur convertira automatiquement cette étoile en la liste de tous les dossiers auxquels il a droit. S'il possède l'ACL suprême `["*"]`, la recherche sera étendue à toutes les bases existantes dans Qdrant en temps réel. Si un utilisateur demande un accès non autorisé, la demande est ignorée de façon sécurisée et un avertissement est ajouté à la réponse.
- **Haute Performance (Concurrency) :** Lors de la recherche sur de multiples workspaces, Mail2RAG utilise du **Multi-Threading** pour interroger toutes les bases Qdrant en parallèle, garantissant une extraction en quelques millisecondes. Une **Limite Top-K Dynamique** protège automatiquement le Reranker IA contre la surcharge si un utilisateur interroge 50 collections à la fois, assurant un temps de réponse instantané.

### 🧠 Prompts IA Personnalisés par Workspace (NOUVEAU v3.17.0)

Définissez des comportements, un ton de voix ou des règles métier spécifiques pour chaque espace de travail.
Lorsqu'un utilisateur interroge un workspace ciblé (ex: `Ressources Humaines` ou `Juridique`), l'IA adopte la consigne système correspondante (ex: *"Réponds comme un avocat, cite les articles de loi"*) au lieu du prompt global par défaut.
Configurable facilement et en temps réel depuis l'onglet "Prompts IA" du Dashboard Admin Streamlit.

### 🧠 RAG Conversationnel Avancé & Cache Sémantique (NOUVEAU v3.18.0)

Mail2Rag gère désormais les conversations multi-tours à la perfection :
- **Reformulation Intelligente (Few-Shot) :** Les questions contenant des pronoms ("A quoi ça sert ?") sont analysées via l'historique et transformées en requêtes de recherche autonomes de haute précision.
- **Mémoire Conversationnelle Fluide :** L'historique des échanges est réinjecté de manière sécurisée dans la réflexion finale de l'IA. Elle rebondit naturellement sur ses propres propos sans jamais se répéter inutilement ("Syndrome du perroquet").
- **Sécurité Mémoire Dynamique :** Le système compte le nombre exact de "tokens" de chaque extrait de document avant de l'envoyer à l'IA. Si la limite de sécurité (ex: 6000 tokens) est atteinte, les derniers documents sont ignorés pour éviter tout crash serveur (OOM).
- **Isolation du Cache Sémantique :** Les réponses mises en cache sont désormais invisibles lors des recherches manuelles pour éviter la pollution des résultats. L'interface Streamlit regroupe visuellement les vraies sources sous le nom de leur collection respective (ex: "Urbanisme") pour une traçabilité parfaite.

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
- [x] Personnalisation des prompts par workspace
- [x] Dashboard d'Audit Streamlit & Gestion des mots de passe
- [x] Format de Logging JSON Structuré pour l'observabilité IA
- [x] RAG Conversationnel Avancé & Reformulation (Few-Shot)
- [x] UI : Regroupement visuel des sources par collection
- [ ] Intégrations webhook
- [ ] Connecteurs Slack/Teams

---

<p align="center">
  <strong>Fait avec ❤️ par <a href="https://github.com/dorriklabs">dorriklabs</a></strong>
</p>
