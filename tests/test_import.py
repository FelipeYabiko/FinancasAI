import io
import json
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from app.llm.client import LLMClient
from app.llm.providers import register_provider
from app.llm.providers.fake import FakeProvider
from app.services.importer.baseline import parse_lines
from app.services.importer.categorize import CatItem, categorize
from app.services.importer.chunking import chunk_lines, strip_repeated_boilerplate
from app.services.importer.detect import detect_document
from app.services.importer.pdf_text import PdfTextError, extract_pdf_text

DATA = Path(__file__).resolve().parent.parent / "evals" / "datasets" / "extraction"
FEATURES = ("extraction", "categorization", "assistant", "insights")


def pdf_bytes(name: str) -> bytes:
    return (DATA / name).read_bytes()


# ---------- step 1: text ----------
def test_pdf_text_preserves_columns():
    t = extract_pdf_text(pdf_bytes("mare_003.pdf"))
    line = next(ln for ln in t.lines if "SALARIO" in ln)
    # income sits in the "Entradas" column, left of where the "Saídas" amounts are
    out_line = next(ln for ln in t.lines if "NETFLIX" in ln.upper())
    assert line.index("R$") < out_line.index("R$")


def test_scanned_pdf_rejected():
    buf = io.BytesIO()
    c = Canvas(buf)
    c.rect(100, 100, 200, 200, fill=1)  # graphics only, no text
    c.save()
    with pytest.raises(PdfTextError, match="OCR"):
        extract_pdf_text(buf.getvalue())


def test_not_a_pdf():
    with pytest.raises(PdfTextError):
        extract_pdf_text(b"hello")


# ---------- step 2: detection ----------
@pytest.mark.parametrize(
    ("name", "bank", "doc"),
    [
        ("aurora_000.pdf", "Banco Aurora", "checking_statement"),
        ("ipe_001.pdf", "Cooperativa Ipê", "checking_statement"),
        ("lume_002.pdf", "Lume Card", "credit_card_invoice"),
        ("mare_003.pdf", "Banco Maré", "checking_statement"),
    ],
)
def test_detect(name, bank, doc):
    gt = json.loads((DATA / name.replace(".pdf", ".json")).read_text())
    info = detect_document(extract_pdf_text(pdf_bytes(name)).lines)
    assert (info.bank, info.document_type) == (bank, doc)
    assert info.period_end.isoformat() == gt["period_end"]
    if doc == "credit_card_invoice":
        assert info.invoice_month == gt["invoice_month"]


# ---------- step 3: chunking ----------
def test_chunks_never_cut_lines_and_prefer_date_boundaries():
    lines = []
    for i in range(200):
        lines.append(f"{i % 28 + 1:02d}/01 COMPRA LOJA {i}        10,00-")
        if i % 3 == 0:
            lines.append("CONTINUACAO DA DESCRICAO")
    res = chunk_lines(lines, max_tokens=120)
    assert sum(len(c) for c in res.chunks) == len(lines)  # nothing dropped
    assert [ln for c in res.chunks for ln in c] == lines  # order kept, lines intact
    for c in res.chunks[1:]:
        assert c[0][0].isdigit()  # each chunk starts on a transaction, not a continuation


def test_chunk_limit_warns():
    res = chunk_lines([f"{i:02d}/01 X {'y' * 200}" for i in range(400)], max_tokens=60)
    assert any("NÃO foram processados" in w for w in res.warnings)


def test_boilerplate_removed_only_on_repeat():
    pages = [["BANCO X", "Data Hist Valor", "01/01 A 10,00", "pag 1"],
             ["BANCO X", "Data Hist Valor", "02/01 B 10,00", "pag 2"]]  # fmt: skip
    out, removed = strip_repeated_boilerplate(pages)
    assert out[1] == ["02/01 B 10,00"]
    assert "01/01 A 10,00" in out[0]
    assert removed >= 3  # header lines of page 2 + page footers


# ---------- baseline ----------
def test_baseline_parser_trailing_sign_and_saldo():
    rows = parse_lines(
        ["  03/09   PADARIA PAO   15,99-", "   SALDO DO DIA    100,00", "04/09  SALARIO  1.000,00"],
        2026,
    )
    assert [(r["date"], r["amount_cents"], r["type"]) for r in rows] == [
        ("2026-09-03", -1599, "expense"), ("2026-09-04", 100000, "income"),
    ]  # fmt: skip


