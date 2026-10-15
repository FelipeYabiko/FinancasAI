"""Domain events for other services, delivered through a transactional outbox.

Write path: a SQLAlchemy session hook adds an `OutboxEvent` for every new income/expense in the
same database transaction that creates it (no "saved but never announced" gap, no dual write).

Delivery path: `OutboxRelay` (a background thread, only when RABBITMQ_URL is set) publishes
pending events to the `financasia.events` topic exchange with publisher confirms, then marks them
published. Delivery is at-least-once, so consumers deduplicate by `event_id`.
"""

import json
import logging
import threading
import uuid
from datetime import UTC, datetime

from sqlalchemy import event as sa_event
from sqlmodel import Session, col, func, select

from app.domain.dates import add_months_to_month, month_bounds, month_key
from app.models import Account, Budget, Category, OutboxEvent, Transaction

log = logging.getLogger("financasia.events")

EVENT_TRANSACTION_CREATED = "transaction.created"
SKIP_OUTBOX = "skip_outbox"  # session.info flag (e.g. restoring a backup is not "new spending")


# ---------------------------------------------------------------- write path (outbox)
def _collect_new_transactions(session, _flush_context) -> None:
    if session.info.get(SKIP_OUTBOX):
        return
    new = [o for o in session.new if isinstance(o, Transaction) and o.type in ("income", "expense")]
    if new:
        session.info.setdefault("_outbox_pending", []).extend(t.id for t in new)


def _add_outbox_events(session, _flush_context) -> None:
    pending = session.info.pop("_outbox_pending", None)
    for tx_id in pending or []:
        # Added after the flush; Session.commit() flushes again until clean, so these rows are
        # committed atomically with the transactions themselves.
        session.add(
            OutboxEvent(
                event_id=str(uuid.uuid4()), type=EVENT_TRANSACTION_CREATED, aggregate_id=tx_id
            )
        )


def register_outbox_hooks() -> None:
    if not sa_event.contains(Session, "after_flush", _collect_new_transactions):
        sa_event.listen(Session, "after_flush", _collect_new_transactions)
        sa_event.listen(Session, "after_flush_postexec", _add_outbox_events)


# ---------------------------------------------------------------- event payload
def _category_spent(db: Session, category_id: int, start, end, up_to_id: int | None = None) -> int:
    stmt = select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
        Transaction.category_id == category_id,
        Transaction.type == "expense",
        Transaction.date >= start,
        Transaction.date <= end,
    )
    if up_to_id is not None:
        # State as of this transaction's creation, not as of publishing: the relay may publish
        # after later transactions exist, which would hide the "this one crossed the budget" moment.
        stmt = stmt.where(Transaction.id <= up_to_id)
    return -int(db.exec(stmt).one())


def build_event(db: Session, outbox: OutboxEvent) -> dict | None:
    """The `transaction.created` message (contract: contracts/transaction-created.example.json).
    Context facts are computed here so the consumer never needs to read this database."""
    tx = db.get(Transaction, outbox.aggregate_id)
    if tx is None:
        return None  # deleted before it was published: nothing to announce
    category = db.get(Category, tx.category_id) if tx.category_id else None
    account = db.get(Account, tx.account_id)
    context: dict[str, int | None] = {
        "category_month_spent_cents": None,
        "category_budget_cents": None,
        "category_avg_month_cents": None,
    }
    if category:
        month = month_key(tx.date)
        start, end = month_bounds(month)
        context["category_month_spent_cents"] = _category_spent(
            db, category.id, start, end, up_to_id=tx.id
        )
        budget = db.exec(
            select(Budget).where(Budget.category_id == category.id, Budget.month == month)
        ).first()
        context["category_budget_cents"] = budget.limit_cents if budget else None
        prev = [month_bounds(add_months_to_month(month, -i)) for i in (1, 2, 3)]
        context["category_avg_month_cents"] = (
            sum(_category_spent(db, category.id, s, e) for s, e in prev) // 3
        )
    return {
        "event_id": outbox.event_id,
        "type": outbox.type,
        "occurred_at": outbox.created_at.replace(
            tzinfo=outbox.created_at.tzinfo or UTC
        ).isoformat(),
        "transaction": {
            "id": tx.id,
            "date": tx.date.isoformat(),
            "description": tx.description,
            "description_normalized": tx.description_normalized,
            "amount_cents": tx.amount_cents,
            "type": tx.type,
            "category": category.name if category else None,
            "account": account.name if account else None,
            "origin": tx.origin,
        },
        "context": context,
    }


# ---------------------------------------------------------------- delivery path (relay)
def publish_pending(db: Session, publish, limit: int = 100) -> int:
    """Publish unpublished events in order. `publish(routing_key, body, message_id)` must raise
    on failure (e.g. a nacked publisher confirm). Stops at the first failure to keep order."""
    sent = 0
    rows = db.exec(
        select(OutboxEvent)
        .where(col(OutboxEvent.published_at).is_(None))
        .order_by(OutboxEvent.id)
        .limit(limit)
    ).all()
    for row in rows:
        payload = build_event(db, row)
        try:
            if payload is not None:
                publish(row.type, json.dumps(payload, ensure_ascii=False).encode(), row.event_id)
        except Exception as exc:
            row.attempts += 1
            row.last_error = str(exc)[:300]
            db.add(row)
            db.commit()
            log.warning("outbox publish failed (event %s): %s", row.event_id, exc)
            break
        row.published_at = datetime.now(UTC)
        db.add(row)
        db.commit()
        sent += 1
    return sent


class OutboxRelay(threading.Thread):
    """Background publisher with reconnect/backoff. Started by the app when RABBITMQ_URL is set."""

    def __init__(self, engine, url: str, exchange: str, interval: float = 2.0):
        super().__init__(name="outbox-relay", daemon=True)
        self.engine, self.url, self.exchange, self.interval = engine, url, exchange, interval
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # pragma: no cover - exercised against a real broker
        import pika

        backoff = 1.0
        while not self._stop.is_set():
            try:
                conn = pika.BlockingConnection(pika.URLParameters(self.url))
                channel = conn.channel()
                channel.exchange_declare(self.exchange, exchange_type="topic", durable=True)
                channel.confirm_delivery()  # basic_publish raises if the broker nacks

                def publish(routing_key: str, body: bytes, message_id: str, ch=channel) -> None:
                    ch.basic_publish(
                        self.exchange,
                        routing_key,
                        body,
                        pika.BasicProperties(
                            content_type="application/json", delivery_mode=2, message_id=message_id
                        ),
                        mandatory=False,
                    )

                backoff = 1.0
                while not self._stop.is_set():
                    with Session(self.engine) as db:
                        publish_pending(db, publish)
                    conn.process_data_events(time_limit=self.interval)
                conn.close()
            except Exception as exc:
                log.warning(
                    "outbox relay: broker unavailable (%s); retrying in %.0fs", exc, backoff
                )
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 60)
