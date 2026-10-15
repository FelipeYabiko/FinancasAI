from datetime import date

import pytest

from app.domain.dates import add_months, add_months_to_month, month_range
from app.domain.dedup import dedup_hash, is_near_duplicate
from app.domain.installments import plan_installments, split_amount
from app.domain.invoices import invoice_due_date, invoice_month
from app.domain.money import cents_to_decimal, format_brl, parse_brl
from app.domain.normalize import normalize_description
from app.domain.recurring import months_to_generate, occurrence_date
from app.domain.summary import expenses_by_category, pct_change, totals


# ---------- invoices ----------
@pytest.mark.parametrize(
    ("purchase", "closing", "expected"),
    [
        (date(2026, 3, 10), 25, "2026-03"),  # before closing
        (date(2026, 3, 25), 25, "2026-03"),  # ON the closing day -> same invoice
        (date(2026, 3, 26), 25, "2026-04"),  # after closing -> next invoice
        (date(2026, 12, 26), 25, "2027-01"),  # year rollover
        (date(2026, 12, 31), 5, "2027-01"),
        (date(2027, 1, 1), 5, "2027-01"),
        (date(2026, 2, 28), 31, "2026-02"),  # closing day clamped to Feb's last day
        (date(2028, 2, 29), 30, "2028-02"),  # leap year
        (date(2026, 2, 28), 27, "2026-03"),
    ],
)
def test_invoice_month(purchase, closing, expected):
    assert invoice_month(purchase, closing) == expected


def test_invoice_due_date():
    # closes 3, due 10 -> same month
    assert invoice_due_date("2026-03", 3, 10) == date(2026, 3, 10)
    # closes 25, due 5 -> following month, with year rollover
    assert invoice_due_date("2026-12", 25, 5) == date(2027, 1, 5)
    assert invoice_due_date("2026-01", 25, 31) == date(2026, 1, 31)


# ---------- installments ----------
@pytest.mark.parametrize("total", [1, 99, 100, 1000, 300000, 299999, 12345, 7])
@pytest.mark.parametrize("n", [1, 2, 3, 7, 10, 12, 24])
def test_split_amount_sums_exactly(total, n):
    parts = split_amount(total, n)
    assert len(parts) == n
    assert sum(parts) == total
    # all but the last are equal; the last absorbs the difference
    assert len(set(parts[:-1])) <= 1
    assert parts[-1] >= parts[0]


def test_split_amount_difference_goes_to_last():
    assert split_amount(10000, 3) == [3333, 3333, 3334]
    assert split_amount(-10000, 3) == [-3333, -3333, -3334]


def test_split_amount_invalid():
    with pytest.raises(ValueError):
        split_amount(100, 0)


def test_plan_installments_consecutive_invoices_across_year():
    plan = plan_installments(300000, 10, date(2026, 11, 28), closing_day=25)
    assert [p.invoice_month for p in plan] == [
        "2026-12", "2027-01", "2027-02", "2027-03", "2027-04",
        "2027-05", "2027-06", "2027-07", "2027-08", "2027-09",
    ]  # fmt: skip
    assert sum(p.amount_cents for p in plan) == 300000
    assert [p.number for p in plan] == list(range(1, 11))
    assert plan[2].date == date(2027, 1, 28)


def test_plan_installments_without_card():
    plan = plan_installments(1000, 3, date(2026, 1, 31), closing_day=None)
    assert [p.invoice_month for p in plan] == [None, None, None]
    assert [p.date for p in plan] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]


# ---------- dates ----------
def test_month_helpers():
    assert add_months_to_month("2026-12", 1) == "2027-01"
    assert add_months_to_month("2026-01", -1) == "2025-12"
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert month_range("2026-11", "2027-02") == ["2026-11", "2026-12", "2027-01", "2027-02"]
    assert month_range("2027-02", "2026-11") == []


# ---------- money ----------
@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("1.234,56", 123456),
        ("R$ 10,00", 1000),
        ("-50,00", -5000),
        ("150,00-", -15000),
        ("R$ -7,5", -750),
        ("- R$ 3,00", -300),
        ("99,90 D", -9990),
        ("99,90 C", 9990),
        ("1000", 100000),
        ("0,01", 1),
    ],
)
def test_parse_brl(text, cents):
    assert parse_brl(text) == cents


def test_parse_brl_invalid():
    with pytest.raises(ValueError):
        parse_brl("abc")


def test_format_brl():
    assert format_brl(123456) == "R$ 1.234,56"
    assert format_brl(-5) == "-R$ 0,05"
    assert cents_to_decimal(-12345) == "-123,45"


# ---------- normalize / dedup ----------
def test_normalize_description():
    assert normalize_description("UBER *TRIP 1234") == "uber trip"
    assert normalize_description("Padaria São João 03/10") == "padaria sao joao"
    assert normalize_description("COMPRA CARTAO  Mercado Bom Preço") == "mercado bom preco"


def test_dedup():
    h1 = dedup_hash(date(2026, 1, 1), -1000, "padaria", 1)
    assert h1 == dedup_hash(date(2026, 1, 1), -1000, "padaria", 1)
    assert h1 != dedup_hash(date(2026, 1, 1), -1000, "padaria", 2)
    d = date(2026, 1, 1)
    assert is_near_duplicate(d, -1000, "padaria sao joao", d, -1000, "padaria s joao")
    assert not is_near_duplicate(d, -1000, "padaria", d, -1001, "padaria")
    assert not is_near_duplicate(d, -1000, "padaria", d, -1000, "uber")


# ---------- recurring ----------
def test_recurring_never_duplicates():
    first = months_to_generate("2026-01", "2026-03", set())
    assert first == ["2026-01", "2026-02", "2026-03"]
    assert months_to_generate("2026-01", "2026-03", set(first)) == []
    assert months_to_generate("2026-01", "2026-04", set(first)) == ["2026-04"]
    assert occurrence_date("2026-02", 31) == date(2026, 2, 28)


# ---------- summary ----------
class T:
    def __init__(self, amount, type_, cat=None):
        self.amount_cents = amount
        self.type = type_
        self.category_id = cat
        self.date = date(2026, 1, 5)
        self.description_normalized = "x"


def test_totals_exclude_transfers_and_handle_refunds():
    txs = [
        T(500000, "income"),
        T(-12000, "expense", 1),
        T(2000, "expense", 1),  # refund
        T(-100000, "transfer"),
        T(100000, "transfer"),
    ]
    t = totals(txs)
    assert t.income_cents == 500000
    assert t.expense_cents == 10000
    assert t.net_cents == 490000
    assert expenses_by_category(txs) == {1: 10000}


def test_pct_change():
    assert pct_change(150, 100) == 50.0
    assert pct_change(100, 0) is None