# ---------- step 5: categorization ----------
def test_categorize_memory_first_then_llm():
    cats = [(1, "Mercado", "expense"), (2, "Delivery", "expense"), (3, "Salário", "income")]
    fake = FakeProvider(
        script=[
            {"items": [{"index": 0, "category": "delivery"}, {"index": 1, "category": "Inventada"}]}
        ]
    )
    register_provider("fake", fake)
    items = [
        CatItem("PADARIA PAO DOURADO 03/10", "expense"),
        CatItem("IFOOD *PIZZA", "expense"),
        CatItem("LOJA QUALQUER", "expense"),
        CatItem("PAGAMENTO FATURA", "transfer"),
    ]
    run = categorize(items, cats, {"padaria pao dourado": 1}, LLMClient(), "fake", "fake")
    assert [(r.category_id, r.source) for r in run.results] == [
        (1, "memory"), (2, "llm"), (None, "none"), (None, "none"),
    ]  # fmt: skip
    assert len(fake.calls) == 1
    assert "PADARIA" not in fake.calls[0]["messages"][1]["content"]  # memory hit never sent


# ---------- end-to-end via API (offline fake provider) ----------
@pytest.fixture
def ai_fake(client):
    client.put(
        "/api/ai/settings", json={f: {"provider": "fake", "model": "fake"} for f in FEATURES}
    )


def test_import_flow_dedup_and_undo(client, accounts, ai_fake):
    acc = accounts["checking"]["id"]
    gt = json.loads((DATA / "aurora_000.json").read_text())
    files = {"file": ("aurora_000.pdf", pdf_bytes("aurora_000.pdf"), "application/pdf")}
    r = client.post("/api/import/preview", files=files, data={"account_id": acc})
    assert r.status_code == 200, r.text
    prev = r.json()
    assert prev["bank"] == "Banco Aurora"
    assert len(prev["rows"]) == len(gt["transactions"])
    assert all(row["selected"] for row in prev["rows"])
    assert prev["stats"]["llm_calls"] >= 1

    # user fixes one category during review → memory learns it
    rows = prev["rows"]
    cats = {c["name"]: c["id"] for c in client.get("/api/categories").json()}
    rows[1]["category_id"] = cats["Lazer"]
    rows[2]["selected"] = False
    r = client.post(f"/api/import/{prev['batch_id']}/commit", json={"rows": rows})
    res = r.json()
    assert res["imported"] == len(rows) - 1
    assert res["skipped"] == 1
    assert res["latest_month"] == gt["period_end"][:7]
    mem = client.get("/api/category-memory").json()
    assert any(m["category_id"] == cats["Lazer"] for m in mem)
    first_batch = prev["batch_id"]

    # re-importing the same file: everything already imported is flagged as duplicate
    prev2 = client.post("/api/import/preview", files=files, data={"account_id": acc}).json()
    dups = [row for row in prev2["rows"] if row["duplicate"] == "db"]
    assert len(dups) == len(rows) - 1
    assert not any(row["selected"] for row in dups)
    res2 = client.post(
        f"/api/import/{prev2['batch_id']}/commit", json={"rows": prev2["rows"]}
    ).json()
    assert res2["imported"] == 1  # only the row unchecked the first time

    # undo the first import
    assert client.post(f"/api/import/{first_batch}/undo").json()["deleted"] == len(rows) - 1
    assert (
        client.get("/api/transactions", params={"import_batch_id": first_batch}).json()["total"]
        == 0
    )
    batches = client.get("/api/import/batches").json()
    assert {b["status"] for b in batches} == {"undone", "committed"}
    assert client.post(f"/api/import/{first_batch}/undo").status_code == 400


def test_import_card_invoice_uses_statement_invoice_month(client, accounts, ai_fake):
    card = accounts["card"]["id"]
    gt = json.loads((DATA / "aurora_000.json").read_text())
    files = {"file": ("a.pdf", pdf_bytes("aurora_000.pdf"), "application/pdf")}
    prev = client.post("/api/import/preview", files=files, data={"account_id": card}).json()
    assert any("conta" in w for w in prev["warnings"])  # checking statement into a card account
    res = client.post(
        f"/api/import/{prev['batch_id']}/commit",
        json={"rows": prev["rows"][:3], "invoice_month": "2030-01"},
    ).json()
    items = client.get("/api/transactions", params={"import_batch_id": res["batch_id"]}).json()[
        "items"
    ]
    assert {t["invoice_month"] for t in items} == {"2030-01"}
    assert gt


def test_import_rejects_non_pdf(client, accounts, ai_fake):
    files = {"file": ("x.pdf", b"not a pdf", "application/pdf")}
    r = client.post(
        "/api/import/preview", files=files, data={"account_id": accounts["checking"]["id"]}
    )
    assert r.status_code == 422


def test_import_without_key_is_503(client, accounts):
    files = {"file": ("a.pdf", pdf_bytes("aurora_000.pdf"), "application/pdf")}
    r = client.post(
        "/api/import/preview", files=files, data={"account_id": accounts["checking"]["id"]}
    )
    assert r.status_code == 503
    assert "chave" in r.json()["detail"]
