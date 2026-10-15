"""Create a demo database with ~4 months of realistic (synthetic) data.

DATABASE_URL=sqlite:///data/demo.db uv run python -m scripts.seed_demo
login: demo / demo1234
"""

import random
from datetime import date

from sqlmodel import Session, select

from app.db import engine, init_db
from app.domain.dates import add_months, clamp_day, month_key, today
from app.models import Account, Budget, Category, Goal, RecurringRule, User
from app.schemas.api import InstallmentPurchaseIn, TransactionIn
from app.services import ledger
from app.services.auth import create_user
from app.services.recurring import run_recurring
from evals.generators.catalog import MERCHANTS, PEOPLE


def main(seed: int = 3) -> None:
    init_db()
    rng = random.Random(seed)
    with Session(engine) as db:
        if db.exec(select(User)).first():
            raise SystemExit("database is not empty; point DATABASE_URL to a new file")
        create_user(db, "Demo", "demo", "demo1234")
        cats = {c.name: c.id for c in db.exec(select(Category))}
        checking = Account(
            name="Conta Aurora", type="checking", initial_balance_cents=350000, color="#4f46e5"
        )
        card = Account(
            name="Lume Card", type="credit_card", closing_day=25, due_day=5, color="#db2777"
        )
        cash = Account(name="Carteira", type="cash", initial_balance_cents=15000, color="#16a34a")
        db.add_all([checking, card, cash])
        db.commit()
        start = month_key(add_months(today(), -3)) + "-01"
        for rule in (
            RecurringRule(
                description="Salário Empresa Alfa",
                amount_cents=820000,
                type="income",
                category_id=cats["Salário"],
                account_id=checking.id,
                day_of_month=5,
                start_month=start[:7],
            ),
            RecurringRule(
                description="Aluguel",
                amount_cents=210000,
                type="expense",
                category_id=cats["Moradia"],
                account_id=checking.id,
                day_of_month=10,
                start_month=start[:7],
            ),
            RecurringRule(
                description="NETFLIX.COM",
                amount_cents=5590,
                type="expense",
                category_id=cats["Assinaturas"],
                account_id=card.id,
                day_of_month=12,
                start_month=start[:7],
            ),
            RecurringRule(
                description="SPOTIFY BRASIL",
                amount_cents=2190,
                type="expense",
                category_id=cats["Assinaturas"],
                account_id=card.id,
                day_of_month=3,
                start_month=start[:7],
            ),
        ):
            db.add(rule)
        db.commit()
        run_recurring(db)
        t = today()
        everyday = [
            m
            for m in MERCHANTS
            if m[1] in ("Mercado", "Delivery", "Restaurantes", "Transporte", "Saúde", "Lazer")
        ]
        for back in range(3, -1, -1):
            base = add_months(t, -back)
            last_day = t.day if back == 0 else clamp_day(base.year, base.month, 31).day
            boost = (
                1.6 if back == 0 else 1.0
            )  # make "Delivery" spike this month for the insights demo
            for _ in range(rng.randint(28, 38) if back else max(6, t.day)):
                names, cat, (lo, hi) = rng.choice(everyday)
                amount = rng.randint(lo, hi // 2) if hi > 20000 else rng.randint(lo, hi)
                if cat == "Delivery":
                    amount = int(amount * boost)
                ledger.create_transaction(
                    db,
                    TransactionIn(
                        date=date(base.year, base.month, rng.randint(1, last_day)),
                        description=names[0],
                        amount_cents=amount,
                        type="expense",
                        account_id=rng.choice([card.id, card.id, checking.id]),
                        category_id=cats[cat],
                    ),
                )
            for _ in range(2):
                ledger.create_transaction(
                    db,
                    TransactionIn(
                        date=date(base.year, base.month, rng.randint(1, last_day)),
                        description=f"PIX ENVIADO {rng.choice(PEOPLE)}",
                        amount_cents=rng.randint(3000, 25000),
                        type="expense",
                        account_id=checking.id,
                        category_id=cats["Outros"],
                    ),
                )
        ledger.create_installment_purchase(
            db,
            InstallmentPurchaseIn(
                date=add_months(t, -2),
                description="ELETRO CENTER ONLINE TV",
                total_cents=329900,
                installments=10,
                account_id=card.id,
                category_id=cats["Compras"],
            ),
        )
        for name, limit in (
            ("Mercado", 160000),
            ("Delivery", 60000),
            ("Restaurantes", 50000),
            ("Transporte", 45000),
        ):
            db.add(Budget(category_id=cats[name], month=month_key(t), limit_cents=limit))
        db.add(Goal(name="Reserva de emergência", target_cents=3000000, current_cents=1180000))
        db.add(
            Goal(
                name="Viagem de férias",
                target_cents=800000,
                current_cents=210000,
                deadline=date(t.year + 1, 1, 15),
            )
        )
        db.commit()
    print("demo database ready — login: demo / demo1234")


if __name__ == "__main__":
    main()
