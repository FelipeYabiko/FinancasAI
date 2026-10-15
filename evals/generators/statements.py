"""Synthetic bank statement generator (4 layouts, fictional banks) with ground truth.

Usage:
    uv run python -m evals.generators.statements --count 40 --out evals/datasets/extraction

Each statement produces `<id>.pdf` and `<id>.json` (ground truth). Hard cases included on
purpose: descriptions broken across two lines, trailing minus (`150,00-`), refunds, installments
(`03/10`), PIX with person names, dates without year, header/footer repeated on every page and
daily balance rows mixed with transactions.
"""

import argparse
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from app.domain.dates import add_months, clamp_day
from evals.generators.catalog import EMPLOYERS, MERCHANTS, PEOPLE

MONTHS_PT = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
LAYOUTS = {
    "aurora": ("Banco Aurora", "checking_statement"),
    "ipe": ("Cooperativa Ipê", "checking_statement"),
    "lume": ("Lume Card", "credit_card_invoice"),
    "mare": ("Banco Maré", "checking_statement"),
}
HOLDERS = ["FULANO DE TAL SILVA", "BELTRANA SOUZA COSTA", "CICRANO PEREIRA DIAS"]


@dataclass
class GTx:
    date: str
    description: str
    amount_cents: int  # signed, account holder's perspective
    type: str  # income | expense | transfer
    category: str | None = None
    installment_number: int | None = None
    installment_total: int | None = None


@dataclass
class Statement:
    id: str
    layout: str
    bank: str
    document_type: str
    period_start: str
    period_end: str
    holder: str
    opening_balance_cents: int = 0
    due_date: str | None = None
    invoice_month: str | None = None
    transactions: list[GTx] = field(default_factory=list)


# ---------------------------------------------------------------- money formatting
def brl(cents: int, *, sign: str = "lead", currency: bool = False) -> str:
    """Format cents BR-style. sign: lead ("-1.234,56"), trail ("1.234,56-"), none."""
    neg = cents < 0
    integer, dec = divmod(abs(cents), 100)
    s = f"{integer:,}".replace(",", ".") + f",{dec:02d}"
    if currency:
        s = "R$ " + s
    if neg and sign == "lead":
        s = "-" + s
    elif neg and sign == "trail":
        s = s + "-"
    return s


# ---------------------------------------------------------------- transactions
def _rand_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _merchant(rng: random.Random):
    names, cat, (lo, hi) = rng.choice(MERCHANTS)
    return rng.choice(names), cat, rng.randint(lo, hi)


def checking_transactions(rng: random.Random, start: date, end: date, n: int) -> list[GTx]:
    txs: list[GTx] = []
    pay_day = clamp_day(start.year, start.month, rng.choice([1, 5, 10]))
    employer = rng.choice(EMPLOYERS)
    txs.append(
        GTx(
            pay_day.isoformat(),
            f"SALARIO {employer}",
            rng.randint(350000, 1200000),
            "income",
            "Salário",
        )
    )
    while len(txs) < n:
        d = _rand_date(rng, start, end)
        r = rng.random()
        if r < 0.12:
            person = rng.choice(PEOPLE)
            txs.append(
                GTx(
                    d.isoformat(),
                    f"PIX RECEBIDO {person}",
                    rng.randint(2000, 80000),
                    "income",
                    "Outras receitas",
                )
            )
        elif r < 0.27:
            person = rng.choice(PEOPLE)
            txs.append(
                GTx(
                    d.isoformat(),
                    f"PIX ENVIADO {person}",
                    -rng.randint(1500, 60000),
                    "expense",
                    "Outros",
                )
            )
        elif r < 0.31:
            txs.append(
                GTx(
                    d.isoformat(),
                    "PAGAMENTO FATURA CARTAO",
                    -rng.randint(80000, 450000),
                    "transfer",
                    None,
                )
            )
        elif r < 0.34:
            txs.append(
                GTx(
                    d.isoformat(),
                    "RENDIMENTO APLICACAO",
                    rng.randint(500, 9000),
                    "income",
                    "Investimentos",
                )
            )
        else:
            name, cat, amount = _merchant(rng)
            prefix = (
                rng.choice(["COMPRA DEBITO ", "", "PAG BOLETO "])
                if cat in ("Contas e serviços", "Moradia", "Impostos e taxas")
                else rng.choice(["COMPRA DEBITO ", ""])
            )
            txs.append(GTx(d.isoformat(), f"{prefix}{name}".strip(), -amount, "expense", cat))
    txs.sort(key=lambda t: t.date)
    return txs


