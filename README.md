# 📧 Mail2RAG - Intelligent Email Ingestion System

[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Mail2RAG** is an intelligent email ingestion system that automatically converts emails and their attachments into searchable knowledge bases using RAG (Retrieval-Augmented Generation) technology.

## 🎯 Overview

Mail2RAG monitors an IMAP mailbox and automatically:
- 📥 Ingests emails with attachments into [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) workspaces
- 🤖 Provides AI-powered Q&A via email (chat mode)
- 🔍 Uses hybrid search (Vector + BM25) for optimal retrieval
- 📄 Performs OCR and document analysis on PDFs and images
- 🗂️ Routes emails to specific workspaces based on configurable rules
- ✉️ Sends beautiful HTML confirmation emails with processing summaries

## ✨ Key Features

### 🚀 Email Ingestion
- **Automatic Processing**: IMAP monitoring with configurable polling intervals
- **Smart Routing**: Route emails to specific workspaces based on sender, subject, or custom rules
- **Document Analysis**: OCR and AI-powered vision analysis for PDFs and images
- **Attachment Support**: Process multiple file types with security filtering
- **Email Summaries**: AI-generated summaries for ingested emails

### 💬 Chat Mode
- **Email-based Q&A**: Send questions via email with `Chat:` or `Question:` prefix
- **Context-Aware Responses**: Query your knowledge base through natural language
- **Hybrid Search**: Combines vector similarity and BM25 keyword matching
- **Custom Prompts**: Configure workspace-specific system prompts
- **Source Citations**: Responses include source document references

### 🔧 Advanced Features
- **Multi-threading**: Concurrent email processing with worker pools
- **Secure Archive**: Web-accessible archive server with opaque IDs
- **Workspace Management**: Auto-creation and configuration of workspaces
- **Q&A Rewriting**: Transform support emails into structured Q&A pairs
- **State Management**: Persistent state tracking to avoid reprocessing
- **Synthetic Emails**: Support for programmatic email injection

## 🏗️ Architecture

```
┌─────────────────┐
│  IMAP Server    │ Email Source
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Mail2RAG      │ Email Processing & Orchestration
│   (Python)      │ - Email parsing
│                 │ - Document processing
│                 │ - Routing logic
│                 │ - Chat handling
└─────┬───────────┘
      │
      ├─────────────────────┐
      │                     │
      ▼                     ▼
┌─────────────┐       ┌─────────────┐
│ AnythingLLM │       │  RAG Proxy  │
│             │       │  (FastAPI)  │
│ - Vector DB │       │ - BM25 Index│
│ - Embeddings│       │ - Reranking │
│ - Workspaces│       │ - Hybrid    │
└─────┬───────┘       └──────┬──────┘
      │                      │
      ▼                      ▼
┌─────────────┐       ┌─────────────┐
│   Qdrant    │       │  LM Studio  │
│ Vector DB   │       │  (Local LLM)│
└─────────────┘       └─────────────┘

      ▼
┌─────────────────┐
│ Archive Server  │ NGINX - Public document access
│    (NGINX)      │
└─────────────────┘
```

### Components

1. **Mail2RAG** - Main application (Python)
   - IMAP email monitoring
   - Document processing and OCR
   - Routing and workspace management
   - Chat query handling

2. **AnythingLLM** - Knowledge base management
   - Document storage and embedding
   - Workspace organization
   - Vector search

3. **Qdrant** - Vector database
   - Efficient similarity search
   - Scalable storage

4. **RAG Proxy** - Hybrid search engine
   - BM25 full-text search
   - LLM-based reranking
   - Search result fusion

5. **Archive Server** - Document hosting (NGINX)
   - Secure public access to processed emails
   - Web-based archive browsing

## 📋 Prerequisites

- **Docker** and **Docker Compose**
- **IMAP Email Account** (Gmail, Outlook, custom server)
- **LM Studio** (optional, for local LLM - required for RAG Proxy)
- **SMTP Server** (for sending email responses)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/dorriklabs/mail2rag.git
cd mail2rag
```

### 2. Configure Environment

Create a `.env` file in the root directory:

```bash
# AnythingLLM Configuration
ANYTHINGLLM_API_KEY=your_anythingllm_api_key
DEFAULT_WORKSPACE=general

# IMAP Configuration
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your-email@gmail.com
IMAP_PASSWORD=your-app-password
IMAP_FOLDER=INBOX
IMAP_SEARCH_CRITERIA=UNSEEN
IMAP_POLL_INTERVAL=60

# SMTP Configuration (for sending replies)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=your-email@gmail.com

# Archive Server
ARCHIVE_BASE_URL=http://localhost:8080

# RAG Proxy (Optional - for hybrid search)
USE_RAG_PROXY_FOR_SEARCH=false
RAG_PROXY_URL=http://rag_proxy:8000

# LM Studio (Optional - for RAG Proxy)
LM_STUDIO_URL=http://host.docker.internal:1234
AI_MODEL_NAME=your-model-name

# Feature Flags
ENABLE_EMAIL_SUMMARY=true
SAVE_CHAT_HISTORY=true
SYNC_ON_START=true
```

### 3. Configure Routing (Optional)

Edit `routing.json` to define workspace routing rules:

```json
{
    "rules": [
        {
            "type": "sender",
            "value": "boss@example.com",
            "workspace": "urgent_workspace"
        },
        {
            "type": "subject",
            "value": "Invoice",
            "workspace": "finance_workspace"
        }
    ]
}
```

### 4. Launch the Stack

```bash
docker-compose up -d
```

### 5. Verify Services

Check that all services are running:

```bash
docker-compose ps
```

Access the web interfaces:
- **AnythingLLM**: http://localhost:3001
- **Qdrant Dashboard**: http://localhost:6333/dashboard
- **Archive Server**: http://localhost:8080
- **RAG Proxy** (if enabled): http://localhost:8000/docs

## 📖 Usage

### Email Ingestion Mode

Simply send an email with attachments to your configured inbox. Mail2RAG will:
1. Extract email content and attachments
2. Route to the appropriate workspace
3. Generate embeddings and index documents
4. Send a confirmation email with processing summary

**Example Email:**
```
To: your-inbox@example.com
Subject: Q4 Financial Report
Attachments: report.pdf, charts.xlsx

Please index this quarterly financial report for our records.
```

### Chat/Q&A Mode

Send an email with `Chat:` or `Question:` prefix in the subject:

**Example Email:**
```
To: your-inbox@example.com
Subject: Chat: What were the key findings in the Q4 report?

I need a summary of the main financial highlights from last quarter.
```

Mail2RAG will:
1. Search relevant documents in the workspace
2. Generate an AI-powered response
3. Reply with the answer and source citations

## ⚙️ Configuration

### Workspace Settings

Configure workspace-specific behaviors in `.env`:

```bash
# Example: Enable Q&A rewriting for support workspace
WORKSPACE_SETTINGS={"support_workspace": {"qa_rewrite": true}}
```

### Custom Prompts

Create custom system prompts for workspaces in `mail2rag/prompts/`:

**Example: `mail2rag/prompts/support_workspace.txt`**
```
You are a helpful customer support assistant. Answer questions based on the provided documentation.
Be friendly, concise, and always cite your sources.
```

### Document Processing

Configure OCR and document analysis:

```bash
# Enable/disable features
ENABLE_OCR=true
ENABLE_VISION_ANALYSIS=true

# Processing limits
MAX_ATTACHMENT_SIZE=10485760  # 10MB
MAX_FILENAME_LENGTH=100
```

## 🗂️ Project Structure

```
mail2rag/
├── docker-compose.yml          # Docker orchestration
├── .env                        # Environment configuration
├── routing.json                # Email routing rules
├── nginx.conf                  # Archive server config
│
├── mail2rag/                   # Main application
│   ├── app.py                  # Application entry point
│   ├── config.py               # Configuration management
│   ├── client.py               # AnythingLLM client
│   ├── Dockerfile              # Container definition
│   ├── requirements.txt        # Python dependencies
│   │
│   ├── services/               # Service modules
│   │   ├── mail.py            # IMAP/SMTP handling
│   │   ├── router.py          # Email routing
│   │   ├── processor.py       # Document processing
│   │   ├── cleaner.py         # Content cleaning
│   │   ├── maintenance.py     # System maintenance
│   │   ├── support_qa.py      # Q&A rewriting
│   │   └── utils.py           # Utilities
│   │
│   ├── templates/              # Email templates
│   │   ├── ingestion_success.html
│   │   ├── ingestion_error.html
│   │   ├── chat_response.html
│   │   └── crash_report.html
│   │
│   └── prompts/                # Workspace prompts
│       └── *.txt
│
├── ragproxy/                   # RAG Proxy service
│   ├── main.py                 # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── embeddings.py       # Embedding utilities
│       └── bm25_index.py       # BM25 indexing
│
├── state/                      # Persistent state
├── logs/                       # Application logs
└── README.md                   # This file
```

## 🛠️ Maintenance

### Viewing Logs

```bash
# Mail2RAG logs
docker-compose logs -f mail2rag

# All services
docker-compose logs -f
```

### Backup State

```bash
# Backup state and configuration
tar -czf backup-$(date +%Y%m%d).tar.gz state/ .env routing.json
```

### Rebuild Services

```bash
# Rebuild after code changes
docker-compose up -d --build

# Restart specific service
docker-compose restart mail2rag
```

## 🔒 Security Considerations

- **Email Credentials**: Never commit `.env` file - use `.env.example` template
- **Archive Access**: Archive server uses opaque IDs to prevent enumeration
- **Attachment Filtering**: Configure allowed file types in `CleanerService`
- **Network Isolation**: Services communicate via internal Docker network
- **SMTP Security**: Use app-specific passwords, not account passwords

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) - Universal LLM wrapper
- [Qdrant](https://qdrant.tech/) - Vector database
- [LM Studio](https://lmstudio.ai/) - Local LLM runtime

## 📞 Support

- 🐛 **Issues**: [GitHub Issues](https://github.com/dorriklabs/mail2rag/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/dorriklabs/mail2rag/discussions)

## 🗺️ Roadmap

- [ ] Web UI for configuration and monitoring
- [ ] Multi-language support
- [ ] Advanced attachment preview in emails
- [ ] Webhook integrations
- [ ] Slack/Teams connectors
- [ ] Mobile app

---

**Made with ❤️ by dorriklabs**
