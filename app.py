"""
VoxScribe – API asincrona di trascrizione e diarizzazione.

Flusso:
  POST /transcribe          → calcola checksum, avvia job in background, ritorna job_id
  GET  /status/{job_id}     → stato del job (pending | processing | done | error)
  GET  /result/{job_id}     → JSON finale (solo quando status=done)
  GET  /health              → liveness probe

Deduplicazione automatica:
  - stesso file già in lavorazione → restituisce job_id e stato
  - stesso file già elaborato      → restituisce job_id per scaricare il risultato

Persistenza:
  I risultati sono salvati in RESULTS_DIR/{checksum}/{checksum}.json
  In memoria si tengono al massimo MAX_JOBS entry (FIFO); il registro in RAM
  viene anche reidratato al boot leggendo i file già presenti su disco.
"""

import os
import hashlib
import shutil
import logging
import json
import asyncio
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import pathlib
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import Response, HTMLResponse

from transcriber import transcribe_audio
from diarizer import diarize_audio
from audio_utils import extract_audio

# ──────────────────────────────────────────────────────────────────────────────
# Configurazione
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

WORK_DIR = os.environ.get("VOXSCRIBE_WORK_DIR", "/tmp/voxscribe_work")
RESULTS_DIR = os.environ.get("VOXSCRIBE_RESULTS_DIR", "/data/voxscribe_results")
MAX_JOBS = int(os.environ.get("VOXSCRIBE_MAX_JOBS", "1000"))
MAX_WORKERS = int(os.environ.get("VOXSCRIBE_MAX_WORKERS", "2"))

os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# Pool di thread per il lavoro CPU-bound (trascrizione + diarizzazione)
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# ──────────────────────────────────────────────────────────────────────────────
# Registro job in memoria  (OrderedDict → FIFO facile)
# key  : checksum (SHA-256, 64 hex chars → usato come job_id)
# value: dict con campi status, created_at, params, error
# ──────────────────────────────────────────────────────────────────────────────

_jobs: OrderedDict = OrderedDict()
_jobs_lock = threading.Lock()   # lock normale (usato anche dai thread worker)


def _register_job(checksum: str, params: dict) -> None:
    """Aggiunge il job al registro e, se serve, evicts il più vecchio (FIFO)."""
    with _jobs_lock:
        if checksum in _jobs:
            # sposta in fondo (MRU touch) così non verrà evicted subito
            _jobs.move_to_end(checksum)
            return
        _jobs[checksum] = {
            "job_id": checksum,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "elapsed_sec": None,
            "filename": params.get("filename"),
            "params": params,
            "error": None,
        }
        # FIFO eviction
        while len(_jobs) > MAX_JOBS:
            evicted_key, _ = _jobs.popitem(last=False)
            logger.info(f"[registry] Evicted job {evicted_key} (FIFO, max={MAX_JOBS})")


def _update_job(checksum: str, **kwargs) -> None:
    with _jobs_lock:
        if checksum in _jobs:
            _jobs[checksum].update(kwargs)


def _get_job(checksum: str) -> Optional[dict]:
    with _jobs_lock:
        return dict(_jobs[checksum]) if checksum in _jobs else None


def _result_path(checksum: str) -> str:
    return os.path.join(RESULTS_DIR, checksum, f"{checksum}.json")


def _result_exists(checksum: str) -> bool:
    return os.path.isfile(_result_path(checksum))


# ──────────────────────────────────────────────────────────────────────────────
# Reidratazione al boot: scopre risultati già a disco
# ──────────────────────────────────────────────────────────────────────────────

def _boot_rehydrate() -> None:
    count = 0
    if not os.path.isdir(RESULTS_DIR):
        return
    for entry in os.scandir(RESULTS_DIR):
        if not entry.is_dir():
            continue
        checksum = entry.name
        rpath = os.path.join(entry.path, f"{checksum}.json")
        if os.path.isfile(rpath):
            mtime = datetime.fromtimestamp(os.path.getmtime(rpath), tz=timezone.utc).isoformat()
            with _jobs_lock:
                if len(_jobs) >= MAX_JOBS:
                    break
                # try to read filename from the persisted JSON
                _filename = None
                try:
                    with open(rpath, "r", encoding="utf-8") as _f:
                        _d = json.load(_f)
                    _filename = _d.get("filename")
                except Exception:
                    pass
                _jobs[checksum] = {
                    "job_id": checksum,
                    "status": "done",
                    "created_at": mtime,
                    "started_at": None,
                    "completed_at": mtime,
                    "elapsed_sec": None,
                    "filename": _filename,
                    "params": {},
                    "error": None,
                }
            count += 1
    if count:
        logger.info(f"[boot] Reidratati {count} job da disco.")


_boot_rehydrate()

# ──────────────────────────────────────────────────────────────────────────────
# FastAPI
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="VoxScribe – Async Transcription & Diarization API",
    description=(
        "Carica un media, ricevi subito un job_id, "
        "interroga lo stato e scarica il risultato quando pronto."
    ),
    version="2.0.0",
)


# ──────────────────────────────────────────────────────────────────────────────
# Worker (gira in ThreadPoolExecutor)
# ──────────────────────────────────────────────────────────────────────────────

