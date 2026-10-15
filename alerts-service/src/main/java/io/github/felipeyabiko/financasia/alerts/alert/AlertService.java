package io.github.felipeyabiko.financasia.alerts.alert;

import io.github.felipeyabiko.financasia.alerts.llm.AlertWriter;
import io.github.felipeyabiko.financasia.alerts.messaging.TransactionEvent;
import io.github.felipeyabiko.financasia.alerts.rules.AlertRule;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class AlertService {

    private static final Logger log = LoggerFactory.getLogger(AlertService.class);

    private final List<AlertRule> rules;
    private final AlertWriter writer;
    private final AlertRepository alerts;
    private final SeenChargeRepository seenCharges;
    private final Clock clock;

    public AlertService(List<AlertRule> rules, AlertWriter writer, AlertRepository alerts,
                        SeenChargeRepository seenCharges, Clock clock) {
        this.rules = rules;
        this.writer = writer;
        this.alerts = alerts;
        this.seenCharges = seenCharges;
        this.clock = clock;
    }

    /**
     * Applies every rule to the event and stores the resulting alerts. Idempotent: re-delivering the
     * same event (at-least-once messaging) never creates a second alert for the same rule.
     */
    public List<Alert> process(TransactionEvent event) {
        List<Alert> created = new ArrayList<>();
        for (AlertRule rule : rules) {
            if (alerts.existsByEventIdAndRule(event.eventId(), rule.name())) {
                continue;
            }
            rule.evaluate(event).ifPresent(candidate -> {
                var text = writer.write(candidate);
                var alert = new Alert(event.eventId(), event.transaction().id(), candidate.rule(),
                        candidate.severity(), text.title(), text.message(), candidate.facts(), text.llmWritten(),
                        Instant.now(clock));
                try {
                    created.add(alerts.save(alert));
                } catch (DuplicateKeyException e) {
                    log.debug("alert {} for event {} already stored", candidate.rule(), event.eventId());
                }
            });
        }
        rememberCharge(event);
        return created;
    }

    private void rememberCharge(TransactionEvent event) {
        var tx = event.transaction();
        if (tx.isExpense() && tx.descriptionNormalized() != null && !tx.descriptionNormalized().isBlank()) {
            seenCharges.save(new SeenCharge(event.eventId(), tx.descriptionNormalized(), tx.amountCents(), tx.date(), tx.id()));
        }
    }

    public Page<Alert> list(boolean unreadOnly, Pageable pageable) {
        return unreadOnly
                ? alerts.findByReadFalseOrderByCreatedAtDesc(pageable)
                : alerts.findAllByOrderByCreatedAtDesc(pageable);
    }

    public Alert markRead(String id) {
        Alert alert = alerts.findById(id).orElseThrow(() -> new NoSuchElementException("alert " + id + " not found"));
        alert.markRead();
        return alerts.save(alert);
    }

    public long unreadCount(Severity severity) {
        return alerts.countByReadFalseAndSeverity(severity);
    }
}
