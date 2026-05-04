#!/usr/bin/env bash
# Verify the local-only contract (SPEC §11) end-to-end.
#
# This script is the human-facing check. The machine-facing equivalent is
# `pytest tests/test_local_only.py`. Both must pass for the contract to hold.

set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PY:-.venv/bin/python}"
status=0
section() { printf "\n=== %s ===\n" "$1"; }

section "1. No cloud LLM SDK in the venv"
for pkg in anthropic openai google-generativeai boto3; do
  if "$PY" -c "import importlib, sys; importlib.import_module('${pkg}'); sys.exit(0)" 2>/dev/null; then
    echo "  FAIL: ${pkg} importable in venv"
    status=1
  else
    echo "  OK: ${pkg} not importable"
  fi
done

section "2. No cloud provider names in source tree"
# Grep for cloud-LLM class/SDK mentions in src/. A clean local-only build returns 0 matches.
if matches=$(grep -RInE 'AnthropicProvider|AzureProvider|OpenAIProvider|GoogleProvider|BedrockProvider|VertexProvider' \
              src/ 2>/dev/null); then
  echo "  FAIL: cloud-provider class names found in source:"
  echo "$matches" | sed 's/^/    /'
  status=1
else
  echo "  OK: no cloud-provider class names in src/"
fi

section "3. No cloud endpoints in source tree"
if matches=$(grep -RInE 'api\.anthropic\.com|api\.openai\.com|openai\.azure\.com|generativelanguage\.googleapis\.com|bedrock-runtime' \
              src/ 2>/dev/null); then
  echo "  FAIL: cloud endpoint URL found in source:"
  echo "$matches" | sed 's/^/    /'
  status=1
else
  echo "  OK: no cloud endpoint URLs in src/"
fi

section "4. pyproject.toml has no cloud SDK dependency"
if grep -nE '^\s*"(anthropic|openai|google-generativeai|boto3|azure-ai-openai)' pyproject.toml >/dev/null; then
  echo "  FAIL: cloud SDK declared in pyproject.toml dependencies:"
  grep -nE '^\s*"(anthropic|openai|google-generativeai|boto3|azure-ai-openai)' pyproject.toml | sed 's/^/    /'
  status=1
else
  echo "  OK: pyproject.toml lists no cloud SDKs"
fi

section "5. Local-only contract test"
if "$PY" -m pytest tests/test_local_only.py -q; then
  echo "  OK: test_local_only.py passed"
else
  echo "  FAIL: test_local_only.py failed"
  status=1
fi

section "6. Eval gate runs against mock without network"
# The mock provider makes zero outbound calls. We assert the eval still passes.
SUBSTITUTERX_PROVIDER=mock "$PY" -m tests.eval.run_eval --mode mock >/tmp/eval_local_only.log
if grep -qE '\[mock\] \[FAIL\]' /tmp/eval_local_only.log; then
  echo "  FAIL: mock eval reported a FAIL"
  tail -20 /tmp/eval_local_only.log | sed 's/^/    /'
  status=1
else
  echo "  OK: mock eval passed (see /tmp/eval_local_only.log)"
fi

echo
if [[ $status -eq 0 ]]; then
  echo "Local-only contract: VERIFIED."
else
  echo "Local-only contract: VIOLATED — see failures above."
fi
exit $status
