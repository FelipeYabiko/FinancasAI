package io.github.felipeyabiko.financasia.alerts.rules;

import io.github.felipeyabiko.financasia.alerts.alert.SeenChargeRepository;
import io.github.felipeyabiko.financasia.alerts.alert.Severity;
import io.github.felipeyabiko.financasia.alerts.config.AlertsProperties;
import io.github.felipeyabiko.financasia.alerts.messaging.TransactionEvent;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** Same merchant and same amount within a few days: maybe the card was charged twice. */
@Component
public class DuplicateChargeRule implements AlertRule {

    private final SeenChargeRepository seenCharges;
    private final AlertsProperties.Rules config;

    public DuplicateChargeRule(SeenChargeRepository seenCharges, AlertsProperties properties) {
        this.seenCharges = seenCharges;
        this.config = properties.rules();
    }

    @Override
    public String name() {
        return "duplicate_charge";
    }

    @Override
    public Optional<AlertCandidate> evaluate(TransactionEvent event) {
        var tx = event.transaction();
        if (!tx.isExpense() || tx.descriptionNormalized() == null || tx.descriptionNormalized().isBlank()) {
            return Optional.empty();
        }
        int window = config.duplicateWindowDays();
        var previous = seenCharges.findByMerchantAndAmountCentsAndDateBetween(
                        tx.descriptionNormalized(), tx.amountCents(), tx.date().minusDays(window), tx.date().plusDays(window))
                .stream()
                .filter(c -> !c.eventId().equals(event.eventId()))
                .findFirst();
        if (previous.isEmpty()) {
            return Optional.empty();
        }
        Map<String, Object> facts = new LinkedHashMap<>();
        facts.put("descricao", tx.description());
        facts.put("valor", Money.brl(tx.absCents()));
        facts.put("data", tx.date().toString());
        facts.put("data_cobranca_anterior", previous.get().date().toString());
        String message = "\"%s\" de %s aparece duas vezes (%s e %s). Confira se não foi cobrado em dobro."
                .formatted(tx.description(), Money.brl(tx.absCents()), previous.get().date(), tx.date());
        return Optional.of(new AlertCandidate(name(), Severity.WARNING, "Possível cobrança duplicada", message, facts));
    }
}
