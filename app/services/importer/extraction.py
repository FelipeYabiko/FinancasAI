"""Step 4 — structured extraction with the LLM, chunk by chunk (validated output)."""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta

from app.llm.client import LLMClient, LLMValidationError
from app.llm.prompts import load_prompt
from app.llm.types import LLMConfigError, ProviderError
from app.schemas.llm import ExtractedTransaction, ExtractionOutput
from app.services.importer.chunking import chunk_lines, strip_repeated_boilerplate
from app.services.importer.detect import DocumentInfo, detect_document
from app.services.importer.pdf_text import PdfText

DOC_TYPE_PT = {
    "checking_statement": "extrato de conta corrente",
    "credit_card_invoice": "fatura de cartão de crédito",
    "unknown": "desconhecido",
}


@dataclass
class ExtractionRun:
    info: DocumentInfo
    transactions: list[ExtractedTransaction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    chunks: int = 0
    boilerplate_lines_removed: int = 0
    failed_chunks: int = 0
    llm_calls: int = 0
    validation_retries: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0  # wall-clock for the whole document
    input_tokens: int = 0
    output_tokens: int = 0


def context_block(info: DocumentInfo) -> str:
    lines = [
        f"Banco: {info.bank or 'não identificado'}",
        f"Tipo de documento: {DOC_TYPE_PT[info.document_type]}",
    ]
    if info.period_start or info.period_end:
        start = info.period_start.isoformat() if info.period_start else "?"
        end = info.period_end.isoformat() if info.period_end else "?"
        lines.append(f"Período: {start} a {end}")
    if info.closing_date:
        lines.append(f"Fechamento da fatura: {info.closing_date.isoformat()}")
    if info.due_date:
        lines.append(f"Vencimento: {info.due_date.isoformat()}")
    if info.reference_year:
        lines.append(f"Ano de referência para datas sem ano: {info.reference_year}")
    return "\n".join(lines)


def extract_transactions(
    pdf: PdfText,
    client: LLMClient,
    provider: str,
    model: str,
    prompt_version: str | None = None,
    chunk_tokens: int = 1500,
    max_workers: int = 4,
) -> ExtractionRun:
    started = time.perf_counter()
    info = detect_document(pdf.lines)
    pages, removed = strip_repeated_boilerplate(pdf.pages)
    chunked = chunk_lines([ln for p in pages for ln in p], chunk_tokens)
    run = ExtractionRun(info=info, warnings=list(chunked.warnings), chunks=len(chunked.chunks),
                        boilerplate_lines_removed=removed)  # fmt: skip
    if info.document_type == "unknown":
        run.warnings.append("tipo de documento não identificado; confira o resultado com atenção")
    system, version = load_prompt(
        "extraction", prompt_version.split(".")[-1] if prompt_version else None
    )
    ctx = context_block(info)

    def one(idx_chunk):
        idx, chunk = idx_chunk
        user = (
            f"Contexto do documento:\n{ctx}\n\n"
            f"Trecho {idx + 1} de {len(chunked.chunks)}:\n<<<\n" + "\n".join(chunk) + "\n>>>"
        )
        return client.call(
            "extraction",
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            provider=provider,
            model=model,
            prompt_version=version,
            response_model=ExtractionOutput,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(one, item) for item in enumerate(chunked.chunks)]
        for idx, fut in enumerate(futures):
            try:
                res = fut.result()
            except LLMConfigError:
                raise
            except (LLMValidationError, ProviderError) as exc:
                run.failed_chunks += 1
                run.warnings.append(f"bloco {idx + 1} não pôde ser extraído ({exc.__class__.__name__}): "
                                    f"{str(exc)[:160]}")  # fmt: skip
                for rec in getattr(exc, "records", []):
                    run.cost_usd += rec.cost_usd
                continue
            run.llm_calls += res.calls
            run.validation_retries += res.validation_retries
            run.cost_usd += res.cost_usd
            run.input_tokens += res.input_tokens
            run.output_tokens += res.output_tokens
            run.transactions.extend(res.parsed.transactions)
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    _sanity_check(run)
    return run


def _sanity_check(run: ExtractionRun) -> None:
    """Flag (not drop) transactions dated far outside the statement period."""
    info = run.info
    if not info.period_end:
        return
    start = (info.period_start or info.period_end - timedelta(days=31)) - timedelta(days=7)
    end = info.period_end + timedelta(days=7)
    out_of_range = 0
    for tx in run.transactions:
        if tx.installment_total:  # installments show the original purchase date
            continue
        if not start <= tx.date <= end:
            tx.confidence = min(tx.confidence, 0.5)
            out_of_range += 1
    if out_of_range:
        run.warnings.append(f"{out_of_range} transação(ões) com data fora do período do documento")
