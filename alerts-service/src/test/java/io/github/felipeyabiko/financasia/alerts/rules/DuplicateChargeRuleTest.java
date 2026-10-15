package io.github.felipeyabiko.financasia.alerts.rules;

import static io.github.felipeyabiko.financasia.alerts.Fixtures.expense;
import static io.github.felipeyabiko.financasia.alerts.Fixtures.properties;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

import io.github.felipeyabiko.financasia.alerts.alert.SeenCharge;
import io.github.felipeyabiko.financasia.alerts.alert.SeenChargeRepository;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class DuplicateChargeRuleTest {

    @Mock
    SeenChargeRepository seenCharges;

    @Test
    void flagsSameMerchantAndAmountWithinWindow() {
        when(seenCharges.findByMerchantAndAmountCentsAndDateBetween(eq("supermercado bom preco"), eq(-4500L), any(), any()))
                .thenReturn(List.of(new SeenCharge("other-event", "supermercado bom preco", -4500, LocalDate.of(2026, 10, 13), 9L)));
        var rule = new DuplicateChargeRule(seenCharges, properties());

        var alert = rule.evaluate(expense("e1", 4_500, "Mercado", null, null, null));

        assertThat(alert).isPresent();
        assertThat(alert.get().facts()).containsEntry("data_cobranca_anterior", "2026-10-13");
    }

    @Test
    void ignoresTheSameEventRedelivered() {
        when(seenCharges.findByMerchantAndAmountCentsAndDateBetween(any(), anyLong(), any(), any()))
                .thenReturn(List.of(new SeenCharge("e1", "supermercado bom preco", -4500, LocalDate.of(2026, 10, 14), 1L)));
        var rule = new DuplicateChargeRule(seenCharges, properties());

        assertThat(rule.evaluate(expense("e1", 4_500, "Mercado", null, null, null))).isEmpty();
    }
}
