package io.github.felipeyabiko.financasia.alerts.messaging;

import io.github.felipeyabiko.financasia.alerts.alert.AlertService;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class TransactionEventListener {

    private static final Logger log = LoggerFactory.getLogger(TransactionEventListener.class);

    private final AlertService alertService;
    private final Validator validator;

    public TransactionEventListener(AlertService alertService, Validator validator) {
        this.alertService = alertService;
        this.validator = validator;
    }

    @RabbitListener(queues = "${alerts.queue:alerts.transactions}")
    public void onTransactionEvent(TransactionEvent event) {
        Set<ConstraintViolation<TransactionEvent>> violations = validator.validate(event);
        if (!violations.isEmpty()) {
            // A malformed event will never succeed: skip retries and send it straight to the DLQ.
            throw new AmqpRejectAndDontRequeueException("invalid event: " + violations);
        }
        var created = alertService.process(event);
        log.info("event {} (transaction {}) → {} alert(s)", event.eventId(), event.transaction().id(), created.size());
    }
}
