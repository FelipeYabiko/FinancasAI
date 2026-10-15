package io.github.felipeyabiko.financasia.alerts.llm;

/** Minimal chat-completion port. Implementations talk to a provider; tests mock it with Mockito. */
public interface LlmClient {

    String complete(String systemPrompt, String userMessage);
}
