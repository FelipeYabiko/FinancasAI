package io.github.felipeyabiko.financasia.alerts.rules;

import io.github.felipeyabiko.financasia.alerts.messaging.TransactionEvent;
import java.util.Optional;

/**
 * Strategy pattern: each rule decides on its own whether an event deserves an alert. New rules
 * are new beans; {@code AlertService} receives all of them through constructor injection.
 */
public interface AlertRule {

    String name();

    Optional<AlertCandidate> evaluate(TransactionEvent event);
}
