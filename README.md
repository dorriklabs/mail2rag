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
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker"/>
  <img src="https://img.shields.io/badge/FastAPI-RAG_Proxy-009688?logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Qdrant-Vector_DB-FF6B6B?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0xMiAyTDIgN2wxMCA1IDEwLTV6Ii8+PC9zdmc+" alt="Qdrant"/>
  <img src="https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?logo=streamlit&logoColor=white" alt="Streamlit"/>
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License"/>
</p>

---

## ⚡ TL;DR

Mail2RAG monitors your inbox and **automatically**:
1. 📥 Ingests emails + attachments into a vector database
2. 🔍 Indexes with hybrid search (Vector + BM25 + Reranking)
3. 💬 Answers questions via email using RAG

**Send an email → Get it indexed → Query via email or dashboard**

---

## 🚀 Quick Start

```bash
# 1. Clone & configure
git clone https://github.com/dorriklabs/mail2rag.git
cd mail2rag && cp .env.example .env

# 2. Edit .env with your IMAP/SMTP credentials

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
| **Tesseract** | OCR fallback |

</td>
<td width="50%" valign="top">

### 🔍 Hybrid Search
- Vector similarity (Qdrant)
- BM25 keyword matching
- Cross-encoder reranking
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
| **Chat** | Test RAG queries directly |
| **Admin** | Rebuild BM25, view logs, manage collections |

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
┌───────────────┐                 ┌────────────────┐
│     TIKA      │                 │   RAG PROXY    │
│ • OCR         │                 │ • Chunking     │
│ • EXIF        │                 │ • Embeddings   │
│ • Text Extract│                 │ • BM25 Index   │
└───────────────┘                 │ • Reranking    │
                                  └───────┬────────┘
                                          │
        ┌─────────────────────────────────┼─────────────────────┐
        │                                 │                     │
        ▼                                 ▼                     ▼
┌───────────────┐                 ┌───────────────┐     ┌───────────────┐
│    QDRANT     │                 │   LM STUDIO   │     │   STREAMLIT   │
│  Vector DB   │                 │   Local LLM   │     │   Dashboard   │
└───────────────┘                 └───────────────┘     └───────────────┘
```
### Minimal `.env`

```bash
# Email
IMAP_SERVER=imap.gmail.com
IMAP_USER=your-email@gmail.com
IMAP_PASSWORD=app-password
SMTP_SERVER=smtp.gmail.com
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=app-password

# LM Studio
AI_API_URL=http://host.docker.internal:1234/v1/chat/completions
AI_MODEL_NAME=qwen/qwen3-vl-8b
```

### Key Options

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_RAGPROXY_INGESTION` | `true` | Use RAG Proxy for ingestion |
| `USE_RAG_PROXY_FOR_SEARCH` | `true` | Enable hybrid search |
| `AUTO_REBUILD_BM25` | `true` | Auto-update BM25 after ingestion |
| `CHUNK_SIZE` | `800` | Text chunk size (chars) |
| `CHUNK_OVERLAP` | `100` | Overlap between chunks |
| `USE_LOCAL_RERANKER` | `true` | Enable cross-encoder reranking |
| `TIKA_ENABLE` | `true` | Enable Apache Tika |
| `VISION_ENABLE` | `true` | Enable Vision AI analysis |

> 📄 See [`.env.example`](.env.example) for all options.

---

## 📁 Project Structure

```
mail2rag/
├── docker-compose.yml
├── .env.example
├── routing.json              # Email routing rules
│
├── mail2rag/                 # Main app
│   ├── app.py
│   ├── services/
│   │   ├── ingestion_service.py
│   │   ├── processor.py      # Tika + Vision
│   │   ├── ragproxy_client.py
│   │   └── ...
│   ├── templates/            # Email templates
│   └── prompts/              # AI prompts
│
├── ragproxy/                 # Search engine
│   ├── main.py
│   └── app/
│       ├── bm25.py
│       ├── chunker.py
│       ├── local_reranker.py
│       └── pipeline.py
│
└── streamlit_admin/          # Dashboard
    ├── app.py
    └── pages/
```

---

## 🛠️ Commands

```bash
# Start
docker-compose up -d

# Logs
docker-compose logs -f mail2rag
docker-compose logs -f rag_proxy

# Rebuild after changes
docker-compose up -d --build

# Rebuild BM25 index
curl -X POST "http://localhost:8000/rebuild-bm25?collection=default-workspace"

# Backup
tar -czf backup-$(date +%Y%m%d).tar.gz state/ .env routing.json
```

---

## 🗺️ Roadmap

- [x] Streamlit Admin Dashboard
- [x] Hybrid search (Vector + BM25)
- [x] Local cross-encoder reranker
- [x] Apache Tika integration
- [x] EXIF metadata extraction
- [x] Complete AnythingLLM replacement
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
1. 📥 Ingère emails + pièces jointes dans une base vectorielle
2. 🔍 Indexe avec recherche hybride (Vecteur + BM25 + Reranking)
3. 💬 Répond aux questions par email via RAG

---

## 🚀 Démarrage Rapide

```bash
# 1. Cloner & configurer
git clone https://github.com/dorriklabs/mail2rag.git
cd mail2rag && cp .env.example .env

# 2. Modifier .env avec vos identifiants IMAP/SMTP

# 3. Lancer
docker-compose up -d

# 4. Accéder au dashboard
open http://localhost:8501
```

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
| **EXIF** | GPS, appareil, horodatage |
| **Tesseract** | OCR de secours |

### 🔍 Recherche Hybride
- Similarité vectorielle (Qdrant)
- Correspondance mots-clés BM25
- Reranking cross-encoder
- Support multi-collections

### 💬 Mode Chat
Envoyez `Chat: votre question` par email :
```
Sujet: Chat: Quels sont les points clés du T4 ?
```
→ Recevez une réponse IA avec citations des sources

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

# LM Studio
AI_API_URL=http://host.docker.internal:1234/v1/chat/completions
AI_MODEL_NAME=qwen/qwen3-vl-8b
```

### Options Clés

| Variable | Défaut | Description |
|----------|--------|-------------|
| `USE_RAGPROXY_INGESTION` | `true` | Ingestion via RAG Proxy |
| `AUTO_REBUILD_BM25` | `true` | Rebuild auto après ingestion |
| `CHUNK_SIZE` | `800` | Taille des chunks (caractères) |
| `USE_LOCAL_RERANKER` | `true` | Activer le reranker local |
| `TIKA_ENABLE` | `true` | Activer Apache Tika |
| `VISION_ENABLE` | `true` | Activer Vision AI |

---

## 🗺️ Feuille de Route

- [x] Dashboard Admin Streamlit
- [x] Recherche hybride (Vecteur + BM25)
- [x] Reranker cross-encoder local
- [x] Intégration Apache Tika
- [x] Extraction métadonnées EXIF
- [x] Remplacement complet d'AnythingLLM
- [ ] Intégrations webhook
- [ ] Connecteurs Slack/Teams

---

<p align="center">
  <strong>Fait avec ❤️ par <a href="https://github.com/dorriklabs">dorriklabs</a></strong>
</p>