def _process_job(
    checksum: str,
    video_path: str,
    language: Optional[str],
    model_size: str,
    num_speakers: Optional[int],
    filename: Optional[str] = None,
) -> None:
    """Elaborazione sincrona eseguita in un thread del pool."""
    tmp_dir = os.path.join(WORK_DIR, checksum)
    os.makedirs(tmp_dir, exist_ok=True)
    try:
        t_start = datetime.now(timezone.utc)
        _update_job(checksum, status="processing", started_at=t_start.isoformat())
        logger.info(f"[{checksum[:12]}] Inizio elaborazione.")

        # 1. Estrai audio WAV 16kHz mono
        audio_path = os.path.join(tmp_dir, "audio.wav")
        logger.info(f"[{checksum[:12]}] Estrazione audio...")
        extract_audio(video_path, audio_path)

        # 2. Trascrizione Whisper
        logger.info(f"[{checksum[:12]}] Trascrizione (modello={model_size}, lingua={language or 'auto'})...")
        segments = transcribe_audio(audio_path, model_size=model_size, language=language)

        # 3. Diarizzazione speaker
        logger.info(f"[{checksum[:12]}] Diarizzazione speaker...")
        segments_with_speakers = diarize_audio(audio_path, segments, num_speakers=num_speakers)

        # 4. Costruisci risultato
        result = _build_response(checksum, segments_with_speakers, filename=filename)

        # 5. Persisti su disco
        out_dir = os.path.join(RESULTS_DIR, checksum)
        os.makedirs(out_dir, exist_ok=True)
        out_path = _result_path(checksum)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)

        t_end = datetime.now(timezone.utc)
        elapsed = round((t_end - t_start).total_seconds(), 1)
        _update_job(checksum, status="done", completed_at=t_end.isoformat(), elapsed_sec=elapsed)
        logger.info(f"[{checksum[:12]}] Completato in {elapsed}s. Risultato in {out_path}")

    except Exception as exc:
        logger.error(f"[{checksum[:12]}] Errore: {exc}", exc_info=True)
        _update_job(checksum, status="error", error=str(exc))

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        # rimuovi anche il file originale caricato (non l'audio estratto, già in tmp_dir)
        if os.path.isfile(video_path):
            os.remove(video_path)


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui():
    html = (pathlib.Path(__file__).parent / "client-web" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/health")
async def health():
    with _jobs_lock:
        total = len(_jobs)
    return {"status": "ok", "jobs_in_memory": total}


@app.post("/transcribe", status_code=202)
async def transcribe_video(
    file: UploadFile = File(...),
    language: str = "it",
    model_size: str = "small",
    num_speakers: int = None,
):
    """
    Accetta un file media (qualsiasi formato supportato da ffmpeg).
    Ritorna immediatamente con http 202 e un job_id (checksum SHA-256 del file).

    Deduplicazione automatica:
    - se il file è già in lavorazione restituisce status=processing
    - se il file è già stato elaborato restituisce status=done con hint al download

    Parametri:
    - language   : codice lingua ISO 639-1 (default 'it'). Usa 'auto' per auto-detect.
    - model_size : tiny | base | small | medium | large (default 'small')
    - num_speakers: numero atteso di speaker (None = auto-detect)

    Esempio:
      curl -X POST http://localhost:8000/transcribe \\
           -F "file=@video.mp4" -F "language=it" -F "model_size=small"
    """
    # 1. Leggi e calcola checksum in streaming (non caricare tutto in RAM)
    sha = hashlib.sha256()
    chunks = []
    while True:
        chunk = await file.read(1 << 20)   # 1 MB alla volta
        if not chunk:
            break
        sha.update(chunk)
        chunks.append(chunk)
    checksum = sha.hexdigest()

    # 2. Controlla stato in memoria
    existing = _get_job(checksum)
    if existing:
        status = existing["status"]
        if status == "processing" or status == "pending":
            return Response(
                content=json.dumps({
                    "job_id": checksum,
                    "status": status,
                    "message": "File già in lavorazione.",
                    "status_url": f"/status/{checksum}",
                }, ensure_ascii=False),
                status_code=202,
                media_type="application/json",
            )
        if status == "done":
            return Response(
                content=json.dumps({
                    "job_id": checksum,
                    "status": "done",
                    "message": "File già elaborato in precedenza.",
                    "result_url": f"/result/{checksum}",
                }, ensure_ascii=False),
                status_code=200,
                media_type="application/json",
            )
        # status == "error": ri-accoda

    # 3. Controlla se il risultato esiste già su disco (dopo un riavvio)
    if _result_exists(checksum):
        _register_job(checksum, {})
        _update_job(checksum, status="done")
        return Response(
            content=json.dumps({
                "job_id": checksum,
                "status": "done",
                "message": "Risultato già presente su disco.",
                "result_url": f"/result/{checksum}",
            }, ensure_ascii=False),
            status_code=200,
            media_type="application/json",
        )

    # 4. Salva il file su disco (in una posizione fuori da tmp_dir che verrà pulita)
    upload_path = os.path.join(WORK_DIR, f"{checksum}_upload{os.path.splitext(file.filename or '.bin')[1]}")
    with open(upload_path, "wb") as fh:
        for c in chunks:
            fh.write(c)

    # 5. Registra il job e avvia il worker
    original_filename = file.filename or "unknown"
    params = {"language": language, "model_size": model_size, "num_speakers": num_speakers, "filename": original_filename}
    _register_job(checksum, params)
    lang = None if language == "auto" else language

    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _executor,
        _process_job,
        checksum,
        upload_path,
        lang,
        model_size,
        num_speakers,
        original_filename,
    )

    logger.info(f"[{checksum[:12]}] Job registrato. File: {file.filename}")
    return Response(
        content=json.dumps({
            "job_id": checksum,
            "status": "pending",
            "message": "Elaborazione avviata.",
            "status_url": f"/status/{checksum}",
            "result_url": f"/result/{checksum}",
        }, ensure_ascii=False),
        status_code=202,
        media_type="application/json",
    )


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """
    Restituisce lo stato del job.

    Possibili valori di status: pending | processing | done | error
    """
    job = _get_job(job_id)
    if job is None:
        # prova a verificare se il risultato esiste comunque su disco
        if _result_exists(job_id):
            return {"job_id": job_id, "status": "done", "result_url": f"/result/{job_id}"}
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' non trovato.")

    resp = {
        "job_id": job["job_id"],
        "status": job["status"],
        "filename": job.get("filename"),
        "created_at": job["created_at"],
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "elapsed_sec": job.get("elapsed_sec"),
    }
    if job["status"] == "done":
        resp["result_url"] = f"/result/{job_id}"
    if job["status"] == "error":
        resp["error"] = job.get("error")
    return resp


