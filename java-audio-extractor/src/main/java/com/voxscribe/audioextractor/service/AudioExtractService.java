package com.voxscribe.audioextractor.service;

import com.voxscribe.audioextractor.config.AudioExtractorConfig;
import org.bytedeco.javacv.FFmpegFrameGrabber;
import org.bytedeco.javacv.FFmpegFrameRecorder;
import org.bytedeco.javacv.Frame;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.stream.Stream;

import static org.bytedeco.ffmpeg.global.avcodec.AV_CODEC_ID_MP3;

/**
 * Estrae l'audio da un file video usando JavaCV (FFmpeg bundled).
 *
 * Flusso:
 *  1. Il video viene letto in streaming via InputStream → nessun caricamento completo in RAM
 *  2. FFmpegFrameGrabber decodifica solo le tracce audio frame per frame
 *  3. FFmpegFrameRecorder codifica in MP3 → ByteArrayOutputStream (in memoria)
 *  4. Solo a fine elaborazione riuscita l'MP3 viene scritto su disco
 */
@Service
public class AudioExtractService {

    private static final Logger log = LoggerFactory.getLogger(AudioExtractService.class);

    private static final List<String> ALLOWED_EXTENSIONS =
            List.of("mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "ts", "mpeg", "mpg");

    private final AudioExtractorConfig config;

    public AudioExtractService(AudioExtractorConfig config) {
        this.config = config;
    }

    /**
     * Estrae l'audio MP3 dal video {@code filename}.
     *
     * @param filename nome del file video (solo nome, senza path)
     * @return nome del file MP3 creato
     */
    public String extractAudio(String filename) throws IOException {
        Path videoDir  = resolvedVideoDir();
        Path inputPath = safeResolve(videoDir, filename);

        if (!Files.exists(inputPath)) {
            throw new IllegalArgumentException("File non trovato: " + filename);
        }
        validateExtension(filename);

        Path outputPath = toMp3Path(inputPath);

        log.info("Inizio estrazione: {} ({} MB) -> {}",
                inputPath.getFileName(),
                String.format("%.1f", Files.size(inputPath) / 1_048_576.0),
                outputPath.getFileName());

        ByteArrayOutputStream mp3Buffer = new ByteArrayOutputStream();

        try (InputStream videoIn = Files.newInputStream(inputPath);
             FFmpegFrameGrabber grabber = new FFmpegFrameGrabber(videoIn)) {

            grabber.start();

            int channels   = grabber.getAudioChannels();
            int sampleRate = grabber.getSampleRate();

            if (channels == 0) {
                throw new IOException("Il file non contiene tracce audio: " + filename);
            }

            try (FFmpegFrameRecorder recorder = new FFmpegFrameRecorder(mp3Buffer, channels)) {
                recorder.setAudioCodec(AV_CODEC_ID_MP3);
                recorder.setAudioBitrate(config.getAudioBitrate() * 1000);
                recorder.setSampleRate(sampleRate);
                recorder.setFormat("mp3");
                recorder.start();

                Frame frame;
                while ((frame = grabber.grabSamples()) != null) {
                    recorder.record(frame);
                }
            }

        } catch (FFmpegFrameGrabber.Exception | FFmpegFrameRecorder.Exception e) {
            throw new IOException("Errore JavaCV/FFmpeg: " + e.getMessage(), e);
        }

        // Scrittura su disco solo a elaborazione completata con successo
        Files.write(outputPath, mp3Buffer.toByteArray());
        log.info("MP3 salvato: {} ({} KB)", outputPath.getFileName(), mp3Buffer.size() / 1024);

        return outputPath.getFileName().toString();
    }

    /** Restituisce i file video presenti nella directory configurata. */
    public List<String> listVideoFiles() throws IOException {
        Path dir = resolvedVideoDir();
        try (Stream<Path> stream = Files.list(dir)) {
            return stream
                    .filter(Files::isRegularFile)
                    .map(p -> p.getFileName().toString())
                    .filter(this::isVideoFile)
                    .sorted()
                    .toList();
        }
    }

    private Path resolvedVideoDir() throws IOException {
        Path dir = Paths.get(config.getVideoDir()).toAbsolutePath().normalize();
        Files.createDirectories(dir);
        return dir;
    }

    private Path safeResolve(Path dir, String filename) {
        if (filename.contains("/") || filename.contains("\\") || filename.contains("..")) {
            throw new SecurityException("Nome file non valido: " + filename);
        }
        Path resolved = dir.resolve(filename).normalize();
        if (!resolved.startsWith(dir)) {
            throw new SecurityException("Tentativo di path traversal: " + filename);
        }
        return resolved;
    }

    private Path toMp3Path(Path inputPath) {
        String name = inputPath.getFileName().toString();
        int dot = name.lastIndexOf('.');
        String base = (dot > 0) ? name.substring(0, dot) : name;
        return inputPath.resolveSibling(base + ".mp3");
    }

    private void validateExtension(String filename) {
        if (!isVideoFile(filename)) {
            throw new IllegalArgumentException("Formato non supportato. Ammessi: " + ALLOWED_EXTENSIONS);
        }
    }

    private boolean isVideoFile(String filename) {
        int dot = filename.lastIndexOf('.');
        if (dot < 0) return false;
        return ALLOWED_EXTENSIONS.contains(filename.substring(dot + 1).toLowerCase());
    }
}
