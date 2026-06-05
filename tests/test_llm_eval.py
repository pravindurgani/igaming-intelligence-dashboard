"""Opt-in quality evals against a real LLM provider.

These tests only run when at least one of ``CEREBRAS_API_KEY``,
``GROQ_API_KEY``, or ``OPENROUTER_API_KEY`` is set. Otherwise they are
skipped so CI without credentials stays green.

The goal is not exhaustive output validation (LLMs are nondeterministic) but
to catch regressions in:
- Provider wiring (the call actually reaches a real API)
- Prompt shape (model responds with sensible structure, not refusal text)
- JSON-mode contract (when we ask for JSON we get valid JSON)

Each eval makes one short call (~50 tokens) to keep the daily free tier safe.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


_HAS_KEYS = any(
    os.getenv(k) and len(os.getenv(k, '')) >= 20
    for k in ('CEREBRAS_API_KEY', 'GROQ_API_KEY', 'OPENROUTER_API_KEY')
)

pytestmark = pytest.mark.skipif(
    not _HAS_KEYS,
    reason='No LLM provider keys configured; set CEREBRAS_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY to enable evals.',
)


@pytest.fixture(scope='module')
def llm():
    """Fresh llm_client module bound to current env."""
    import importlib
    sys.modules.pop('src.llm_client', None)
    module = importlib.import_module('src.llm_client')
    importlib.reload(module)
    assert module.is_available(), 'Provider discovery failed despite key set.'
    return module


def test_simple_generation_returns_non_empty_string(llm):
    """Trivial 'are you alive' check — provider responds with text."""
    out = llm.generate(
        'Reply with the single word: pong',
        temperature=0.0,
        max_tokens=10,
    )
    assert isinstance(out, str)
    assert len(out) > 0
    # Don't strictly assert "pong" — models sometimes add punctuation/explanation
    # at low temperature too. Presence of non-empty text is enough.


def test_igaming_insight_prompt_returns_actionable_text(llm):
    """End-to-end shape check matching the dashboard's insight pattern."""
    prompt = (
        'As an iGaming analyst, in ONE sentence (max 20 words), name the top '
        'opportunity from this data: Brazil 30% external, 10% internal coverage.'
    )
    out = llm.generate(prompt, temperature=0.3, max_tokens=60)
    assert isinstance(out, str)
    assert len(out) >= 20  # not an empty/refusal response
    # The model should mention the named geography we passed in.
    assert 'brazil' in out.lower()


def test_json_mode_returns_parseable_json(llm):
    """Validate that response_format hint produces valid JSON."""
    prompt = (
        'Return a JSON object with exactly one key "winner" whose value is '
        '"Brazil". Do not include any other fields or commentary.'
    )
    out = llm.generate_json(prompt, temperature=0.0, max_tokens=60)
    assert isinstance(out, str)
    # Some providers wrap JSON in markdown fences even with json_object mode.
    # Strip a leading ``` if present so the test reflects real-world handling.
    text = out.strip()
    if text.startswith('```'):
        text = text.strip('`').lstrip('json').strip()
    parsed = json.loads(text)
    assert isinstance(parsed, dict)
    assert 'winner' in parsed
