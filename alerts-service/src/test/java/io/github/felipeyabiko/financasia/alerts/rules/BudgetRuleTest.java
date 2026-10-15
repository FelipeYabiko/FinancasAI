package io.github.felipeyabiko.financasia.alerts.rules;

import static io.github.felipeyabiko.financasia.alerts.Fixtures.expense;
import static io.github.felipeyabiko.financasia.alerts.Fixtures.properties;
import static org.assertj.core.api.Assertions.assertThat;

import io.github.felipeyabiko.financasia.alerts.alert.Severity;
import org.junit.jupiter.api.Test;

class BudgetRuleTest {

    private final BudgetRule rule = new BudgetRule(properties());

    @Test
    void dangerWhenThisExpenseCrossesTheBudget() {
        // spent 380 before + 50 now = 430 of 400
        var alert = rule.evaluate(expense("e1", 5_000, "Delivery", 43_000L, 40_000L, null));
        assertThat(alert).get().extracting(AlertCandidate::severity).isEqualTo(Severity.DANGER);
        assertThat(alert.get().facts()).containsEntry("percentual", "107%");
    }

    @Test
    void warningWhenCrossing80Percent() {
        // 300 before + 30 now = 330 of 400 (82%)
        var alert = rule.evaluate(expense("e1", 3_000, "Delivery", 33_000L, 40_000L, null));
        assertThat(alert).get().extracting(AlertCandidate::severity).isEqualTo(Severity.WARNING);
    }

    @Test
    void silentWhenAlreadyOverBeforeThisExpense() {
        // already at 450 of 400 before: the user was warned when it crossed
        assertThat(rule.evaluate(expense("e1", 1_000, "Delivery", 46_000L, 40_000L, null))).isEmpty();
    }

    @Test
    void silentWithoutBudget() {
        assertThat(rule.evaluate(expense("e1", 1_000, "Delivery", 46_000L, null, null))).isEmpty();
    }
}
