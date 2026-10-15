package io.github.felipeyabiko.financasia.alerts.alert;

import static io.github.felipeyabiko.financasia.alerts.Fixtures.expense;
import static io.github.felipeyabiko.financasia.alerts.Fixtures.properties;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import io.github.felipeyabiko.financasia.alerts.llm.TemplateAlertWriter;
import io.github.felipeyabiko.financasia.alerts.rules.BudgetRule;
import io.github.felipeyabiko.financasia.alerts.rules.LargeExpenseRule;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class AlertServiceTest {

    @Mock
    AlertRepository alerts;

    @Mock
    SeenChargeRepository seenCharges;

    private AlertService service;

    @BeforeEach
    void setUp() {
        var clock = Clock.fixed(Instant.parse("2026-10-15T10:00:00Z"), ZoneOffset.UTC);
        service = new AlertService(List.of(new LargeExpenseRule(properties()), new BudgetRule(properties())),
                new TemplateAlertWriter(), alerts, seenCharges, clock);
    }

    @Test
    void storesOneAlertPerMatchingRule() {
        when(alerts.save(any(Alert.class))).thenAnswer(inv -> inv.getArgument(0));
        var created = service.process(expense("e1", 150_000, "Compras", 160_000L, 100_000L, null));
        assertThat(created).extracting(Alert::getRule).containsExactly("large_expense", "budget");
        assertThat(created.get(0).getCreatedAt()).isEqualTo(Instant.parse("2026-10-15T10:00:00Z"));
        verify(seenCharges).save(any(SeenCharge.class));
    }

    @Test
    void redeliveredEventDoesNotDuplicateAlerts() {
        when(alerts.existsByEventIdAndRule(eq("e1"), anyString())).thenReturn(true);
        var created = service.process(expense("e1", 150_000, "Compras", 160_000L, 100_000L, null));
        assertThat(created).isEmpty();
        verify(alerts, never()).save(any());
    }
}
