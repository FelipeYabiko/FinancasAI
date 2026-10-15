from datetime import date

from sqlmodel import select

from app.domain.dates import month_key, today
from app.models import CategoryMemory, RecurringRule, Transaction
from app.services.recurring import run_recurring


# ---------- auth ----------
def test_auth_flow(anon_client):
    assert anon_client.get("/api/auth/status").json()["needs_setup"] is True
    assert anon_client.get("/api/accounts").status_code == 401
    r = anon_client.post(
        "/api/auth/setup", json={"name": "Ana", "username": "Ana", "password": "segredo123"}
    )
    assert r.status_code == 200
    # second setup is refused
    assert (
        anon_client.post(
            "/api/auth/setup", json={"name": "X", "username": "xx", "password": "segredo123"}
        ).status_code
        == 409
    )
    # writes without CSRF header are refused
    assert anon_client.post("/api/accounts", json={"name": "A", "type": "cash"}).status_code == 403
    csrf = anon_client.cookies["fia_csrf"]
    r = anon_client.post(
        "/api/accounts", json={"name": "A", "type": "cash"}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 201
    # logout then login again
    assert anon_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    anon_client.cookies.clear()
    assert anon_client.get("/api/accounts").status_code == 401
    bad = anon_client.post("/api/auth/login", json={"username": "ana", "password": "errada"})
    assert bad.status_code == 401
    ok = anon_client.post("/api/auth/login", json={"username": "ANA", "password": "segredo123"})
    assert ok.status_code == 200
    assert anon_client.get("/api/accounts").status_code == 200


def test_users_management(client):
    r = client.post("/api/users", json={"name": "Bia", "username": "bia", "password": "123456"})
    assert r.status_code == 201
    assert len(client.get("/api/users").json()) == 2
    me = client.get("/api/auth/status").json()["user"]["id"]
    assert client.delete(f"/api/users/{me}").status_code == 400
    assert client.delete(f"/api/users/{r.json()['id']}").status_code == 200


# ---------- accounts ----------
def test_credit_card_requires_days(client):
    r = client.post("/api/accounts", json={"name": "C", "type": "credit_card"})
    assert r.status_code == 422


# ---------- transactions ----------
def test_transaction_crud_and_invoice(client, accounts, categories):
    card = accounts["card"]["id"]
    r = client.post(
        "/api/transactions",
        json={
            "date": "2026-12-26",
            "description": "Mercado Bom Preço",
            "amount_cents": 15990,
            "type": "expense",
            "account_id": card,
            "category_id": categories["Mercado"],
        },
    )
    assert r.status_code == 201
    tx = r.json()
    assert tx["amount_cents"] == -15990
    assert tx["invoice_month"] == "2027-01"  # after closing day 25 + year rollover
    # edit date moves invoice
    r = client.patch(f"/api/transactions/{tx['id']}", json={"date": "2026-12-20"})
    assert r.json()["invoice_month"] == "2026-12"
    # category correction teaches the memory
    client.patch(f"/api/transactions/{tx['id']}", json={"category_id": categories["Compras"]})
    mem = client.get("/api/category-memory").json()
    assert mem[0]["description_normalized"] == "mercado bom preco"
    assert mem[0]["category_id"] == categories["Compras"]
    # refund flag stores a positive expense
    r = client.patch(f"/api/transactions/{tx['id']}", json={"is_refund": True})
    assert r.json()["amount_cents"] == 15990
    assert client.delete(f"/api/transactions/{tx['id']}").json() == {"deleted": 1}


def test_filters_and_stats(client, accounts, categories):
    acc = accounts["checking"]["id"]
    for d, desc, amt, t in [
        ("2026-05-01", "Salário", 500000, "income"),
        ("2026-05-03", "iFood pedido", 4590, "expense"),
        ("2026-05-04", "Uber viagem", 2300, "expense"),
        ("2026-06-01", "iFood pedido", 6000, "expense"),
    ]:
        client.post(
            "/api/transactions",
            json={
                "date": d,
                "description": desc,
                "amount_cents": amt,
                "type": t,
                "account_id": acc,
                "tags": ["casa"] if "Uber" in desc else [],
            },
        )
    page = client.get("/api/transactions", params={"month": "2026-05"}).json()
    assert page["total"] == 3
    assert page["stats"]["income_cents"] == 500000
    assert page["stats"]["expense_cents"] == 6890
    assert client.get("/api/transactions", params={"q": "ifood"}).json()["total"] == 2
    assert client.get("/api/transactions", params={"min_cents": 5000}).json()["total"] == 2
    assert client.get("/api/transactions", params={"tag": "casa"}).json()["total"] == 1
    r = client.get("/api/transactions", params={"date_from": "2026-05-02", "date_to": "2026-05-31"})
    assert r.json()["total"] == 2
    assert client.get("/api/transactions", params={"type": "income"}).json()["total"] == 1


def test_installments_exact_and_group_delete(client, accounts):
    card = accounts["card"]["id"]
    r = client.post(
        "/api/transactions/installments",
        json={
            "date": "2026-11-28",
            "description": "TV",
            "total_cents": 299999,
            "installments": 10,
            "account_id": card,
        },
    )
    assert r.status_code == 201
    items = r.json()
    assert len(items) == 10
    assert sum(i["amount_cents"] for i in items) == -299999
    assert items[0]["invoice_month"] == "2026-12"
    assert items[-1]["invoice_month"] == "2027-09"
    assert items[-1]["description"] == "TV (10/10)"
    assert len({i["installment_group_id"] for i in items}) == 1
    # deleting one installment only
    assert client.delete(f"/api/transactions/{items[0]['id']}").json() == {"deleted": 1}
    # deleting the whole group
    r = client.delete(f"/api/transactions/{items[1]['id']}", params={"whole_group": True})
    assert r.json() == {"deleted": 9}


def test_transfers_out_of_totals(client, accounts):
    checking, card = accounts["checking"]["id"], accounts["card"]["id"]
    month = month_key(today())
    d = today().isoformat()
    client.post(
        "/api/transactions",
        json={
            "date": d,
            "description": "Salário",
            "amount_cents": 300000,
            "type": "income",
            "account_id": checking,
        },
    )
    r = client.post(
        "/api/transactions/transfers",
        json={"date": d, "from_account_id": checking, "to_account_id": card, "amount_cents": 50000},
    )
    assert r.status_code == 201
    pair = r.json()
    assert {p["amount_cents"] for p in pair} == {-50000, 50000}
    assert pair[0]["transfer_pair_id"] == pair[1]["transfer_pair_id"]
    dash = client.get("/api/dashboard", params={"month": month}).json()
    assert dash["income_cents"] == 300000
    assert dash["expense_cents"] == 0
    balances = {a["id"]: a["balance_cents"] for a in dash["accounts"]}
    assert balances[checking] == 100000 + 300000 - 50000
    assert balances[card] == 50000
    # deleting one side deletes the pair
    assert client.delete(f"/api/transactions/{pair[0]['id']}").json() == {"deleted": 2}
    assert (
        client.post(
            "/api/transactions/transfers",
            json={"date": d, "from_account_id": card, "to_account_id": card, "amount_cents": 1},
        ).status_code
        == 422
    )


# ---------- recurring ----------
def test_recurring_no_duplicates(client, accounts, db, categories):
    acc = accounts["checking"]["id"]
    r = client.post(
        "/api/recurring",
        json={
            "description": "Aluguel",
            "amount_cents": 180000,
            "type": "expense",
            "account_id": acc,
            "category_id": categories["Moradia"],
            "day_of_month": 31,
            "start_month": "2026-01",
        },
    )
    assert r.status_code == 201
    on = date(2026, 4, 15)
    run_recurring(db, on=on)
    run_recurring(db, on=on)
    txs = db.exec(select(Transaction).where(Transaction.recurring_rule_id == r.json()["id"])).all()
    months = sorted(t.recurring_month for t in txs)
    assert months[:4] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert len(months) == len(set(months))
    feb = next(t for t in txs if t.recurring_month == "2026-02")
    assert feb.date == date(2026, 2, 28)
    assert feb.amount_cents == -180000
    before = len(txs)
    client.post("/api/recurring/run")
    client.post("/api/recurring/run")
    after = db.exec(select(Transaction).where(Transaction.recurring_rule_id == r.json()["id"]))
    assert len(after.all()) >= before
    # inactive rules don't generate
    rule = db.get(RecurringRule, r.json()["id"])
    rule.active = False
    db.add(rule)
    db.commit()
    assert run_recurring(db, on=date(2030, 1, 1)) == []


# ---------- budgets / goals ----------
def test_budget_status(client, accounts, categories):
    acc = accounts["checking"]["id"]
    month = "2026-05"
    client.put(
        "/api/budgets",
        json={"category_id": categories["Delivery"], "month": month, "limit_cents": 10000},
    )
    client.post(
        "/api/transactions",
        json={
            "date": "2026-05-10",
            "description": "iFood",
            "amount_cents": 8500,
            "type": "expense",
            "account_id": acc,
            "category_id": categories["Delivery"],
        },
    )
    b = client.get("/api/budgets", params={"month": month}).json()[0]
    assert b["spent_cents"] == 8500
    assert b["status"] == "warning"
    # upsert updates the same budget
    b2 = client.put(
        "/api/budgets",
        json={"category_id": categories["Delivery"], "month": month, "limit_cents": 8000},
    ).json()
    assert b2["id"] == b["id"]
    assert b2["status"] == "exceeded"
    assert client.post(
        "/api/budgets/copy", params={"from_month": month, "to_month": "2026-06"}
    ).json() == {"copied": 1}


def test_goals(client):
    g = client.post("/api/goals", json={"name": "Viagem", "target_cents": 500000}).json()
    g = client.patch(f"/api/goals/{g['id']}", json={"current_cents": 125000}).json()
    assert g["percent"] == 25.0


# ---------- dashboard ----------
def test_dashboard_open_invoices(client, accounts):
    card = accounts["card"]["id"]
    d = today()
    client.post(
        "/api/transactions",
        json={
            "date": d.isoformat(),
            "description": "Livraria",
            "amount_cents": 8000,
            "type": "expense",
            "account_id": card,
        },
    )
    dash = client.get("/api/dashboard").json()
    assert len(dash["last_6_months"]) == 6
    assert dash["open_invoices"][0]["amount_cents"] == 8000
    assert dash["top_merchants"][0]["name"] == "livraria"
    assert sum(w["amount_cents"] for w in dash["by_weekday"]) == 8000


# ---------- backup ----------
def test_backup_roundtrip(client, accounts, categories, db):
    acc = accounts["checking"]["id"]
    client.post(
        "/api/transactions",
        json={
            "date": "2026-05-10",
            "description": "Padaria",
            "amount_cents": 1250,
            "type": "expense",
            "account_id": acc,
            "category_id": categories["Mercado"],
            "tags": ["café"],
        },
    )
    db.add(CategoryMemory(description_normalized="padaria", category_id=categories["Mercado"]))
    db.commit()
    dump = client.get("/api/backup/json")
    assert dump.status_code == 200
    data = dump.json()
    assert len(data["transactions"]) == 1
    # wipe by restoring an empty-ish backup, then restore the original
    empty = {**data, "transactions": [], "budgets": [], "category_memory": []}
    files = {"file": ("b.json", __import__("json").dumps(empty), "application/json")}
    assert client.post("/api/backup/json", files=files).status_code == 200
    assert client.get("/api/transactions").json()["total"] == 0
    files = {"file": ("b.json", dump.content, "application/json")}
    r = client.post("/api/backup/json", files=files)
    assert r.json()["restored"]["transactions"] == 1
    tx = client.get("/api/transactions").json()["items"][0]
    assert tx["tags"] == ["café"]
    assert (
        client.post(
            "/api/backup/json", files={"file": ("x.json", "{}", "application/json")}
        ).status_code
        == 400
    )
    csv = client.get("/api/backup/csv").text
    assert "Padaria" in csv
    assert "-12,50" in csv


def test_delete_category_uncategorizes(client, accounts):
    cat = client.post("/api/categories", json={"name": "Temp", "kind": "expense"}).json()
    tx = client.post(
        "/api/transactions",
        json={
            "date": "2026-05-10",
            "description": "x",
            "amount_cents": 100,
            "type": "expense",
            "account_id": accounts["checking"]["id"],
            "category_id": cat["id"],
        },
    ).json()
    assert client.delete(f"/api/categories/{cat['id']}").status_code == 200
    assert client.get(f"/api/transactions/{tx['id']}").json()["category_id"] is None
    # accounts with transactions can't be deleted
    assert client.delete(f"/api/accounts/{accounts['checking']['id']}").status_code == 400
