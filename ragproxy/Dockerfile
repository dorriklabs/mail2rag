FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install dev dependencies if needed (optional build arg)
ARG INSTALL_DEV=false
COPY requirements-dev.txt .
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi

# Copy application code (changes often, so last)
COPY main.py ./main.py
COPY app ./app
COPY tests ./tests

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
