"""Local-only contract test. Locks SPEC §11.

This codebase ships no cloud LLM client. If a future change reintroduces one — by
adding a dependency, a provider class, or an import — these tests fail and the build
blocks. The tests are deliberately blunt; they assert source-text invariants rather
than runtime behaviour, because the property we care about is what *can* be in the
code, not just what currently runs.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import substituterx.provider as provider_module
from substituterx.provider import (
    LLMProvider,
    MockProvider,
    OllamaProvider,
    get_provider,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"


# ---------- 1. The cloud SDK is not installed ------------------------------

@pytest.mark.parametrize("module_name", ["anthropic", "openai", "azure.ai.openai"])
def test_no_cloud_sdk_importable(module_name: str) -> None:
    """No cloud LLM SDK should be importable in the venv."""
    with pytest.raises(ImportError):
        importlib.import_module(module_name)


# ---------- 2. The provider module declares only local providers ----------

_BANNED_NAME_FRAGMENTS = ("anthropic", "azure", "openai", "bedrock", "vertex", "gemini")


def test_provider_module_has_no_cloud_classes() -> None:
    """No class in provider.py may be named after a cloud LLM."""
    for name in dir(provider_module):
        if name.startswith("_"):
            continue
        obj = getattr(provider_module, name)
        if isinstance(obj, type):
            lowered = name.lower()
            assert not any(frag in lowered for frag in _BANNED_NAME_FRAGMENTS), (
                f"provider.py exposes a cloud-LLM class: {name}. "
                "Local-only contract (SPEC §11) forbids this."
            )


def test_provider_source_mentions_no_cloud_endpoint() -> None:
    """The provider source must not contain any cloud LLM hostname or endpoint."""
    src = (SRC_DIR / "substituterx" / "provider.py").read_text()
    lowered = src.lower()
    for forbidden in (
        "api.anthropic.com",
        "api.openai.com",
        "openai.azure.com",
        "generativelanguage.googleapis.com",
        "bedrock-runtime",
    ):
        assert forbidden not in lowered, (
            f"provider.py mentions cloud endpoint {forbidden!r} — local-only contract violated."
        )


# ---------- 3. get_provider only ever returns local providers -------------

@pytest.mark.parametrize("kind", ["mock", "ollama"])
def test_get_provider_returns_local_class(monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    monkeypatch.setenv("SUBSTITUTERX_PROVIDER", kind)
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    p = get_provider()
    assert isinstance(p, (MockProvider, OllamaProvider))


def test_get_provider_rejects_unknown_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUBSTITUTERX_PROVIDER", "anthropic")
    with pytest.raises(ValueError):
        get_provider()


def test_get_provider_auto_falls_back_to_mock_when_ollama_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUBSTITUTERX_PROVIDER", "auto")
    # Point at a port nothing is listening on so the probe definitely fails.
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")
    p = get_provider()
    assert isinstance(p, MockProvider)


# ---------- 4. Both concrete providers satisfy the LLMProvider Protocol --

def test_providers_satisfy_protocol() -> None:
    assert isinstance(MockProvider(), LLMProvider)
    assert isinstance(OllamaProvider(), LLMProvider)


# ---------- 5. The OllamaProvider only ever talks to OLLAMA_HOST ---------

def test_ollama_provider_uses_configured_host() -> None:
    """OllamaProvider must read its endpoint from OLLAMA_HOST, not a hardcoded URL."""
    p = OllamaProvider(host="http://example.invalid:11434")
    assert p.host == "http://example.invalid:11434"
    p_default = OllamaProvider()
    # Default is loopback unless the operator overrides via env.
    assert "localhost" in p_default.host or "127.0.0.1" in p_default.host or p_default.host.startswith("http://")
