"""
Modulo di trascrizione basato su OpenAI Whisper (open-source).
Whisper scarica i modelli da GitHub Releases — nessun token richiesto.

Modelli disponibili (ordine crescente di accuratezza/lentezza):
  tiny, base, small, medium, large, large-v2, large-v3
"""

import os
import logging
import warnings
from typing import Optional
import whisper

warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

logger = logging.getLogger(__name__)

# Cache in-process dei modelli già caricati
_model_cache: dict = {}


def _load_model(model_size: str) -> whisper.Whisper:
    if model_size not in _model_cache:
        logger.info(f"Caricamento modello Whisper '{model_size}' (primo avvio: download automatico)...")
        _model_cache[model_size] = whisper.load_model(model_size)
        logger.info(f"Modello '{model_size}' caricato.")
    return _model_cache[model_size]


def transcribe_audio(
    audio_path: str,
    model_size: str = "base",
    language: Optional[str] = "it",
) -> list[dict]:
    """
    Trascrive un file audio WAV e restituisce una lista di segmenti con timestamp.

    Args:
        audio_path: percorso del file WAV (mono 16kHz, prodotto da audio_utils)
        model_size: dimensione del modello Whisper
        language: codice lingua ISO 639-1 (es. 'it', 'en') o None per auto-detect

    Returns:
        Lista di dizionari:
        [
          {"start": 0.0, "end": 2.5, "text": "Ciao come stai"},
          ...
        ]
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"File audio non trovato: {audio_path}")

    model = _load_model(model_size)

    decode_options: dict = {
        "task": "transcribe",
        "word_timestamps": True,
        "verbose": False,
    }
    if language:
        decode_options["language"] = language

    logger.info(f"Inizio trascrizione: {audio_path}")
    result = model.transcribe(audio_path, **decode_options)

    segments = []
    for seg in result.get("segments", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        segments.append(
            {
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": text,
                "words": [
                    {
                        "word": w.get("word", "").strip(),
                        "start": float(w.get("start", seg["start"])),
                        "end": float(w.get("end", seg["end"])),
                    }
                    for w in seg.get("words", [])
                ],
            }
        )

    logger.info(f"Trascrizione completata: {len(segments)} segmenti")
    return segments
