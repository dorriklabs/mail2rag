FROM python:3.11-slim

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    libjpeg-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier les requirements en premier pour utiliser le cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY . .

# Créer les répertoires nécessaires
RUN mkdir -p /var/lib/mail2rag /app/logs

# Définir le point d'entrée
CMD ["python", "app.py"]
