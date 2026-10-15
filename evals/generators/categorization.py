"""Builds the labelled categorization dataset (~150 descriptions).

    uv run python -m evals.generators.categorization

Descriptions mimic what statements print: prefixes, city suffixes, card ids, installment markers,
mixed case. Labels use the app's default category names.
"""

import json
import random
from pathlib import Path

from evals.generators.catalog import EMPLOYERS, MERCHANTS, PEOPLE

PREFIXES = ["", "", "COMPRA DEBITO ", "COMPRA CARTAO ", "PAG*", "DEB AUT "]
SUFFIXES = ["", "", " SAO PAULO BR", " BELO HORIZONT", " *1234", " 03/10", " CURITIBA"]

# Hand-written harder cases (ambiguous wording, abbreviations, incomes).
EXTRA: list[tuple[str, str, str]] = [
    ("PIX RECEBIDO REEMBOLSO ALMOCO", "income", "Outras receitas"),
    ("TED RECEBIDA CLIENTE PROJETO SITE", "income", "Freelance"),
    ("PAGTO NF SERVICOS DESIGN", "income", "Freelance"),
    ("RESGATE CDB LIQUIDEZ", "income", "Investimentos"),
    ("DIVIDENDOS FII XPTO11", "income", "Investimentos"),
    ("RENDIMENTO POUPANCA", "income", "Investimentos"),
    ("SHELL BOX POSTO", "expense", "Transporte"),
    ("SEM PARAR PEDAGIO", "expense", "Transporte"),
    ("METRO RECARGA BILHETE", "expense", "Transporte"),
    ("DROGASIL 1234", "expense", "Saúde"),
    ("UNIMED MENSALIDADE", "expense", "Saúde"),
    ("DISNEY PLUS", "expense", "Assinaturas"),
    ("APPLE.COM/BILL", "expense", "Assinaturas"),
    ("GOOGLE ONE STORAGE", "expense", "Assinaturas"),
    ("STEAM PURCHASE", "expense", "Lazer"),
    ("BAR DO ZE", "expense", "Restaurantes"),
    ("MC DONALDS 0042", "expense", "Restaurantes"),
    ("ZE DELIVERY BEBIDAS", "expense", "Delivery"),
    ("ALUGUEL APTO 42", "expense", "Moradia"),
    ("IPVA 2026 PARCELA 1", "expense", "Impostos e taxas"),
    ("IOF COMPRA INTERNACIONAL", "expense", "Impostos e taxas"),
    ("ANUIDADE CARTAO", "expense", "Impostos e taxas"),
    ("PETZ FILIAL 22", "expense", "Pets"),
    ("VETERINARIO AMIGO BICHO", "expense", "Pets"),
    ("BOOKING.COM HOTEL", "expense", "Viagem"),
    ("LATAM AIRLINES", "expense", "Viagem"),
    ("ESCOLA PEQUENO SABER MENS", "expense", "Educação"),
    ("UDEMY CURSO ONLINE", "expense", "Educação"),
    ("SHOPEE COMPRA", "expense", "Compras"),
    ("MERCADOLIVRE*VENDEDOR", "expense", "Compras"),
    ("CLARO RESIDENCIAL", "expense", "Contas e serviços"),
    ("COPEL ENERGIA", "expense", "Contas e serviços"),
]


def build(seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    items: list[dict] = []
    for names, cat, _ in MERCHANTS:
        for name in names:
            for _ in range(2):
                desc = f"{rng.choice(PREFIXES)}{name}{rng.choice(SUFFIXES)}"
                if rng.random() < 0.3:
                    desc = desc.title()
                items.append({"description": desc.strip(), "type": "expense", "category": cat})
    for person in PEOPLE:
        items.append(
            {"description": f"PIX ENVIADO {person}", "type": "expense", "category": "Outros"}
        )
        items.append(
            {
                "description": f"PIX RECEBIDO {person}",
                "type": "income",
                "category": "Outras receitas",
            }
        )
    for emp in EMPLOYERS:
        items.append({"description": f"SALARIO {emp}", "type": "income", "category": "Salário"})
        items.append(
            {
                "description": f"CRED SALARIO {emp.split()[0]}",
                "type": "income",
                "category": "Salário",
            }
        )
    items += [{"description": d, "type": t, "category": c} for d, t, c in EXTRA]
    seen: set[str] = set()
    unique = []
    for it in items:
        if it["description"].lower() not in seen:
            seen.add(it["description"].lower())
            unique.append(it)
    for i, it in enumerate(unique):
        it["id"] = i
    return unique


def main() -> None:
    items = build()
    out = Path("evals/datasets/categorization.json")
    out.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    print(f"{len(items)} labelled descriptions → {out}")


if __name__ == "__main__":
    main()
