"""Per-cell token metering for the model-swap eval (cost ranking).

A thin ``LlmClient`` wrapper that observes ``LlmResult.usage`` and accumulates it into a shared
``TokenMeter`` — it never alters the call or the result, so it is byte-identical to the unwrapped
client. Wrap the SUBJECT roles (L1/L3/helpers) so the cell's est. cost/turn reflects the answer
path; leave the JUDGE client unwrapped (it is the measuring instrument, not the subject — mirrors
``Record.elapsed_ms`` excluding the judge call).

Accounting is keyed by MODEL (``model_config.model``), not by client: in a mixed cell (L1=mistral,
L3=openai) two subject roles bill at different rates, so per-model counts let the runner apply each
model's published rate. The harness shares one pipeline across concurrent units, so this meters per
CELL (sum across the run), not per unit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sealai_v2.core.contracts import LlmResult, ModelConfig, TokenUsage


def _zero() -> dict:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "n_calls": 0,
        "n_calls_with_usage": 0,
    }


@dataclass
class TokenMeter:
    by_model: dict[str, dict] = field(default_factory=dict)

    def add(self, model: str, usage: TokenUsage | None) -> None:
        # asyncio is cooperative single-thread; no await between reads/writes here → safe to += .
        m = self.by_model.setdefault(model, _zero())
        m["n_calls"] += 1
        if usage is None:
            return
        m["n_calls_with_usage"] += 1
        m["prompt_tokens"] += usage.prompt_tokens
        m["completion_tokens"] += usage.completion_tokens
        m["total_tokens"] += usage.total_tokens

    def _sum(self, key: str) -> int:
        return sum(m[key] for m in self.by_model.values())

    @property
    def prompt_tokens(self) -> int:
        return self._sum("prompt_tokens")

    @property
    def completion_tokens(self) -> int:
        return self._sum("completion_tokens")

    @property
    def total_tokens(self) -> int:
        return self._sum("total_tokens")

    @property
    def n_calls(self) -> int:
        return self._sum("n_calls")

    @property
    def n_calls_with_usage(self) -> int:
        return self._sum("n_calls_with_usage")


class MeteringLlmClient:
    """Wraps an inner ``LlmClient``; tees ``usage`` (keyed by model) into ``meter`` and returns the
    result verbatim."""

    def __init__(self, inner, meter: TokenMeter) -> None:
        self._inner = inner
        self._meter = meter

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        res = await self._inner.generate(
            system=system, user=user, model_config=model_config
        )
        self._meter.add(model_config.model, res.usage)
        return res
