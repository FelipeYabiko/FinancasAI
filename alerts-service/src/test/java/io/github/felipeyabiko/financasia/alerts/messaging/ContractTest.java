package io.github.felipeyabiko.financasia.alerts.messaging;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Validation;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

/**
 * Consumer side of the contract: the example the Python producer is tested against must
 * deserialize into TransactionEvent and pass validation. Unknown fields are ignored on purpose
 * (producers may add fields), but missing required ones fail.
 */
class ContractTest {

    private static final Path CONTRACT = Path.of("..", "contracts", "transaction-created.example.json");

    @Test
    void sharedExampleIsAValidTransactionEvent() throws Exception {
        var mapper = new ObjectMapper().findAndRegisterModules()
                .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE);
        var event = mapper.readValue(Files.readString(CONTRACT), TransactionEvent.class);

        try (var factory = Validation.buildDefaultValidatorFactory()) {
            assertThat(factory.getValidator().validate(event)).isEmpty();
        }
        assertThat(event.transaction().amountCents()).isEqualTo(-329_900L);
        assertThat(event.transaction().isExpense()).isTrue();
        assertThat(event.context().categoryBudgetCents()).isEqualTo(300_000L);
    }
}
