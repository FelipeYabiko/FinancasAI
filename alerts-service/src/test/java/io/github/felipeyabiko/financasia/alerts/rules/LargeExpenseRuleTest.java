package io.github.felipeyabiko.financasia.alerts.rules;

import static io.github.felipeyabiko.financasia.alerts.Fixtures.expense;
import static io.github.felipeyabiko.financasia.alerts.Fixtures.properties;
import static org.assertj.core.api.Assertions.assertThat;

import io.github.felipeyabiko.financasia.alerts.alert.Severity;
import org.junit.jupiter.api.Test;

class LargeExpenseRuleTest {

    private final LargeExpenseRule rule = new LargeExpenseRule(properties());

    @Test
    void flagsExpenseAboveAbsoluteThreshold() {
        var alert = rule.evaluate(expense("e1", 150_000, "Compras", null, null, null));
        assertThat(alert).isPresent();
        assertThat(alert.get().severity()).isEqualTo(Severity.WARNING);
        assertThat(alert.get().facts()).containsEntry("valor", "R$ 1.500,00");
    }

    @Test
    void flagsExpenseLargeRelativeToCategoryAverage() {
        // R$ 300 is half of the usual R$ 600 per month in this category
        var alert = rule.evaluate(expense("e1", 30_000, "Mercado", null, null, 60_000L));
        assertThat(alert).isPresent();
        assertThat(alert.get().defaultMessage()).contains("acima da metade");
    }

    @Test
    void ignoresSmallExpense() {
        assertThat(rule.evaluate(expense("e1", 4_500, "Mercado", null, null, 60_000L))).isEmpty();
    }
}
