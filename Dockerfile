# Single image for the whole app: build the React frontend, then serve it
# from FastAPI. One service means one URL, no CORS, and one free-tier slot.

# ---------- stage 1: frontend build
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- stage 2: python runtime
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# libgomp is needed by onnxruntime (ddddocr's captcha model) on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ backend/
COPY --from=web /web/dist frontend/dist

# Warm the OCR model at build time, so the first live search doesn't pay for it.
RUN python -c "import ddddocr; ddddocr.DdddOcr(show_ad=False)"

WORKDIR /app/backend
EXPOSE 8000
# ONE worker on purpose: parked manual-captcha sessions live in process memory
# (see app/scraper/session_store.py). Sync routes still run concurrently in the threadpool.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
