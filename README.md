# Voxscribe

> Trascrizione automatica di video e identificazione degli interlocutori via API REST.
> Nessun token, nessun servizio esterno — gira tutto in locale o in Docker.

---

## Cosa fa

Invii un video con `curl`, ricevi un JSON con:

- **trascrizione completa** del parlato
- **dialogo formattato** per speaker (`Speaker_1: ...`, `Speaker_2: ...`)
- **lista degli interlocutori** rilevati automaticamente
- **segmenti** con timestamp di inizio/fine e speaker assegnato

---

## Architettura

```
video (curl)
     │
     ▼
  FastAPI
     │
     ├── ffmpeg ──────────────► WAV mono 16kHz
     │
     ├── Whisper (open-source) ► segmenti + timestamp
     │
     └── resemblyzer + sklearn ► speaker per segmento
                                        │
                                        ▼
                                   risposta JSON
```

---

## Avvio

```bash
./start.sh
```

Fa tutto in automatico: build Docker, avvio container, polling health check.
L'API è pronta su `http://localhost:8000`.

---

## Utilizzo

### Trascrizione base
```bash
curl -X POST http://localhost:8000/transcribe \
     -F "file=@video.mp4"
```

### Specificare lingua e modello
```bash
curl -X POST http://localhost:8000/transcribe \
     -F "file=@video.mp4" \
     -F "language=it" \
     -F "model_size=small"
```

### Forzare numero di interlocutori
```bash
curl -X POST http://localhost:8000/transcribe \
     -F "file=@intervista.mp4" \
     -F "language=it" \
     -F "num_speakers=2"
```

### Rilevamento automatico lingua
```bash
curl -X POST http://localhost:8000/transcribe \
     -F "file=@video.mp4" \
     -F "language=auto"
```

### Salvare il risultato su file
```bash
curl -X POST http://localhost:8000/transcribe \
     -F "file=@video.mp4" \
     -o risultato.json
```

### Lanciare tutti i test
```bash
./test.sh video.mp4
```

---

## Parametri endpoint `POST /transcribe`

| Parametro      | Default  | Descrizione |
|----------------|----------|-------------|
| `file`         | —        | File video (mp4, mkv, avi, mov, …) |
| `language`     | `it`     | Codice lingua ISO 639-1 oppure `auto` |
| `model_size`   | `small`  | Modello Whisper: `tiny` `base` `small` `medium` `large` |
| `num_speakers` | `null`   | Numero interlocutori attesi (null = rilevamento automatico) |

---

## Risposta JSON

```json
{
  "transcription": "Testo completo del parlato...",
  "dialogue": "Speaker_1: Prima battuta\n\nSpeaker_2: Risposta\n\nSpeaker_1: ...",
  "speakers": ["Speaker_1", "Speaker_2"],
  "speaker_details": {
    "Speaker_1": { "total_segments": 26, "total_duration_sec": 96.8 },
    "Speaker_2": { "total_segments": 9,  "total_duration_sec": 26.5 }
  },
  "segments": [
    { "start": 0.0,  "end": 1.3,  "speaker": "Speaker_1", "text": "Prima frase." },
    { "start": 1.5,  "end": 4.2,  "speaker": "Speaker_2", "text": "Seconda frase." }
  ]
}
```

---

## Modelli Whisper — guida alla scelta

| Modello  | RAM      | Qualità     | Velocità (CPU) |
|----------|----------|-------------|----------------|
| `tiny`   | ~1 GB    | bassa       | molto veloce   |
| `base`   | ~1 GB    | discreta    | veloce         |
| `small`  | ~2 GB    | **buona** ✓ | media          |
| `medium` | ~5 GB    | ottima      | lenta          |
| `large`  | ~10 GB   | massima     | molto lenta    |

Default: `small` — ottimo compromesso per italiano su CPU.

---

## Struttura del progetto

```
voxscribe/
├── app.py              # Server FastAPI
├── transcriber.py      # Trascrizione Whisper
├── diarizer.py         # Diarizzazione speaker (resemblyzer + sklearn)
├── audio_utils.py      # Estrazione audio via ffmpeg
├── requirements.txt    # Dipendenze Python
├── Dockerfile          # Build immagine Docker
├── docker-compose.yml  # Orchestrazione container
├── start.sh            # Avvio one-shot
├── test.sh             # Test curl automatici
└── backup.sh           # Backup sorgenti con timestamp
```

---

## Dipendenze — nessun token richiesto

| Libreria         | Scopo                              |
|------------------|------------------------------------|
| `openai-whisper` | Trascrizione ASR (modelli pubblici)|
| `resemblyzer`    | Embedding vocali per diarizzazione |
| `scikit-learn`   | Clustering speaker                 |
| `fastapi`        | API HTTP                           |
| `ffmpeg`         | Estrazione audio da video          |

I modelli vengono scaricati automaticamente da GitHub Releases durante il build Docker.

---

## Backup sorgenti

```bash
./backup.sh
# crea ../backup_YYYYMMDD_HHMMSS.tar.gz
```
