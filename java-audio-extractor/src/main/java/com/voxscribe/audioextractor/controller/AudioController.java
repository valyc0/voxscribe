package com.voxscribe.audioextractor.controller;

import com.voxscribe.audioextractor.dto.ExtractResponse;
import com.voxscribe.audioextractor.service.AudioExtractService;
import jakarta.validation.constraints.NotBlank;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/audio")
@Validated
public class AudioController {

    private static final Logger log = LoggerFactory.getLogger(AudioController.class);

    private final AudioExtractService service;

    public AudioController(AudioExtractService service) {
        this.service = service;
    }

    /**
     * Estrae l'audio MP3 dal video specificato.
     * ffmpeg legge il video in streaming (adatto a file di grandi dimensioni).
     * Il file MP3 viene scritto su disco solo a fine elaborazione.
     *
     * Esempio:
     *   curl -X POST "http://localhost:8081/api/audio/extract?filename=film.mp4"
     */
    @PostMapping("/extract")
    public ResponseEntity<ExtractResponse> extract(@RequestParam @NotBlank String filename)
            throws IOException {
        String outputFile = service.extractAudio(filename);
        return ResponseEntity.ok(new ExtractResponse("ok", filename, outputFile, null));
    }

    /** Elenca i file video presenti nella directory configurata. */
    @GetMapping("/files")
    public ResponseEntity<Map<String, Object>> listFiles() throws IOException {
        List<String> files = service.listVideoFiles();
        return ResponseEntity.ok(Map.of("count", files.size(), "files", files));
    }

    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "ok"));
    }

    @ExceptionHandler({IllegalArgumentException.class, SecurityException.class})
    public ResponseEntity<ExtractResponse> handleBadRequest(RuntimeException ex) {
        log.warn("Richiesta non valida: {}", ex.getMessage());
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(new ExtractResponse("error", null, null, ex.getMessage()));
    }

    @ExceptionHandler(IOException.class)
    public ResponseEntity<ExtractResponse> handleIo(IOException ex) {
        log.error("Errore I/O: {}", ex.getMessage(), ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ExtractResponse("error", null, null, ex.getMessage()));
    }
}
