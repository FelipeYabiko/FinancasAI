package io.github.felipeyabiko.financasia.alerts.alert;

import java.time.LocalDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

/** Recent expenses, kept so the duplicate-charge rule can look back a few days. */
@Document("seen_charges")
public record SeenCharge(
        @Id String eventId,
        @Indexed String merchant,
        long amountCents,
        LocalDate date,
        Long transactionId) {}