def card_transactions(rng: random.Random, start: date, end: date, n: int) -> list[GTx]:
    txs: list[GTx] = []
    # payment of the previous invoice
    pay = _rand_date(rng, start, start + timedelta(days=10))
    txs.append(
        GTx(
            pay.isoformat(),
            "PAGAMENTO RECEBIDO OBRIGADO",
            rng.randint(80000, 400000),
            "transfer",
            None,
        )
    )
    while len(txs) < n:
        d = _rand_date(rng, start, end)
        r = rng.random()
        if r < 0.15:
            m = rng.choice([m for m in MERCHANTS if m[1] in ("Compras", "Viagem", "Educação")])
            name = m[0][0]
            total = rng.randint(6, 12) * rng.randint(5000, 40000)
            parts = rng.randint(3, 12)
            k = rng.randint(1, parts)
            amount = total // parts
            # original purchase date shown (k-1 months before)
            orig = add_months(d, -(k - 1))
            txs.append(GTx(orig.isoformat(), name, -amount, "expense", m[1], k, parts))
        elif r < 0.22 and txs:
            name, cat, amount = _merchant(rng)
            txs.append(GTx(d.isoformat(), f"ESTORNO {name}", amount, "expense", cat))
        else:
            name, cat, amount = _merchant(rng)
            txs.append(GTx(d.isoformat(), name, -amount, "expense", cat))
    txs.sort(key=lambda t: t.date)
    return txs


def make_statement(idx: int, layout: str, rng: random.Random) -> Statement:
    bank, doc_type = LAYOUTS[layout]
    year = rng.choice([2025, 2026])
    month = rng.randint(1, 12)
    n = rng.randint(15, 60)
    holder = rng.choice(HOLDERS)
    sid = f"{layout}_{idx:03d}"
    if doc_type == "credit_card_invoice":
        closing_day = rng.choice([3, 8, 15, 25])
        end = clamp_day(year, month, closing_day)
        start = add_months(end, -1) + timedelta(days=1)
        due = end + timedelta(days=7)
        st = Statement(sid, layout, bank, doc_type, start.isoformat(), end.isoformat(), holder,
                       due_date=due.isoformat(), invoice_month=f"{end.year:04d}-{end.month:02d}")  # fmt: skip
        st.transactions = card_transactions(rng, start, end, n)
    else:
        start = date(year, month, 1)
        end = clamp_day(year, month, 31)
        st = Statement(sid, layout, bank, doc_type, start.isoformat(), end.isoformat(), holder,
                       opening_balance_cents=rng.randint(-50000, 900000))  # fmt: skip
        st.transactions = checking_transactions(rng, start, end, n)
    return st


# ---------------------------------------------------------------- rendering helpers
class Page:
    """Small wrapper around reportlab's canvas with a row cursor."""

    W, H = A4

    def __init__(self, path: Path, header, footer, top=720, bottom=70, step=14):
        self.c = Canvas(str(path), pagesize=A4)
        self.c.setTitle("Extrato")
        self.header, self.footer = header, footer
        self.top, self.bottom, self.step = top, bottom, step
        self.page = 1
        self.y = 0
        self._start()

    def _start(self):
        self.header(self.c, self.page)
        self.y = self.top

    def need(self, rows: int = 1):
        if self.y - rows * self.step < self.bottom:
            self.footer(self.c, self.page)
            self.c.showPage()
            self.page += 1
            self._start()

    def text(self, x, s, font="Helvetica", size=9, right=False):
        self.c.setFont(font, size)
        (self.c.drawRightString if right else self.c.drawString)(x, self.y, s)

    def nl(self):
        self.y -= self.step

    def save(self):
        self.footer(self.c, self.page)
        self.c.save()


def _split_desc(rng: random.Random, desc: str, max_first: int = 18) -> list[str]:
    """Sometimes break a description into two printed lines (hard case)."""
    if len(desc) > max_first + 4 and rng.random() < 0.45:
        cut = desc.rfind(" ", 0, max_first + 6)
        if cut > 4:
            return [desc[:cut], desc[cut + 1 :]]
    return [desc]


