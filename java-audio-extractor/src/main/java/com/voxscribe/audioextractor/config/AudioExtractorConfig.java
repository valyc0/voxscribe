package com.voxscribe.audioextractor.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Proprietà configurabili tramite application.yml (prefisso "audio-extractor").
 *
 * <pre>
 * audio-extractor:
 *   video-dir: /mnt/videos        # directory contenente i file video
 *   ffmpeg-path: ffmpeg            # percorso binario ffmpeg (default: cerca nel PATH)
 *   audio-bitrate: 192             # bitrate MP3 in kbps
 * </pre>
 */
@ConfigurationProperties(prefix = "audio-extractor")
public class AudioExtractorConfig {

    /** Directory radice che contiene i file video da elaborare. */
    private String videoDir = "/tmp/videos";

    /** Percorso del binario ffmpeg. Di default si usa quello nel PATH di sistema. */
    private String ffmpegPath = "ffmpeg";

    /** Bitrate audio per l'MP3 in kbps. */
    private int audioBitrate = 192;

    public String getVideoDir() {
        return videoDir;
    }

    public void setVideoDir(String videoDir) {
        this.videoDir = videoDir;
    }

    public String getFfmpegPath() {
        return ffmpegPath;
    }

    public void setFfmpegPath(String ffmpegPath) {
        this.ffmpegPath = ffmpegPath;
    }

    public int getAudioBitrate() {
        return audioBitrate;
    }

    public void setAudioBitrate(int audioBitrate) {
        this.audioBitrate = audioBitrate;
    }
}
