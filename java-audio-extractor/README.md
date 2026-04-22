# audio-extractor

Microservizio Spring Boot 3 che espone una REST API per estrarre la traccia audio da un file video e salvarla come MP3.

## Come funziona

1. Il file video viene letto **in streaming** chunk per chunk (64 KB) tramite `InputStream` — nessun caricamento completo in RAM, adatto a file di grandi dimensioni
2. **JavaCV** (FFmpeg bundled, nessun binario di sistema richiesto) decodifica i frame audio con `FFmpegFrameGrabber`
3. `FFmpegFrameRecorder` codifica i frame in MP3 e li accumula in un `ByteArrayOutputStream` in memoria
4. Solo a elaborazione **completata con successo** l'MP3 viene scritto su disco nella stessa directory del video

> Evoluzione futura: sostituire l'`InputStream` del file locale con quello di una risposta HTTP per inviare l'audio direttamente a un'API esterna.

## Requisiti

- Java 21+
- Maven 3.8+
- Nessun `ffmpeg` di sistema (le librerie native sono bundled via `ffmpeg-platform`)

## Configurazione

`src/main/resources/application.yml`:

```yaml
audio-extractor:
  video-dir: /tmp/videos   # directory contenente i file video
  ffmpeg-path: ffmpeg       # ignorato (si usa JavaCV)
  audio-bitrate: 192        # bitrate MP3 in kbps
```

La directory può essere impostata anche tramite variabile d'ambiente:

```bash
AUDIO_EXTRACTOR_VIDEO_DIR=/mnt/videos ./start.sh
```

## Avvio

```bash
./start.sh
```

Al primo avvio Maven scarica le librerie native FFmpeg (~150 MB).

## API

### `POST /api/audio/extract?filename=<nome_file>`

Estrae l'audio dal video e lo salva come MP3 nella stessa directory.

**Risposta:**
```json
{
  "status": "ok",
  "inputFile": "film.mp4",
  "outputFile": "film.mp3",
  "message": null
}
```

### `GET /api/audio/files`

Elenca i file video presenti nella directory configurata.

```json
{
  "count": 2,
  "files": ["film.mp4", "videoplayback.mp4"]
}
```

### `GET /api/audio/health`

Liveness probe.

## Script di test

```bash
# lista file video disponibili
./test-api.sh list

# estrai audio da un video
./test-api.sh extract film.mp4
```

## Formati video supportati

`mp4`, `mkv`, `avi`, `mov`, `wmv`, `flv`, `webm`, `m4v`, `ts`, `mpeg`, `mpg`
