package io.github.felipeyabiko.financasia.alerts.alert;

import java.time.LocalDate;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface SeenChargeRepository extends MongoRepository<SeenCharge, String> {

    List<SeenCharge> findByMerchantAndAmountCentsAndDateBetween(
            String merchant, long amountCents, LocalDate from, LocalDate to);
}
