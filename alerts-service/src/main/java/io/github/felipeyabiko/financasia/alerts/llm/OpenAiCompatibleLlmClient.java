package io.github.felipeyabiko.financasia.alerts.llm;

import com.fasterxml.jackson.databind.JsonNode;
import io.github.felipeyabiko.financasia.alerts.config.AlertsProperties;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/**
 * Chat-completions client for any OpenAI-compatible API (Groq, OpenRouter, Gemini's compatibility
 * endpoint). Same wire format the Python app uses.
 */
public class OpenAiCompatibleLlmClient implements LlmClient {

    private final RestClient http;
    private final String model;

    public OpenAiCompatibleLlmClient(AlertsProperties.Llm config) {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout((int) config.timeout().toMillis());
        factory.setReadTimeout((int) config.timeout().toMillis());
        this.http = RestClient.builder()
                .baseUrl(config.baseUrl())
                .requestFactory(factory)
                .defaultHeader("Authorization", "Bearer " + config.apiKey())
                .build();
        this.model = config.model();
    }

    @Override
    public String complete(String systemPrompt, String userMessage) {
        var body = Map.of(
                "model", model,
                "temperature", 0.2,
                "messages", List.of(
                        Map.of("role", "system", "content", systemPrompt),
                        Map.of("role", "user", "content", userMessage)));
        JsonNode response = http.post()
                .uri("/chat/completions")
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(JsonNode.class);
        if (response == null) {
            throw new IllegalStateException("empty response from LLM provider");
        }
        return response.path("choices").path(0).path("message").path("content").asText("");
    }
}
