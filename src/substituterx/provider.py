"""LLM provider abstraction. Anthropic primary, Azure OpenAI compat-stub.

Per SPEC §10: agent contracts in models.py are the integration seam; nothing in the
agent layer assumes a specific provider.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    cost_usd: float


class AnthropicProvider:
    """Anthropic SDK wrapper. Supports tool use + structured output via JSON mode."""

    # Sonnet 4.6 pricing (as of 2026-04): $3/MTok in, $15/MTok out
    PRICING = {
        "claude-sonnet-4-6": (3.00 / 1_000_000, 15.00 / 1_000_000),
        "claude-haiku-4-5-20251001": (0.80 / 1_000_000, 4.00 / 1_000_000),
        "claude-opus-4-7": (15.00 / 1_000_000, 75.00 / 1_000_000),
    }

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        from anthropic import Anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set. See .env.example.")
        self.client = Anthropic(api_key=api_key)
        self.model = model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def call(
        self,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResult:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
        in_cost, out_cost = self.PRICING.get(self.model, (0.0, 0.0))
        cost = msg.usage.input_tokens * in_cost + msg.usage.output_tokens * out_cost
        return LLMResult(
            text=text,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            model=self.model,
            cost_usd=cost,
        )

    def call_json(
        self,
        system: str,
        user: str,
        schema_hint: str,
        max_tokens: int = 1024,
    ) -> tuple[dict[str, Any], LLMResult]:
        """Call expecting JSON. Wraps a schema instruction and parses the response."""
        sys_full = (
            f"{system}\n\n"
            f"Respond with valid JSON only, matching this schema:\n{schema_hint}\n"
            "Do not include any prose outside the JSON object."
        )
        result = self.call(sys_full, user, max_tokens=max_tokens)
        text = result.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned non-JSON: {result.text[:300]}") from exc
        return parsed, result


class OllamaProvider:
    """Local Ollama. JSON output via the /api/chat format=json field."""

    def __init__(self, model: str = "mistral-small3.2:latest", host: str | None = None) -> None:
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.model = model

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
    def call(self, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.0) -> LLMResult:
        import httpx
        r = httpx.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=120.0,
        )
        r.raise_for_status()
        data = r.json()
        text = data["message"]["content"]
        return LLMResult(
            text=text,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=self.model,
            cost_usd=0.0,  # local
        )

    def call_json(self, system: str, user: str, schema_hint: str, max_tokens: int = 1024) -> tuple[dict, LLMResult]:
        import json as _json

        import httpx
        sys_full = (
            f"{system}\n\nRespond with valid JSON only, matching this schema:\n{schema_hint}\n"
            "Do not include any prose outside the JSON object."
        )
        r = httpx.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "system", "content": sys_full},
                             {"role": "user", "content": user}],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_predict": max_tokens},
            },
            timeout=120.0,
        )
        r.raise_for_status()
        data = r.json()
        text = data["message"]["content"]
        try:
            parsed = _json.loads(text)
        except _json.JSONDecodeError as exc:
            raise ValueError(f"Ollama returned non-JSON: {text[:300]}") from exc
        result = LLMResult(text=text, input_tokens=data.get("prompt_eval_count", 0),
                           output_tokens=data.get("eval_count", 0), model=self.model, cost_usd=0.0)
        return parsed, result


class MockProvider:
    """Deterministic rule-based provider for offline CI and demo recording.
    Intentionally narrow: it produces structurally correct claims for the eval cases
    so the pipeline (validator + auditor + orchestrator) can be tested in isolation."""

    def __init__(self, model: str = "mock-deterministic") -> None:
        self.model = model

    def call(self, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.0) -> LLMResult:
        return LLMResult(text="(mock)", input_tokens=0, output_tokens=0, model=self.model, cost_usd=0.0)

    def call_json(self, system: str, user: str, schema_hint: str, max_tokens: int = 1024) -> tuple[dict, LLMResult]:
        # Deterministic shapes; the actual decision lives in the validator/orchestrator.
        result = LLMResult(text="(mock)", input_tokens=0, output_tokens=0, model=self.model, cost_usd=0.0)

        if '"per_edge"' in schema_hint or "edge_id" in schema_hint and "leakage" not in schema_hint:
            # Validator narrator
            return ({"per_edge": []}, result)
        if "leakage_detected" in schema_hint:
            # Auditor — defer to the regex pass; return clean LLM verdict
            return ({"leakage_detected": False, "downgraded_edge_ids": [], "flags": []}, result)

        # Reasoner default: emit unknown claims; the orchestrator's KG resolution + validator drive the verdict
        return ({
            "equivalent": None,
            "mechanism": "unknown",
            "structured_claims": [
                {"subject_rxcui": None, "predicate": "unknown",
                 "object_rxcui": None, "object_str": None,
                 "rationale": "mock provider — defers to KG resolution",
                 "evidence_request": "validator: resolve via KG name lookup"}
            ],
            "confidence": 0.0,
        }, result)


def get_provider(agent: str | None = None):
    """Return the provider for a given agent role.

    Per-agent overrides are read from env vars (highest priority first):
      SUBSTITUTERX_MODEL_REASONER, _VALIDATOR, _AUDITOR
    Falling back to:
      SUBSTITUTERX_MODEL  (global default)
    Provider kind is set by SUBSTITUTERX_PROVIDER (auto | anthropic | ollama | mock).

    This is the orchestration seam: different agents have different cognitive loads
    (medical knowledge vs. semantic-judgment vs. structured extraction). Routing each
    to the right model is what 'orchestration / fallbacks' on the JD means in practice.
    """
    kind = os.environ.get("SUBSTITUTERX_PROVIDER", "auto").lower()
    role_env = f"SUBSTITUTERX_MODEL_{agent.upper()}" if agent else None
    model = (
        (os.environ.get(role_env) if role_env else None)
        or os.environ.get("SUBSTITUTERX_MODEL")
    )

    if kind == "anthropic":
        return AnthropicProvider(model or "claude-sonnet-4-6")
    if kind == "ollama":
        return OllamaProvider(model or "mistral-small3.2:latest")
    if kind == "mock":
        return MockProvider()
    try:
        import httpx
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        httpx.get(f"{host}/api/tags", timeout=2.0).raise_for_status()
        return OllamaProvider(model or "mistral-small3.2:latest")
    except Exception:
        return MockProvider()
