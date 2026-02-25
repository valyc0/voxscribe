"""
Modulo di trascrizione basato su faster-whisper.

faster-whisper usa CTranslate2:
  - int8      : CPU, massima velocità, lieve perdita qualità (ok per tiny/base/small)
  - float32   : CPU, qualità massima (usato per medium/large)

Modelli disponibili (ordine crescente accuratezza/lentezza):
  tiny, base, small, medium, large-v2, large-v3
  ("large" è un alias per large-v3)
"""

import os
import logging
from typing import Optional
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Cache in-process dei modelli già caricati
_model_cache: dict = {}

# Alias: "large" punta a large-v3 (il più accurato)
_MODEL_ALIASES = {
    "large": "large-v3",
}

# Modelli che beneficiano di float32 invece di int8
_FLOAT32_MODELS = {"medium", "large-v2", "large-v3"}

# Initial prompt per lingua: aiuta Whisper a usare la grafia corretta
_INITIAL_PROMPTS = {
    "it": "Trascrizione in italiano.",
    "en": "Transcription in English.",
    "fr": "Transcription en français.",
    "de": "Transkription auf Deutsch.",
    "es": "Transcripción en español.",
    "pt": "Transcrição em português.",
}


def _load_model(model_size: str) -> WhisperModel:
    resolved = _MODEL_ALIASES.get(model_size, model_size)
    if resolved not in _model_cache:
        compute = "float32" if resolved in _FLOAT32_MODELS else "int8"
        logger.info(f"Caricamento modello faster-whisper '{resolved}' (compute={compute})...")
        _model_cache[resolved] = WhisperModel(
            resolved,
            device="cpu",
            compute_type=compute,
        )
        logger.info(f"Modello '{resolved}' caricato.")
    return _model_cache[resolved]


def transcribe_audio(
    audio_path: str,
    model_size: str = "small",
    language: Optional[str] = "it",
) -> list[dict]:
    """
    Trascrive un file audio WAV e restituisce una lista di segmenti con timestamp.

    Args:
        audio_path: percorso del file WAV (mono 16kHz, prodotto da audio_utils)
        model_size: dimensione del modello Whisper (tiny/base/small/medium/large-v2/large-v3/large)
        language: codice lingua ISO 639-1 (es. 'it', 'en') o None per auto-detect

    Returns:
        Lista di dizionari: [{"start", "end", "text", "words"}, ...]
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"File audio non trovato: {audio_path}")

    resolved = _MODEL_ALIASES.get(model_size, model_size)
    model = _load_model(model_size)

    # beam_size più alto per modelli grandi (qualità > velocità)
    beam_size = 10 if resolved in _FLOAT32_MODELS else 5

    initial_prompt = _INITIAL_PROMPTS.get(language or "", None)

    logger.info(f"Inizio trascrizione: {audio_path} [modello={resolved}, lingua={language or 'auto'}, beam={beam_size}]")

    segments_iter, info = model.transcribe(
        audio_path,
        language=language,
        task="transcribe",
        word_timestamps=True,
        beam_size=beam_size,
        # Riduce le allucinazioni su silenzi/rumore
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 200,
        },
        # Anti-allucinazione: scarta segmenti poco probabili
        log_prob_threshold=-1.0,        # default -1.0; abbassare filtra segmenti incerti
        no_speech_threshold=0.5,        # default 0.6; abbassare = più sensibile al parlato
        compression_ratio_threshold=2.4, # filtra output con troppa ripetizione
        # Testa più temperature in caso di fallimento
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        condition_on_previous_text=True,
        initial_prompt=initial_prompt,
    )

    logger.info(f"Lingua rilevata: {info.language} (probabilità: {info.language_probability:.2f})")

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
