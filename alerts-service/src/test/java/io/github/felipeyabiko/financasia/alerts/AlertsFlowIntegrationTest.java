package io.github.felipeyabiko.financasia.alerts;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import io.github.felipeyabiko.financasia.alerts.alert.AlertRepository;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * End to end with real infrastructure (Testcontainers): an event published to RabbitMQ becomes
 * alerts in MongoDB; redelivery is idempotent; a malformed event goes to the dead-letter queue.
 */
@SpringBootTest
@Testcontainers
class AlertsFlowIntegrationTest {

    @Container
    @ServiceConnection
    static MongoDBContainer mongo = new MongoDBContainer("mongo:7.0");

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit = new RabbitMQContainer("rabbitmq:3.13-management-alpine");

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Autowired
    AlertRepository alerts;

    @BeforeEach
    void clean() {
        alerts.deleteAll();
    }

    private void publish(String json) {
        var props = new MessageProperties();
        props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        rabbitTemplate.send("financasia.events", "transaction.created", new Message(json.getBytes(), props));
    }

    private static String event(String eventId) {
        return """
                {"event_id": "%s", "type": "transaction.created", "occurred_at": "2026-10-14T12:00:00Z",
                 "transaction": {"id": 42, "date": "2026-10-14", "description": "ELETRO CENTER TV",
                   "description_normalized": "eletro center tv", "amount_cents": -329900, "type": "expense",
                   "category": "Compras", "account": "Nubank", "origin": "assistant"},
                 "context": {"category_month_spent_cents": 340000, "category_budget_cents": 300000,
                   "category_avg_month_cents": 80000}}""".formatted(eventId);
    }

    @Test
    void eventBecomesAlertsAndRedeliveryIsIdempotent() {
        publish(event("evt-1"));
        await().atMost(Duration.ofSeconds(15)).untilAsserted(() ->
                assertThat(alerts.findAll()).extracting("rule").containsExactlyInAnyOrder("large_expense", "budget"));

        publish(event("evt-1")); // at-least-once delivery: same event again
        publish(event("evt-2")); // a new event with the same charge → possible duplicate
        await().atMost(Duration.ofSeconds(15)).untilAsserted(() ->
                assertThat(alerts.findAll()).extracting("rule").contains("duplicate_charge"));
        assertThat(alerts.findAll().stream().filter(a -> a.getEventId().equals("evt-1"))).hasSize(2);
    }

    @Test
    void malformedEventIsDeadLettered() {
        publish("{\"event_id\": \"bad\", \"type\": \"transaction.created\"}");
        await().atMost(Duration.ofSeconds(15)).untilAsserted(() ->
                assertThat(rabbitTemplate.receive("alerts.transactions.dlq")).isNotNull());
        assertThat(alerts.count()).isZero();
    }
}
