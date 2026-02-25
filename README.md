# VoxScribe

> Trascrizione automatica di video e identificazione degli interlocutori via API REST **asincrona**.
> Interfaccia web responsive inclusa. Nessun token, nessun servizio esterno — gira tutto in locale o in Docker.

---

## Cosa fa

Invii un file media con `curl` e ricevi **subito** un `job_id`.  
L'elaborazione prosegue in background; puoi interrogare lo stato e, una volta completata, scaricare il JSON con:

- **trascrizione completa** del parlato
- **dialogo formattato** per speaker (`Speaker_1: ...`, `Speaker_2: ...`)
- **lista degli interlocutori** rilevati automaticamente
- **segmenti** con timestamp di inizio/fine e speaker assegnato

### Deduplicazione automatica
Il `job_id` corrisponde al checksum SHA-256 del file caricato.

| Situazione | Comportamento |
|---|---|
| File già in elaborazione (pending/processing) | HTTP 202, message = "File già in lavorazione" |
| File già elaborato (sul disco o in memoria) | HTTP 200, message = "File già elaborato", link al risultato |
| File nuovo | HTTP 202, elaborazione avviata |

---

## Architettura

```
POST /transcribe (curl)
     │  risposta immediata HTTP 202 + job_id
     │
     ▼
  FastAPI ──► ThreadPoolExecutor (background)
                    │
                    ├── ffmpeg ──────────────► WAV mono 16kHz
                    ├── Whisper ─────────────► segmenti + timestamp
                    └── resemblyzer + sklearn ► speaker per segmento
                                                      │
                                                      ▼
                                          /data/voxscribe_results/
                                          └── {sha256}/
                                              └── {sha256}.json
```

Il registro in memoria tiene al massimo **1000 job** (FIFO); i risultati su disco persistono oltre il registro RAM.

---

## Web UI

Una volta avviato il server, apri nel browser (desktop o smartphone):

```
http://localhost:8000/
```

Funzionalità:
- **Drag & drop** o selezione file (video e audio, qualsiasi formato ffmpeg)
- Selezione lingua, modello Whisper e numero di speaker
- **Progress bar** durante l'upload
- **Polling automatico** dello stato del job ogni 5 secondi
- Visualizzazione risultato in tre tab: **Dialogo** · **Testo completo** · **Segmenti con timestamp**
- **Deduplicazione** automatica: se carichi lo stesso file già elaborato viene mostrato subito il risultato
- Pulsante **Scarica JSON** per salvare il risultato completo
- Completamente **responsive** — funziona su smartphone e tablet

---

## Avvio

```bash
./start.sh
```

Build Docker, avvio container, polling health check.  
API pronta su `http://localhost:8000`.

### Variabili d'ambiente (opzionali)

| Variabile | Default | Descrizione |
|---|---|---|
| `VOXSCRIBE_RESULTS_DIR` | `/data/voxscribe_results` | Directory risultati persistenti |
| `VOXSCRIBE_WORK_DIR` | `/tmp/voxscribe_work` | Directory di lavoro temporanea |
| `VOXSCRIBE_MAX_JOBS` | `1000` | Max job in memoria (FIFO) |
| `VOXSCRIBE_MAX_WORKERS` | `2` | Thread concorrenti nel pool |

---

## Utilizzo

### 1 — Invia il file, ottieni il job_id

```bash
JOB=$(curl -s -X POST http://localhost:8000/transcribe \
     -F "file=@video.mp4" \
     -F "language=it" \
     -F "model_size=small" | jq -r .job_id)
echo "job_id: $JOB"
```

Risposta immediata (HTTP 202):
```json
{
  "job_id": "a3f84c...",
  "status": "pending",
  "message": "Elaborazione avviata.",
  "status_url": "/status/a3f84c...",
  "result_url": "/result/a3f84c..."
}
```

### 2 — Interroga lo stato

```bash
curl http://localhost:8000/status/$JOB
```

```json
{ "job_id": "a3f84c...", "status": "processing", "created_at": "2026-02-25T10:00:00+00:00" }
```

Possibili valori di `status`: `pending` · `processing` · `done` · `error`

