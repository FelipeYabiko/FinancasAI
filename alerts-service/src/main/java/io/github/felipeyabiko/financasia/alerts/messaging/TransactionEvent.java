package io.github.felipeyabiko.financasia.alerts.messaging;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import java.time.LocalDate;

/**
 * Event published by the FinançasIA app (transactional outbox) when a transaction is created.
 * Money is always integer cents; amounts are signed (money out is negative).
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record TransactionEvent(
        @JsonProperty("event_id") @NotBlank String eventId,
        @NotBlank String type,
        @JsonProperty("occurred_at") Instant occurredAt,
        @NotNull @Valid Transaction transaction,
        @NotNull Context context) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Transaction(
            @NotNull Long id,
            @NotNull LocalDate date,
            @NotBlank String description,
            @JsonProperty("description_normalized") String descriptionNormalized,
            @JsonProperty("amount_cents") long amountCents,
            @NotBlank String type,
            String category,
            String account,
            String origin) {

        public boolean isExpense() {
            return "expense".equals(type) && amountCents < 0;
        }

        /** Positive magnitude of the amount. */
        public long absCents() {
            return Math.abs(amountCents);
        }
    }

    /** Facts computed by the app at publish time, so this service needs no access to the ledger. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Context(
            @JsonProperty("category_month_spent_cents") Long categoryMonthSpentCents,
            @JsonProperty("category_budget_cents") Long categoryBudgetCents,
            @JsonProperty("category_avg_month_cents") Long categoryAvgMonthCents) {}
}