@app.get("/result/{job_id}")
async def get_result(job_id: str):
    """
    Restituisce il JSON completo della trascrizione/diarizzazione.
    Disponibile solo quando status=done.
    """
    rpath = _result_path(job_id)
    if not os.path.isfile(rpath):
        job = _get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' non trovato.")
        status = job["status"]
        if status in ("pending", "processing"):
            raise HTTPException(status_code=202, detail=f"Job ancora in corso (status={status}).")
        if status == "error":
            raise HTTPException(status_code=500, detail=f"Job terminato con errore: {job.get('error')}")
        raise HTTPException(status_code=404, detail="Risultato non trovato su disco.")

    with open(rpath, "r", encoding="utf-8") as fh:
        content = fh.read()
    return Response(content=content, media_type="application/json")


@app.get("/jobs")
async def list_jobs(limit: int = 50):
    """
    Elenca gli ultimi `limit` job presenti in memoria (ordine FIFO inverso = più recenti prima).
    """
    with _jobs_lock:
        items = list(_jobs.values())
    items.reverse()
    return {"total_in_memory": len(items), "jobs": items[:limit]}


@app.delete("/results", status_code=200)
async def delete_all_results():
    """
    Cancella tutti i risultati dal disco e azzera il registro in memoria.
    I job attualmente in elaborazione (pending/processing) vengono saltati.
    """
    # Individua i job attivi da non toccare
    with _jobs_lock:
        active = {k for k, v in _jobs.items() if v["status"] in ("pending", "processing")}

    deleted_files = 0
    skipped_active = 0
    errors = []

    if os.path.isdir(RESULTS_DIR):
        for entry in os.scandir(RESULTS_DIR):
            if not entry.is_dir():
                continue
            checksum = entry.name
            if checksum in active:
                skipped_active += 1
                continue
            try:
                shutil.rmtree(entry.path)
                deleted_files += 1
            except Exception as exc:
                errors.append(f"{checksum[:12]}: {exc}")

    # Rimuovi dalla cache in memoria tutto tranne i job attivi
    with _jobs_lock:
        to_remove = [k for k in _jobs if k not in active]
        for k in to_remove:
            del _jobs[k]

    logger.info(f"[delete_all_results] Eliminati {deleted_files} risultati, saltati {skipped_active} attivi.")
    return {
        "deleted": deleted_files,
        "skipped_active": skipped_active,
        "jobs_in_memory_remaining": len(active),
        "errors": errors,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_response(checksum: str, segments: list, filename: Optional[str] = None) -> dict:
    """Costruisce il JSON finale con trascrizione completa e info sugli interlocutori."""
    full_text = " ".join(s["text"].strip() for s in segments if s.get("text"))

    speaker_stats: dict = {}
    for seg in segments:
        sp = seg.get("speaker", "Speaker_?")
        if sp not in speaker_stats:
            speaker_stats[sp] = {"total_segments": 0, "total_duration_sec": 0.0}
        duration = seg["end"] - seg["start"]
        speaker_stats[sp]["total_segments"] += 1
        speaker_stats[sp]["total_duration_sec"] = round(
            speaker_stats[sp]["total_duration_sec"] + duration, 2
        )

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
        "job_id": checksum,
        "filename": filename,
        "transcription": full_text,
        "dialogue": "\n".join(dialogue_lines).strip(),
        "speakers": sorted(speaker_stats.keys()),
        "speaker_details": speaker_stats,
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
