package io.github.felipeyabiko.financasia.alerts.rules;

import io.github.felipeyabiko.financasia.alerts.alert.Severity;
import io.github.felipeyabiko.financasia.alerts.config.AlertsProperties;
import io.github.felipeyabiko.financasia.alerts.messaging.TransactionEvent;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** A single expense that is big in absolute terms or relative to the category's usual month. */
@Component
public class LargeExpenseRule implements AlertRule {

    private final AlertsProperties.Rules config;

    public LargeExpenseRule(AlertsProperties properties) {
        this.config = properties.rules();
    }

    @Override
    public String name() {
        return "large_expense";
    }

    @Override
    public Optional<AlertCandidate> evaluate(TransactionEvent event) {
        var tx = event.transaction();
        if (!tx.isExpense()) {
            return Optional.empty();
        }
        Long avg = event.context().categoryAvgMonthCents();
        boolean absolute = tx.absCents() >= config.largeExpenseCents();
        boolean relative = avg != null && avg > 0 && tx.absCents() >= avg * config.largeExpenseShareOfAverage();
        if (!absolute && !relative) {
            return Optional.empty();
        }
        Map<String, Object> facts = new LinkedHashMap<>();
        facts.put("descricao", tx.description());
        facts.put("valor", Money.brl(tx.absCents()));
        facts.put("categoria", tx.category() == null ? "Sem categoria" : tx.category());
        if (avg != null && avg > 0) {
            facts.put("media_mensal_categoria", Money.brl(avg));
        }
        String message = "Gasto de %s em \"%s\"%s.".formatted(
                Money.brl(tx.absCents()),
                tx.description(),
                relative ? " — acima da metade do que você costuma gastar por mês em " + facts.get("categoria") : "");
        return Optional.of(new AlertCandidate(name(), Severity.WARNING, "Gasto alto", message, facts));
    }
}
