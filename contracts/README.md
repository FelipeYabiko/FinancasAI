# Event contracts

Messages exchanged between the FinançasIA app (producer, Python) and the alerts-service
(consumer, Java). Both sides test against these examples:

- `tests/test_events.py` checks that the payload the app builds has exactly this shape.
- `alerts-service/.../ContractTest.java` deserializes this file into `TransactionEvent` and validates it.

A breaking change to the shape must update this file, which fails the other side's test.

| Field | Type | Notes |
|---|---|---|
| `event_id` | UUID string | idempotency key (delivery is at-least-once) |
| `type` | `transaction.created` | also the RabbitMQ routing key on exchange `financasia.events` |
| `transaction.amount_cents` | integer | signed cents: money out < 0 |
| `context.*_cents` | integer or null | facts computed by the producer at publish time |
