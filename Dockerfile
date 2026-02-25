# ──────────────────────────────────────────────────────────────────────────────
# Base: Python 3.11 slim + ffmpeg
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Variabili di ambiente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Directory cache modelli (whisper + resemblyzer)
    XDG_CACHE_HOME=/app/.cache \
    WHISPER_CACHE=/app/.cache/whisper

WORKDIR /app

# ── Dipendenze di sistema ─────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Dipendenze Python ─────────────────────────────────────────────────────────
COPY requirements.txt .

# Installa torch CPU-only (più leggero; rimuovi --index-url per GPU CUDA)
# numpy<2 è fissato in requirements.txt per compatibilità con torch 2.2
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        "numpy>=1.26.0,<2.0" && \
    pip install --no-cache-dir \
        torch==2.2.0 torchaudio==2.2.0 \
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# ── Sorgenti ──────────────────────────────────────────────────────────────────
COPY app.py transcriber.py diarizer.py audio_utils.py ./
COPY client-web/ ./client-web/

# Pre-scarica il modello faster-whisper "small" durante il build
# (migliore accuratezza sull'italiano rispetto a base/tiny)
RUN python -c "\
from faster_whisper import WhisperModel; \
WhisperModel('small', device='cpu', compute_type='int8', download_root='/app/.cache/whisper')"

# ── Avvio ─────────────────────────────────────────────────────────────────────
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
