"""
Modulo di trascrizione basato su faster-whisper.

faster-whisper usa CTranslate2 con quantizzazione int8 su CPU:
rispetto a openai-whisper è ~4x più veloce a parità di modello.

Modelli disponibili (ordine crescente di accuratezza/lentezza):
  tiny, base, small, medium, large-v2, large-v3
"""

import os
import logging
from typing import Optional
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Cache in-process dei modelli già caricati
_model_cache: dict = {}


def _load_model(model_size: str) -> WhisperModel:
    if model_size not in _model_cache:
        logger.info(f"Caricamento modello faster-whisper '{model_size}'...")
        # int8 su CPU: massima velocità senza perdita apprezzabile di qualità
        _model_cache[model_size] = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
        )
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

    logger.info(f"Inizio trascrizione: {audio_path}")
    segments_iter, _ = model.transcribe(
        audio_path,
        language=language,
        task="transcribe",
        word_timestamps=True,
        vad_filter=True,          # salta silenzio automaticamente
        vad_parameters={
            "min_silence_duration_ms": 500,
        },
        beam_size=5,
    )

    segments = []
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        segments.append(
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": text,
                "words": [
                    {
                        "word": w.word.strip(),
                        "start": float(w.start),
                        "end": float(w.end),
                    }
                    for w in (seg.words or [])
                ],
            }
        )

    logger.info(f"Trascrizione completata: {len(segments)} segmenti")
    return segments
