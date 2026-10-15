package io.github.felipeyabiko.financasia.alerts.alert;

import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AlertRepository extends MongoRepository<Alert, String> {

    Page<Alert> findAllByOrderByCreatedAtDesc(Pageable pageable);

    Page<Alert> findByReadFalseOrderByCreatedAtDesc(Pageable pageable);

    long countByReadFalseAndSeverity(Severity severity);

    boolean existsByEventIdAndRule(String eventId, String rule);

    List<Alert> findByCreatedAtAfter(Instant since);
}
