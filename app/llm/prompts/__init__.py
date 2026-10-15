"""Versioned prompts. Each prompt is a file `<feature>.<version>.md`.

Changing a prompt means creating a new version file, running the evals, and only then
moving the default below. Every LLMCall records the version it used.
"""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

DEFAULT_VERSIONS = {
    "extraction": "v1",
    "categorization": "v1",
    "assistant": "v1",
    "insights": "v1",
    "ping": "v1",
}


@lru_cache
def load_prompt(feature: str, version: str | None = None) -> tuple[str, str]:
    """Return (prompt_text, version_tag) e.g. ('...', 'extraction.v1')."""
    version = version or DEFAULT_VERSIONS[feature]
    path = PROMPTS_DIR / f"{feature}.{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path.name}")
    return path.read_text(encoding="utf-8").strip(), f"{feature}.{version}"


def list_versions(feature: str) -> list[str]:
    return sorted(p.name.split(".")[1] for p in PROMPTS_DIR.glob(f"{feature}.v*.md"))
