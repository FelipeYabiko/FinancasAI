package io.github.felipeyabiko.financasia.alerts.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfig {

    /** Injectable clock so tests control "now". */
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
