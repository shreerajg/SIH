# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TOKENIZERS_PARALLELISM=false \
    HF_HOME=/app/storage/hf

WORKDIR /app

# Build tools are needed for a few wheels and are removed again in the same
# layer; tesseract-ocr is a runtime dependency (consumer label scanning) and
# is kept - without it, app/services/ocr.py degrades to "OCR unavailable"
# rather than failing, but the feature would silently not work in production.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl tesseract-ocr \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install -r requirements.txt \
 && apt-get purge -y build-essential && apt-get autoremove -y

COPY app ./app
COPY tests ./tests
COPY pytest.ini .

# Bake the embedding model into the image so the first request is not a
# multi-second download (and so the container works without egress).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" \
 || echo "Embedding model not pre-cached; the hashing fallback will be used if it cannot be fetched at runtime."

RUN mkdir -p /app/storage/chroma

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