### 3 — Scarica il risultato (quando status=done)

```bash
curl http://localhost:8000/result/$JOB -o risultato.json
```

### Esempio completo con polling

```bash
JOB=$(curl -s -X POST http://localhost:8000/transcribe \
     -F "file=@video.mp4" | jq -r .job_id)

while true; do
  STATUS=$(curl -s http://localhost:8000/status/$JOB | jq -r .status)
  echo "stato: $STATUS"
  [[ "$STATUS" == "done" || "$STATUS" == "error" ]] && break
  sleep 5
done

curl -s http://localhost:8000/result/$JOB | jq .dialogue
```

### Forzare numero di interlocutori

```bash
curl -X POST http://localhost:8000/transcribe \
     -F "file=@intervista.mp4" \
     -F "num_speakers=2"
```

### Lista job in memoria

```bash
curl http://localhost:8000/jobs?limit=20
```

---

## Endpoints

| Metodo | Path | Descrizione |
|---|---|---|
| `GET` | `/` | Web UI (browser) |
| `POST` | `/transcribe` | Carica file, avvia elaborazione asincrona |
| `GET` | `/status/{job_id}` | Stato del job |
| `GET` | `/result/{job_id}` | JSON risultato (solo se done) |
| `GET` | `/jobs` | Lista job in memoria (`?limit=N`) |
| `GET` | `/health` | Liveness probe |

### Parametri `POST /transcribe`

| Parametro | Default | Descrizione |
|---|---|---|
| `file` | — | File media (mp4, mkv, avi, mov, mp3, wav, …) |
| `language` | `it` | Codice lingua ISO 639-1 oppure `auto` |
| `model_size` | `small` | `tiny` · `base` · `small` · `medium` · `large` |
| `num_speakers` | `null` | Numero interlocutori attesi (null = auto) |

---

## Struttura risultato JSON

```json
{
  "job_id": "a3f84c...",
  "filename": "video.mp4",
  "transcription": "Testo completo del parlato...",
  "dialogue": "Speaker_1: Prima battuta\n\nSpeaker_2: Risposta",
  "speakers": ["Speaker_1", "Speaker_2"],
  "speaker_details": {
    "Speaker_1": { "total_segments": 26, "total_duration_sec": 96.8 },
    "Speaker_2": { "total_segments": 9,  "total_duration_sec": 26.5 }
  },
  "segments": [
    { "start": 0.0, "end": 1.3, "speaker": "Speaker_1", "text": "Prima frase." }
  ]
}
```

---

## Persistenza risultati

I file JSON sono salvati in `VOXSCRIBE_RESULTS_DIR/{sha256}/{sha256}.json`.  
Al riavvio del server il registro in memoria viene reidratato dai file presenti su disco (fino a `MAX_JOBS` entry).

---

## Modelli Whisper — guida alla scelta

| Modello | RAM | Qualità | Velocità (CPU) |
|---|---|---|---|
| `tiny` | ~1 GB | bassa | molto veloce |
| `base` | ~1 GB | discreta | veloce |
| `small` | ~2 GB | **buona** ✓ | media |
| `medium` | ~5 GB | ottima | lenta |
| `large` | ~10 GB | massima | molto lenta |

---

## Struttura del progetto

```
voxscribe/
├── app.py              # Server FastAPI (async, job registry, dedup)
├── transcriber.py      # Trascrizione Whisper
├── diarizer.py         # Diarizzazione speaker (resemblyzer + sklearn)
├── audio_utils.py      # Estrazione audio via ffmpeg
├── client-web/
│   └── index.html      # Web UI responsive (servita da FastAPI su GET /)
├── voxscribe_results/  # Risultati JSON persistenti (bind mount Docker)
├── requirements.txt    # Dipendenze Python
├── Dockerfile          # Build immagine Docker
├── docker-compose.yml  # Orchestrazione container
├── start.sh            # Avvio one-shot
├── test.sh             # Test curl automatici (async-aware)
└── backup.sh           # Backup sorgenti con timestamp
```

---

## Backup sorgenti

```bash
./backup.sh
# crea ../backup_YYYYMMDD_HHMMSS.tar.gz
```
