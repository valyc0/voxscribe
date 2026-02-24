"""
Utilità per l'estrazione audio da file video tramite ffmpeg.
ffmpeg è un binario di sistema — nessuna libreria con token richiesta.
"""

import subprocess
import logging
import shutil

logger = logging.getLogger(__name__)


def extract_audio(video_path: str, output_wav: str) -> None:
    """
    Estrae la traccia audio da un video e la salva come WAV mono 16kHz.
    Requisito: ffmpeg installato nel PATH (o nel container).

    Args:
        video_path : percorso del file video sorgente
        output_wav : percorso destinazione del file WAV
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        raise EnvironmentError(
            "ffmpeg non trovato nel PATH. "
            "Installalo con: apt-get install ffmpeg oppure usa il Dockerfile fornito."
        )

    cmd = [
        ffmpeg_bin,
        "-y",                   # sovrascrive output se esiste
        "-i", video_path,       # input
        "-vn",                  # nessun video in output
        "-acodec", "pcm_s16le", # PCM 16-bit LE (WAV nativo)
        "-ar", "16000",         # 16 kHz (richiesto da Whisper e resemblyzer)
        "-ac", "1",             # mono
        output_wav,
    ]

    logger.info(f"ffmpeg: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg ha restituito codice {result.returncode}.\n"
            f"stderr: {result.stderr}"
        )

    logger.info(f"Audio estratto: {output_wav}")
