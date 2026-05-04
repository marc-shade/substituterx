"""LLM provider abstraction. Local-only: Ollama or deterministic Mock.

Per SPEC §10: agent contracts in models.py are the integration seam; nothing in the
agent layer assumes a specific provider. By design this codebase ships **no cloud
LLM client**. Inference happens on the configured Ollama host (default
``http://localhost:11434``) or the deterministic Mock provider — that is the entire
network surface of the application. This is enforced by ``tests/test_local_only.py``.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    cost_usd: float


@runtime_checkable
class LLMProvider(Protocol):
    """Duck-typed contract every provider satisfies. Used as the type-hint seam in agents."""

    model: str

    def call(self, system: str, user: str, max_tokens: int = ..., temperature: float = ...) -> LLMResult: ...

    def call_json(
        self, system: str, user: str, schema_hint: str, max_tokens: int = ...,
    ) -> tuple[dict[str, Any], LLMResult]: ...


class OllamaProvider:
    """Local Ollama. JSON output via the /api/chat format=json field.

    The host defaults to ``http://localhost:11434``. Setting OLLAMA_HOST to a
    non-localhost address is supported for cluster setups but is the operator's
    decision — it is the only way the application makes a non-localhost call.
    """

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
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
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


def get_provider(agent: str | None = None) -> LLMProvider:
    """Return the provider for a given agent role.

    Per-agent overrides are read from env vars (highest priority first):
      SUBSTITUTERX_MODEL_REASONER, _VALIDATOR, _AUDITOR
    Falling back to:
      SUBSTITUTERX_MODEL  (global default)
    Provider kind is set by SUBSTITUTERX_PROVIDER (auto | ollama | mock).
    "auto" probes the configured Ollama host once and falls back to mock if unreachable.

    This is the orchestration seam: different agents have different cognitive loads
    (medical knowledge vs. semantic-judgment vs. structured extraction). Routing each
    to the right local model is what 'orchestration / fallbacks' on the JD means in
    practice. No cloud providers are wired — see module docstring.
    """
    kind = os.environ.get("SUBSTITUTERX_PROVIDER", "auto").lower()
    role_env = f"SUBSTITUTERX_MODEL_{agent.upper()}" if agent else None
    model = (
        (os.environ.get(role_env) if role_env else None)
        or os.environ.get("SUBSTITUTERX_MODEL")
    )

    if kind == "ollama":
        return OllamaProvider(model or "mistral-small3.2:latest")
    if kind == "mock":
        return MockProvider()
    if kind != "auto":
        raise ValueError(
            f"Unknown SUBSTITUTERX_PROVIDER={kind!r}. Local-only build supports: auto | ollama | mock."
        )
    try:
        import httpx
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        httpx.get(f"{host}/api/tags", timeout=2.0).raise_for_status()
        return OllamaProvider(model or "mistral-small3.2:latest")
    except Exception:
        return MockProvider()
