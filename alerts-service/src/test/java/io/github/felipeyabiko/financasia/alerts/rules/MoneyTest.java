package io.github.felipeyabiko.financasia.alerts.rules;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class MoneyTest {

    @ParameterizedTest
    @CsvSource({"123456, 'R$ 1.234,56'", "5, 'R$ 0,05'", "-4500, '-R$ 45,00'", "100000000, 'R$ 1.000.000,00'"})
    void formatsCentsAsBrl(long cents, String expected) {
        assertThat(Money.brl(cents)).isEqualTo(expected);
    }
}
