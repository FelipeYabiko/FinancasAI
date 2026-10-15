"""Shared eval helpers: model specs, isolated LLM client, statistics, result files."""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.llm.client import LLMClient
from app.llm.prompts import DEFAULT_VERSIONS
from app.models import LLMCall
from app.services.diagnostics import percentile

ROOT = Path(__file__).resolve().parent
DATASETS = ROOT / "datasets"
PRIVATE = ROOT / "private"
RESULTS = ROOT / "results"


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    @classmethod
    def parse(cls, text: str) -> "ModelSpec":
        provider, _, model = text.partition(":")
        if not model:
            raise ValueError(f"model spec must be provider:model, got {text!r}")
        return cls(provider.strip(), model.strip())


@dataclass
class CallLog:
    """Collects every LLMCall of an eval run (in memory, nothing written to the app DB)."""

    calls: list[LLMCall] = field(default_factory=list)

    def __call__(self, call: LLMCall) -> None:
        self.calls.append(call)

    def client(self) -> LLMClient:
        return LLMClient(recorder=self, settings=Settings(llm_log_payloads=False))

    @property
    def cost(self) -> float:
        return sum(c.cost_usd for c in self.calls)


def p50(values: list[int]) -> int:
    return percentile(values, 50)


def p95(values: list[int]) -> int:
    return percentile(values, 95)


def ratio(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def run_metadata(suite: str, prompt_versions: dict | None = None) -> dict:
    return {
        "suite": suite,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "prompt_versions": prompt_versions or dict(DEFAULT_VERSIONS),
    }


def write_result(suite: str, payload: dict, markdown: str) -> Path:
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    path = RESULTS / f"{stamp}_{suite}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    (RESULTS / f"{stamp}_{suite}.md").write_text(markdown)
    return path


def md_table(headers: list[str], rows: list[list]) -> str:
    def fmt(v):
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:.4f}" if abs(v) < 1 else f"{v:.2f}"
        return str(v)

    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in rows]
    return "\n".join(out)