def _ddmm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


# ---------------------------------------------------------------- layout: Banco Aurora
def render_aurora(st: Statement, path: Path, rng: random.Random) -> None:
    def header(c, page):
        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, 800, "BANCO AURORA S.A.")
        c.setFont("Helvetica", 9)
        c.drawString(40, 786, f"Extrato de Conta Corrente  |  Cliente: {st.holder}")
        c.drawString(
            40,
            774,
            f"Agência 0123  Conta 45678-9  |  Período: {_br(st.period_start)} a {_br(st.period_end)}",
        )
        c.setFont("Helvetica-Bold", 9)
        c.drawString(40, 745, "Data")
        c.drawString(110, 745, "Histórico")
        c.drawRightString(470, 745, "Valor (R$)")
        c.drawRightString(555, 745, "Saldo (R$)")
        c.line(40, 740, 555, 740)

    def footer(c, page):
        c.setFont("Helvetica", 7)
        c.drawString(40, 40, "Banco Aurora S.A. - SAC 0800 000 0000 - Ouvidoria 0800 000 0001")
        c.drawRightString(555, 40, f"Página {page}")

    p = Page(path, header, footer)
    bal = st.opening_balance_cents
    p.text(110, "SALDO ANTERIOR")
    p.text(555, brl(bal), right=True)
    p.nl()
    by_day: dict[str, list[GTx]] = {}
    for t in st.transactions:
        by_day.setdefault(t.date, []).append(t)
    for day, txs in by_day.items():
        for t in txs:
            p.need()
            bal += t.amount_cents
            p.text(40, _br(day))
            p.text(110, t.description)
            p.text(470, brl(t.amount_cents), right=True)
            p.nl()
        p.need()
        p.text(110, "SALDO DO DIA", font="Helvetica-Oblique")
        p.text(555, brl(bal), right=True)
        p.nl()
    p.save()


# ---------------------------------------------------------------- layout: Cooperativa Ipê
def render_ipe(st: Statement, path: Path, rng: random.Random) -> None:
    year = st.period_end[:4]

    def header(c, page):
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, 805, "COOPERATIVA DE CRÉDITO IPÊ")
        c.setFont("Helvetica", 9)
        c.drawString(40, 790, f"EXTRATO DE CONTA  -  Associado: {st.holder}")
        c.drawString(
            40, 778, f"Movimentação de {_ddmm(st.period_start)} a {_ddmm(st.period_end)}/{year}"
        )
        c.setFont("Courier-Bold", 9)
        c.drawString(40, 745, "DATA   LANÇAMENTO")
        c.drawRightString(520, 745, "VALOR")

    def footer(c, page):
        c.setFont("Courier", 7)
        c.drawString(40, 45, f"Cooperativa Ipê - extrato emitido para {st.holder} - folha {page}")

    p = Page(path, header, footer)
    for t in st.transactions:
        lines = _split_desc(rng, t.description)
        p.need(len(lines))
        p.text(40, _ddmm(t.date), font="Courier")
        p.text(95, lines[0], font="Courier")
        p.text(
            520,
            brl(t.amount_cents, sign="trail") if t.amount_cents < 0 else brl(t.amount_cents) + " ",
            font="Courier",
            right=True,
        )
        p.nl()
        for extra in lines[1:]:
            p.text(95, extra, font="Courier")
            p.nl()
    p.save()


