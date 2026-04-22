package com.voxscribe.audioextractor.dto;

/**
 * Risposta dell'endpoint /api/audio/files e messaggi di errore.
 */
public record ExtractResponse(
        String status,
        String inputFile,
        String outputFile,
        String message
) {}
