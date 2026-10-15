"""Step 5 — categorization: deterministic CategoryMemory first, LLM only for the rest."""

from dataclasses import dataclass

from app.domain.normalize import normalize_description, strip_accents
from app.llm.client import LLMClient, LLMValidationError
from app.llm.prompts import load_prompt
from app.llm.types import ProviderError
from app.schemas.llm import CategorizationOutput

BATCH = 60


@dataclass
class CatItem:
    description: str
    type: str  # income | expense | transfer


@dataclass
class CatResult:
    category_id: int | None
    source: str  # memory | llm | none


@dataclass
class CategorizationRun:
    results: list[CatResult]
    llm_calls: int = 0
    cost_usd: float = 0.0
    from_memory: int = 0
    from_llm: int = 0
    warnings: list[str] | None = None


def _key(name: str) -> str:
    return strip_accents(name).lower().strip()


def categorize(
    items: list[CatItem],
    categories: list[tuple[int, str, str]],  # (id, name, kind)
    memory: dict[str, int],
    client: LLMClient | None,
    provider: str = "",
    model: str = "",
    prompt_version: str | None = None,
) -> CategorizationRun:
    results: list[CatResult | None] = [None] * len(items)
    run = CategorizationRun(results=[], warnings=[])
    pending: dict[str, list[int]] = {}  # normalized desc -> indexes
    for i, it in enumerate(items):
        if it.type == "transfer":
            results[i] = CatResult(None, "none")
            continue
        norm = normalize_description(it.description)
        if norm in memory:
            results[i] = CatResult(memory[norm], "memory")
            run.from_memory += 1
        else:
            pending.setdefault(f"{it.type}|{norm}", []).append(i)

    by_name = {_key(name): (cid, kind) for cid, name, kind in categories}
    if pending and client is not None:
        system, version = load_prompt(
            "categorization", prompt_version.split(".")[-1] if prompt_version else None
        )
        allowed = "\n".join(
            f"- {name} ({'receita' if kind == 'income' else 'despesa'})"
            for _, name, kind in categories
        )
        keys = list(pending)
        for start in range(0, len(keys), BATCH):
            batch = keys[start : start + BATCH]
            listing = "\n".join(
                f"{n}. [{'receita' if items[pending[k][0]].type == 'income' else 'despesa'}] "
                f"{items[pending[k][0]].description}"
                for n, k in enumerate(batch)
            )
            user = f"Categorias permitidas:\n{allowed}\n\nTransações:\n{listing}"
            try:
                res = client.call(
                    "categorization",
                    [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    provider=provider,
                    model=model,
                    prompt_version=version,
                    response_model=CategorizationOutput,
                )
            except (LLMValidationError, ProviderError) as exc:
                run.warnings.append(
                    f"categorização automática falhou para {len(batch)} item(ns): {str(exc)[:120]}"
                )
                continue
            run.llm_calls += res.calls
            run.cost_usd += res.cost_usd
            for item in res.parsed.items:
                if item.index >= len(batch):
                    continue
                match = by_name.get(_key(item.category))
                key = batch[item.index]
                tx_type = key.split("|", 1)[0]
                if not match or match[1] != tx_type:
                    continue  # unknown category or wrong kind → leave uncategorized
                for i in pending[key]:
                    results[i] = CatResult(match[0], "llm")
                    run.from_llm += 1
    run.results = [r or CatResult(None, "none") for r in results]
    return run
