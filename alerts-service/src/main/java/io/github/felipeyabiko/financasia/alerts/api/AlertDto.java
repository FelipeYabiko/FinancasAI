package io.github.felipeyabiko.financasia.alerts.api;

import io.github.felipeyabiko.financasia.alerts.alert.Alert;
import io.github.felipeyabiko.financasia.alerts.alert.Severity;
import java.time.Instant;
import java.util.Map;

public record AlertDto(
        String id,
        Long transactionId,
        String rule,
        Severity severity,
        String title,
        String message,
        Map<String, Object> facts,
        boolean llmWritten,
        boolean read,
        Instant createdAt) {

    public static AlertDto from(Alert a) {
        return new AlertDto(a.getId(), a.getTransactionId(), a.getRule(), a.getSeverity(), a.getTitle(),
                a.getMessage(), a.getFacts(), a.isLlmWritten(), a.isRead(), a.getCreatedAt());
    }
}
