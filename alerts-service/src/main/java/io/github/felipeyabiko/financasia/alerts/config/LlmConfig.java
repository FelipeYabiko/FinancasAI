package io.github.felipeyabiko.financasia.alerts.config;

import io.github.felipeyabiko.financasia.alerts.llm.AlertWriter;
import io.github.felipeyabiko.financasia.alerts.llm.LlmAlertWriter;
import io.github.felipeyabiko.financasia.alerts.llm.OpenAiCompatibleLlmClient;
import io.github.felipeyabiko.financasia.alerts.llm.TemplateAlertWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LlmConfig {

    /** LLM writing only when enabled AND a key is configured; otherwise deterministic templates. */
    @Bean
    AlertWriter alertWriter(AlertsProperties properties) {
        var llm = properties.llm();
        if (llm.enabled() && !llm.apiKey().isBlank()) {
            return new LlmAlertWriter(new OpenAiCompatibleLlmClient(llm));
        }
        return new TemplateAlertWriter();
    }
}
