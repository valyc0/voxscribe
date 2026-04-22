package com.voxscribe.audioextractor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

import com.voxscribe.audioextractor.config.AudioExtractorConfig;

@SpringBootApplication
@EnableConfigurationProperties(AudioExtractorConfig.class)
public class AudioExtractorApplication {

    public static void main(String[] args) {
        SpringApplication.run(AudioExtractorApplication.class, args);
    }
}
