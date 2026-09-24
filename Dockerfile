# syntax=docker/dockerfile:1

# ── Stage 1: Build do Frontend React com Node 20 ──────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copia package.json e instala dependências
COPY frontend/package.json ./
RUN npm install

# Copia o código-fonte do frontend e compila o bundle estático
COPY frontend/ ./
RUN npm run build


# ── Stage 2: Imagem final em Python com FastAPI e Motores IA ──────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Dependências de sistema para OpenCV e FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia código do backend e motores
COPY . .

# Copia o frontend compilado do Stage 1 para servir via FastAPI
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Cria diretórios de armazenamento e logs
RUN mkdir -p storage/temp_uploads storage/chunk_uploads storage/extracted_frames storage/outputs storage/jobs logs

# Porta de serviço (mantém 8501 para compatibilidade com o Render)
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8501/api/health || exit 1

ENV PYTHONPATH=/app \
    PORT=8501

# Inicializa o servidor FastAPI servindo o React na porta dinâmica do ambiente ($PORT)
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8501}"]
