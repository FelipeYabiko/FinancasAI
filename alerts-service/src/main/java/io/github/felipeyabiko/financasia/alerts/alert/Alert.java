package io.github.felipeyabiko.financasia.alerts.alert;

import java.time.Instant;
import java.util.Map;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

/**
 * An alert stored in MongoDB. The unique (eventId, rule) index makes the consumer idempotent:
 * RabbitMQ delivers at-least-once, so the same event may arrive twice.
 */
@Document("alerts")
@CompoundIndex(name = "event_rule_unique", def = "{'eventId': 1, 'rule': 1}", unique = true)
public class Alert {

    @Id
    private String id;
    private String eventId;
    private Long transactionId;
    private String rule;
    private Severity severity;
    private String title;
    private String message;
    private Map<String, Object> facts;
    private boolean llmWritten;
    private boolean read;
    private Instant createdAt;

    protected Alert() {}

    public Alert(String eventId, Long transactionId, String rule, Severity severity, String title,
                 String message, Map<String, Object> facts, boolean llmWritten, Instant createdAt) {
        this.eventId = eventId;
        this.transactionId = transactionId;
        this.rule = rule;
        this.severity = severity;
        this.title = title;
        this.message = message;
        this.facts = facts;
        this.llmWritten = llmWritten;
        this.createdAt = createdAt;
    }

    public void markRead() {
        this.read = true;
    }

    public String getId() { return id; }
    public String getEventId() { return eventId; }
    public Long getTransactionId() { return transactionId; }
    public String getRule() { return rule; }
    public Severity getSeverity() { return severity; }
    public String getTitle() { return title; }
    public String getMessage() { return message; }
    public Map<String, Object> getFacts() { return facts; }
    public boolean isLlmWritten() { return llmWritten; }
    public boolean isRead() { return read; }
    public Instant getCreatedAt() { return createdAt; }
}
