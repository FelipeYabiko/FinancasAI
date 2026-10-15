package io.github.felipeyabiko.financasia.alerts;

import io.github.felipeyabiko.financasia.alerts.config.AlertsProperties;
import io.github.felipeyabiko.financasia.alerts.messaging.TransactionEvent;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;

public final class Fixtures {

    private Fixtures() {}

    public static AlertsProperties properties() {
        return new AlertsProperties("financasia.events", "alerts.transactions", "transaction.created", "",
                new AlertsProperties.Rules(100_000, 0.5, 0.8, 2),
                new AlertsProperties.Llm(false, "http://localhost", "m", "", Duration.ofSeconds(1)));
    }

    public static TransactionEvent expense(String eventId, long cents, String category, Long spent, Long budget, Long avg) {
        var tx = new TransactionEvent.Transaction(1L, LocalDate.of(2026, 10, 14), "SUPERMERCADO BOM PRECO",
                "supermercado bom preco", -cents, "expense", category, "Nubank", "manual");
        return new TransactionEvent(eventId, "transaction.created", Instant.parse("2026-10-14T12:00:00Z"), tx,
                new TransactionEvent.Context(spent, budget, avg));
    }
}
