import os
import uuid
import tempfile
import shutil
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from transcriber import transcribe_audio
from diarizer import diarize_audio
from audio_utils import extract_audio

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Video Transcription & Speaker Diarization API",
    description="Trascrive video e identifica gli interlocutori senza token esterni",
    version="1.0.0",
)

UPLOAD_DIR = "/tmp/video_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/transcribe")
async def transcribe_video(
    file: UploadFile = File(...),
    language: str = "it",
    model_size: str = "small",
    num_speakers: int = None,
):
    """
    Riceve un video (qualsiasi formato supportato da ffmpeg), lo trascrive
    e identifica gli interlocutori.

    Parametri:
    - file: il file video
    - language: codice lingua (default 'it'). Usa 'auto' per rilevamento automatico.
    - model_size: dimensione modello Whisper (tiny, base, small, medium, large)
    - num_speakers: numero atteso di interlocutori (None = auto-detection)

    Esempio curl:
      curl -X POST http://localhost:8000/transcribe \
           -F "file=@video.mp4" \
           -F "language=it" \
           -F "model_size=base"
    """
    job_id = str(uuid.uuid4())
    tmp_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        # 1. Salva il file caricato
        video_path = os.path.join(tmp_dir, f"input{os.path.splitext(file.filename or 'video.mp4')[1]}")
        logger.info(f"[{job_id}] Salvataggio file: {file.filename}")
        with open(video_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # 2. Estrai audio in WAV mono 16kHz
        audio_path = os.path.join(tmp_dir, "audio.wav")
        logger.info(f"[{job_id}] Estrazione audio...")
        extract_audio(video_path, audio_path)

        # 3. Trascrizione con Whisper (restituisce segmenti con timestamp)
        lang = None if language == "auto" else language
        logger.info(f"[{job_id}] Trascrizione (modello={model_size}, lingua={lang or 'auto'})...")
        segments = transcribe_audio(audio_path, model_size=model_size, language=lang)

        # 4. Diarizzazione speaker
        logger.info(f"[{job_id}] Diarizzazione speaker...")
        segments_with_speakers = diarize_audio(audio_path, segments, num_speakers=num_speakers)

        # 5. Costruisci risposta JSON
        result = build_response(segments_with_speakers)
        logger.info(f"[{job_id}] Completato. Speaker trovati: {len(result['speakers'])}")
        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"[{job_id}] Errore: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def build_response(segments: list) -> dict:
    """Costruisce il JSON finale con trascrizione completa e info sugli interlocutori."""
    full_text = " ".join(s["text"].strip() for s in segments if s.get("text"))

    # Raggruppa per speaker
    speaker_stats: dict = {}
    for seg in segments:
        sp = seg.get("speaker", "Speaker_?")
        if sp not in speaker_stats:
            speaker_stats[sp] = {"total_segments": 0, "total_duration_sec": 0.0, "lines": []}
        duration = seg["end"] - seg["start"]
        speaker_stats[sp]["total_segments"] += 1
        speaker_stats[sp]["total_duration_sec"] = round(
            speaker_stats[sp]["total_duration_sec"] + duration, 2
        )
        speaker_stats[sp]["lines"].append(seg["text"].strip())

    # Trascrizione dialogica (Speaker: testo)
    dialogue_lines = []
    prev_speaker = None
    for seg in segments:
        sp = seg.get("speaker", "Speaker_?")
        text = seg["text"].strip()
        if sp != prev_speaker:
            dialogue_lines.append(f"\n{sp}: {text}")
            prev_speaker = sp
        else:
            dialogue_lines[-1] += f" {text}"

    return {
        "job_id": None,
        "transcription": full_text,
        "dialogue": "\n".join(dialogue_lines).strip(),
        "speakers": sorted(speaker_stats.keys()),
        "speaker_details": {
            sp: {
                "total_segments": v["total_segments"],
                "total_duration_sec": v["total_duration_sec"],
            }
            for sp, v in speaker_stats.items()
        },
        "segments": [
            {
                "start": round(s["start"], 2),
                "end": round(s["end"], 2),
                "speaker": s.get("speaker", "Speaker_?"),
                "text": s["text"].strip(),
            }
            for s in segments
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
