package io.github.felipeyabiko.financasia.alerts.rules;

import io.github.felipeyabiko.financasia.alerts.alert.Severity;
import io.github.felipeyabiko.financasia.alerts.config.AlertsProperties;
import io.github.felipeyabiko.financasia.alerts.messaging.TransactionEvent;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * Fires when THIS transaction made the category cross 80% or 100% of its monthly budget
 * (so the user is warned once per threshold, not on every purchase afterwards).
 */
@Component
public class BudgetRule implements AlertRule {

    private final AlertsProperties.Rules config;

    public BudgetRule(AlertsProperties properties) {
        this.config = properties.rules();
    }

    @Override
    public String name() {
        return "budget";
    }

    @Override
    public Optional<AlertCandidate> evaluate(TransactionEvent event) {
        var tx = event.transaction();
        Long spent = event.context().categoryMonthSpentCents();
        Long budget = event.context().categoryBudgetCents();
        if (!tx.isExpense() || spent == null || budget == null || budget <= 0) {
            return Optional.empty();
        }
        long before = spent - tx.absCents();
        long warning = Math.round(budget * config.budgetWarningShare());
        Severity severity;
        String title;
        if (before < budget && spent >= budget) {
            severity = Severity.DANGER;
            title = "Orçamento estourado";
        } else if (before < warning && spent >= warning && spent < budget) {
            severity = Severity.WARNING;
            title = "Orçamento perto do limite";
        } else {
            return Optional.empty();
        }
        long percent = spent * 100 / budget;
        Map<String, Object> facts = new LinkedHashMap<>();
        facts.put("categoria", tx.category());
        facts.put("gasto_no_mes", Money.brl(spent));
        facts.put("orcamento", Money.brl(budget));
        facts.put("percentual", percent + "%");
        String message = "%s: %s de %s no mês (%d%%)."
                .formatted(tx.category(), Money.brl(spent), Money.brl(budget), percent);
        return Optional.of(new AlertCandidate(name(), severity, title, message, facts));
    }
}
