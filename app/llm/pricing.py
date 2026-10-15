from functools import lru_cache
from pathlib import Path

import yaml

PRICING_FILE = Path(__file__).with_name("pricing.yaml")


@lru_cache
def load_pricing() -> dict[str, dict[str, float]]:
    return yaml.safe_load(PRICING_FILE.read_text()) or {}


def price_for(provider: str, model: str) -> dict[str, float] | None:
    table = load_pricing()
    if provider == "fake":
        return {"input": 0.0, "output": 0.0}
    return table.get(f"{provider}/{model}")


def estimate_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    price = price_for(provider, model)
    if not price:
        return 0.0
    return round((input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000, 8)


def known_models() -> list[dict]:
    out = []
    for key, p in load_pricing().items():
        provider, model = key.split("/", 1)
        out.append({"provider": provider, "model": model, **p})
    return out
