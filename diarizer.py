"""
Modulo di diarizzazione speaker.

Pipeline senza token:
  1. Carica l'audio WAV con resemblyzer
  2. Calcola embedding vocali su finestre temporali scorrevoli
  3. Raggruppa gli embedding con Spectral/Agglomerative Clustering (sklearn)
  4. Assegna lo speaker dominante ad ogni segmento Whisper

Librerie usate (tutte installabili via pip, nessun token):
  - resemblyzer  : encoder voce pre-addestrato (scarica ~17 MB da GitHub)
  - scikit-learn : clustering
  - numpy        : algebra lineare
"""

import logging
import numpy as np
from typing import Optional

from resemblyzer import VoiceEncoder, preprocess_wav
from sklearn.cluster import AgglomerativeClustering, SpectralClustering
from sklearn.preprocessing import normalize

logger = logging.getLogger(__name__)

# Finestra e passo in secondi per il calcolo degli embedding
WINDOW_SEC = 1.5
STEP_SEC = 0.5
MIN_SEGMENT_DURATION = 0.3  # segmenti più brevi vengono ignorati nel clustering


def diarize_audio(
    audio_path: str,
    segments: list[dict],
    num_speakers: Optional[int] = None,
) -> list[dict]:
    """
    Assegna uno speaker a ogni segmento Whisper.

    Args:
        audio_path  : percorso WAV mono 16kHz
        segments    : lista segmenti da transcriber.py
        num_speakers: numero atteso di speaker (None = stima automatica 2-8)

    Returns:
        Lista segmenti arricchita con il campo 'speaker'.
    """
    if not segments:
        return segments

    audio_duration = _get_audio_duration(audio_path)
    if audio_duration < 1.0:
        logger.warning("Audio troppo corto per la diarizzazione; assegno Speaker_1 a tutto.")
        for s in segments:
            s["speaker"] = "Speaker_1"
        return segments

    # ── 1. Carica encoder e audio ─────────────────────────────────────────────
    logger.info("Caricamento VoiceEncoder (resemblyzer)...")
    encoder = VoiceEncoder(device="cpu")
    wav = preprocess_wav(audio_path)

    # ── 2. Embedding su finestre scorrevoli ───────────────────────────────────
    sr = 16000
    win_samples = int(WINDOW_SEC * sr)
    step_samples = int(STEP_SEC * sr)

    frame_times: list[float] = []
    frame_embeddings: list[np.ndarray] = []

    start = 0
    while start + win_samples <= len(wav):
        chunk = wav[start : start + win_samples]
        emb = encoder.embed_utterance(chunk)
        t_center = (start + win_samples / 2) / sr
        frame_times.append(t_center)
        frame_embeddings.append(emb)
        start += step_samples

    if len(frame_embeddings) < 2:
        logger.warning("Embedding insufficienti; assegno Speaker_1 a tutto.")
        for s in segments:
            s["speaker"] = "Speaker_1"
        return segments

    X = normalize(np.array(frame_embeddings))

    # ── 3. Stima numero speaker se non fornito ────────────────────────────────
    if num_speakers is None:
        num_speakers = _estimate_num_speakers(X)
    num_speakers = max(1, min(num_speakers, len(frame_embeddings)))
    logger.info(f"Speaker attesi: {num_speakers}")

    # ── 4. Clustering ─────────────────────────────────────────────────────────
    labels = _cluster(X, num_speakers)

    frame_times_arr = np.array(frame_times)

    # ── 5. Assegna speaker a ogni segmento Whisper ────────────────────────────
    for seg in segments:
        if (seg["end"] - seg["start"]) < MIN_SEGMENT_DURATION:
            # Segmento molto breve: prendi il frame più vicino
            t_mid = (seg["start"] + seg["end"]) / 2
            idx = int(np.argmin(np.abs(frame_times_arr - t_mid)))
            dominant = int(labels[idx])
        else:
            # Voto di maggioranza sui frame che cadono nel segmento
            mask = (frame_times_arr >= seg["start"]) & (frame_times_arr <= seg["end"])
            if mask.sum() == 0:
                t_mid = (seg["start"] + seg["end"]) / 2
                idx = int(np.argmin(np.abs(frame_times_arr - t_mid)))
                dominant = int(labels[idx])
            else:
                seg_labels = labels[mask]
                counts = np.bincount(seg_labels)
                dominant = int(np.argmax(counts))

        seg["speaker"] = f"Speaker_{dominant + 1}"

    logger.info("Diarizzazione completata.")
    return segments


# ── Funzioni di supporto ──────────────────────────────────────────────────────

def _get_audio_duration(audio_path: str) -> float:
    """Durata dell'audio in secondi (tramite resemblyzer/scipy)."""
    try:
        from scipy.io import wavfile
        sr, data = wavfile.read(audio_path)
        return len(data) / sr
    except Exception:
        return 0.0


def _cluster(X: np.ndarray, n_clusters: int) -> np.ndarray:
    """Esegue il clustering scegliendo la strategia in base al numero di campioni."""
    n_samples = len(X)

    if n_clusters == 1:
        return np.zeros(n_samples, dtype=int)

    # SpectralClustering funziona meglio su audio con speaker netti;
    # AgglomerativeClustering è più robusto per n_clusters alto o campioni scarsi.
    if n_samples >= n_clusters * 3 and n_samples >= 10:
        try:
            model = SpectralClustering(
                n_clusters=n_clusters,
                affinity="cosine",
                random_state=42,
                n_init=10,
            )
            return model.fit_predict(X)
        except Exception:
            pass

    model = AgglomerativeClustering(
        n_clusters=n_clusters,
        metric="cosine",
        linkage="average",
    )
    return model.fit_predict(X)


def _estimate_num_speakers(X: np.ndarray, max_speakers: int = 8) -> int:
    """
    Stima il numero di speaker tramite analisi degli eigenvalues della matrice
    di affinità coseno (Eigengap heuristic).
    """
    from sklearn.metrics.pairwise import cosine_similarity

    n = len(X)
    max_k = min(max_speakers, n - 1)
    if max_k < 2:
        return 1

    # Matrice di affinità (valori tra 0 e 1)
    A = cosine_similarity(X)
    A = np.clip(A, 0, 1)

    # Laplaciano normalizzato
    D = np.diag(A.sum(axis=1))
    with np.errstate(divide="ignore", invalid="ignore"):
        D_inv_sqrt = np.diag(1.0 / np.sqrt(np.diag(D) + 1e-10))
    L = np.eye(n) - D_inv_sqrt @ A @ D_inv_sqrt

    eigvals = np.sort(np.linalg.eigvalsh(L))

    # Massimo eigengap
    gaps = np.diff(eigvals[1 : max_k + 1])
    if len(gaps) == 0:
        return 1
    best_k = int(np.argmax(gaps)) + 2  # +2: indice base 1 + skip primo eigenv.
    best_k = max(1, min(best_k, max_k))
    logger.info(f"Numero speaker stimato (eigengap): {best_k}")
    return best_k