# ---------------------------------------------------------------- layout: Lume Card (invoice)
def render_lume(st: Statement, path: Path, rng: random.Random) -> None:
    total = -sum(t.amount_cents for t in st.transactions if t.type != "transfer")

    def header(c, page):
        c.setFont("Helvetica-Bold", 18)
        c.drawString(40, 800, "lume card")
        c.setFont("Helvetica", 9)
        c.drawString(40, 784, f"FATURA DO CARTÃO  -  Titular: {st.holder}  -  Cartão final 4321")
        c.drawString(
            40,
            772,
            f"Fechamento: {_br(st.period_end)}    Vencimento: {_br(st.due_date)}    Total da fatura: R$ {brl(total)}",
        )
        c.setFont("Helvetica-Bold", 8)
        c.drawString(40, 745, "DATA")
        c.drawString(90, 745, "DESCRIÇÃO")
        c.drawString(400, 745, "PARCELA")
        c.drawRightString(555, 745, "VALOR R$")

    def footer(c, page):
        c.setFont("Helvetica", 7)
        c.drawString(
            40, 45, "Lume Card - Central de atendimento 4000-0000 - Pagamento mínimo: 15% do total"
        )
        c.drawRightString(555, 45, f"{page}")

    p = Page(path, header, footer)
    for t in st.transactions:
        lines = _split_desc(rng, t.description, max_first=22)
        p.need(len(lines))
        p.text(40, f"{t.date[8:10]} {MONTHS_PT[int(t.date[5:7]) - 1]}", size=8)
        p.text(90, lines[0], size=8)
        if t.installment_total:
            p.text(400, f"{t.installment_number:02d}/{t.installment_total:02d}", size=8)
        # invoice layout: purchases positive, credits negative
        p.text(555, brl(-t.amount_cents), size=8, right=True)
        p.nl()
        for extra in lines[1:]:
            p.text(90, extra, size=8)
            p.nl()
    p.save()


# ---------------------------------------------------------------- layout: Banco Maré
def render_mare(st: Statement, path: Path, rng: random.Random) -> None:
    def header(c, page):
        c.setFont("Helvetica-Bold", 15)
        c.drawString(40, 805, "Banco Maré")
        c.setFont("Helvetica", 9)
        c.drawString(
            40,
            790,
            f"Extrato mensal  ·  {st.holder}  ·  {_br(st.period_start)} - {_br(st.period_end)}",
        )
        c.setFont("Helvetica-Bold", 8)
        c.drawString(40, 745, "Data")
        c.drawString(95, 745, "Descrição")
        c.drawRightString(400, 745, "Entradas")
        c.drawRightString(475, 745, "Saídas")
        c.drawRightString(555, 745, "Saldo")

    def footer(c, page):
        c.setFont("Helvetica", 7)
        c.drawString(40, 45, "Banco Maré S.A. · documento sem valor fiscal")
        c.drawRightString(555, 45, f"pág. {page}")

    p = Page(path, header, footer)
    bal = st.opening_balance_cents
    p.text(95, "Saldo inicial", size=8)
    p.text(555, brl(bal, currency=True), size=8, right=True)
    p.nl()
    last_day = None
    for t in st.transactions:
        if last_day and t.date != last_day and rng.random() < 0.5:
            p.need()
            p.text(95, f"SALDO EM {_br(last_day)}", size=8)
            p.text(555, brl(bal, currency=True), size=8, right=True)
            p.nl()
        last_day = t.date
        p.need()
        bal += t.amount_cents
        d = t.date
        p.text(40, f"{d[8:10]}/{d[5:7]}/{d[2:4]}", size=8)
        p.text(95, t.description.title() if rng.random() < 0.5 else t.description, size=8)
        if t.amount_cents > 0:
            p.text(400, brl(t.amount_cents, currency=True), size=8, right=True)
        else:
            p.text(475, brl(-t.amount_cents, currency=True), size=8, right=True)
        p.text(555, brl(bal, currency=True), size=8, right=True)
        p.nl()
    p.save()


def _br(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


RENDERERS = {"aurora": render_aurora, "ipe": render_ipe, "lume": render_lume, "mare": render_mare}


def generate(count: int, out: Path, seed: int = 42) -> list[Statement]:
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    layouts = list(LAYOUTS)
    statements = []
    for i in range(count):
        layout = layouts[i % len(layouts)]
        st = make_statement(i, layout, rng)
        RENDERERS[layout](st, out / f"{st.id}.pdf", random.Random(seed * 1000 + i))
        (out / f"{st.id}.json").write_text(json.dumps(asdict(st), ensure_ascii=False, indent=1))
        statements.append(st)
    return statements


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--out", type=Path, default=Path("evals/datasets/extraction"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    sts = generate(args.count, args.out, args.seed)
    n = sum(len(s.transactions) for s in sts)
    print(f"generated {len(sts)} statements / {n} transactions in {args.out}")


if __name__ == "__main__":
    main()
