FROM python:3.11-slim

# -----------------------------
# Dépendances système
# -----------------------------
# poppler-utils: requis pour pdf2image (Vision AI PDF)
# tesseract-ocr: retiré, OCR géré par Tika (tika:latest-full)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    libjpeg-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# -----------------------------
# Requirements
# -----------------------------
COPY requirements.txt .
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install dev dependencies if INSTALL_DEV=true
ARG INSTALL_DEV=false
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi

# -----------------------------
# Code de l'application
# -----------------------------
COPY . .

# Répertoires internes (state / logs si jamais non montés)
RUN mkdir -p /var/lib/mail2rag /var/log/mail2rag /app/logs

# -----------------------------
# Commande de démarrage
# -----------------------------
# app.py est à la racine de /app (mail2rag3/app.py)
CMD ["python", "app.py"]
