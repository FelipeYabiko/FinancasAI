package io.github.felipeyabiko.financasia.alerts.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/** Typed configuration (application.yml prefix {@code alerts}). */
@ConfigurationProperties(prefix = "alerts")
public record AlertsProperties(
        @DefaultValue("financasia.events") String exchange,
        @DefaultValue("alerts.transactions") String queue,
        @DefaultValue("transaction.created") String routingKey,
        @DefaultValue("") String internalToken,
        @DefaultValue Rules rules,
        @DefaultValue Llm llm) {

    public record Rules(
            /* a single expense at or above this is "large" (R$ 1.000,00) */
            @DefaultValue("100000") long largeExpenseCents,
            /* ...or at or above this share of the category's average month */
            @DefaultValue("0.5") double largeExpenseShareOfAverage,
            /* budget usage that triggers a warning */
            @DefaultValue("0.8") double budgetWarningShare,
            /* same merchant + amount within this many days = possible duplicate charge */
            @DefaultValue("2") int duplicateWindowDays) {}

    public record Llm(
            @DefaultValue("false") boolean enabled,
            @DefaultValue("https://api.groq.com/openai/v1") String baseUrl,
            @DefaultValue("openai/gpt-oss-20b") String model,
            @DefaultValue("") String apiKey,
            @DefaultValue("10s") Duration timeout) {}
}
