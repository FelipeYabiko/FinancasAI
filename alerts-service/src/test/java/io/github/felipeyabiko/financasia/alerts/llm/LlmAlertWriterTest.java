package io.github.felipeyabiko.financasia.alerts.llm;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import io.github.felipeyabiko.financasia.alerts.alert.Severity;
import io.github.felipeyabiko.financasia.alerts.rules.AlertCandidate;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class LlmAlertWriterTest {

    @Mock
    LlmClient llm;

    private final AlertCandidate candidate = new AlertCandidate("large_expense", Severity.WARNING, "Gasto alto",
            "Gasto de R$ 1.500,00 em \"TV\".", Map.of("valor", "R$ 1.500,00", "descricao", "TV"));

    @Test
    void usesTheModelTextWhenItOnlyQuotesTheFacts() {
        when(llm.complete(anyString(), anyString())).thenReturn("Você gastou R$ 1.500,00 na TV — vale conferir o orçamento.");
        var out = new LlmAlertWriter(llm).write(candidate);
        assertThat(out.llmWritten()).isTrue();
        assertThat(out.message()).contains("R$ 1.500,00");
    }

    @Test
    void rejectsInventedAmounts() {
        when(llm.complete(anyString(), anyString())).thenReturn("Você gastou R$ 2.000,00 na TV.");
        var out = new LlmAlertWriter(llm).write(candidate);
        assertThat(out.llmWritten()).isFalse();
        assertThat(out.message()).isEqualTo(candidate.defaultMessage());
    }

    @Test
    void fallsBackWhenTheProviderFails() {
        when(llm.complete(anyString(), anyString())).thenThrow(new IllegalStateException("429 rate limit"));
        assertThat(new LlmAlertWriter(llm).write(candidate).llmWritten()).isFalse();
    }

    @Test
    void fallsBackOnEmptyAnswer() {
        when(llm.complete(anyString(), anyString())).thenReturn("   ");
        assertThat(new LlmAlertWriter(llm).write(candidate).message()).isEqualTo(candidate.defaultMessage());
    }
}
