"""Tests for the provider-agnostic LLM client.

Focus areas:
- Provider discovery from env vars (and the primary-provider override)
- Failover chain when an upstream provider errors out
- Retry classification: transient errors retry, quota/auth errors fail through
- JSON-mode hint propagation
- Graceful degradation when no providers are configured
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

# Make repository root importable regardless of where pytest is invoked.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeChoice:
    def __init__(self, content: str | None):
        self.message = SimpleNamespace(content=content)


class _FakeResponse:
    def __init__(self, content: str | None):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    """Records each call so tests can assert which providers were tried."""

    def __init__(self, behavior):
        self._behavior = behavior
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self._behavior(kwargs)
        if isinstance(result, BaseException):
            raise result
        return _FakeResponse(result)


class _FakeClient:
    def __init__(self, behavior):
        self.completions = _FakeCompletions(behavior)
        self.chat = SimpleNamespace(completions=self.completions)


def _fresh_module(monkeypatch, env: dict[str, str]):
    """Import llm_client with a clean state and a specific env."""
    for key in (
        'CEREBRAS_API_KEY', 'GROQ_API_KEY', 'OPENROUTER_API_KEY',
        'LLM_PRIMARY_PROVIDER', 'LLM_TEMPERATURE', 'LLM_MAX_TOKENS',
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    sys.modules.pop('src.llm_client', None)
    module = importlib.import_module('src.llm_client')
    importlib.reload(module)
    return module


def _patch_clients(module, behaviors: dict[str, object]):
    """Install fake OpenAI clients for the given providers."""
    fakes = {name: _FakeClient(behavior) for name, behavior in behaviors.items()}

    def _fake_build(provider):
        return fakes.get(provider.name)

    # Force re-discovery against the patched builder.
    module._CLIENTS.clear()
    module._AVAILABLE_PROVIDERS = []
    module._INIT_DONE = False
    with mock.patch.object(module, '_build_client', side_effect=_fake_build):
        module._ensure_initialized()
    return fakes


# ---------------------------------------------------------------------------
# Discovery + availability
# ---------------------------------------------------------------------------

def test_no_providers_returns_none(monkeypatch):
    module = _fresh_module(monkeypatch, env={})
    assert module.is_available() is False
    assert module.generate('hello') is None
    assert module.active_providers() == []


def test_short_api_key_is_rejected(monkeypatch):
    module = _fresh_module(monkeypatch, env={'CEREBRAS_API_KEY': 'short'})
    # Builder rejects keys < 20 chars to filter out placeholder values.
    assert module.is_available() is False


def test_primary_provider_override(monkeypatch):
    env = {
        'CEREBRAS_API_KEY': 'a' * 30,
        'GROQ_API_KEY': 'b' * 30,
        'OPENROUTER_API_KEY': 'c' * 30,
        'LLM_PRIMARY_PROVIDER': 'groq',
    }
    module = _fresh_module(monkeypatch, env=env)
    _patch_clients(module, {
        'cerebras': lambda kw: 'cerebras-response',
        'groq': lambda kw: 'groq-response',
        'openrouter': lambda kw: 'openrouter-response',
    })
    # Groq is primary, so it should be tried first and answer.
    assert module.generate('hello') == 'groq-response'
    assert module.active_providers()[0] == 'groq'


# ---------------------------------------------------------------------------
# Failover behavior
# ---------------------------------------------------------------------------

def test_failover_from_quota_error_to_next_provider(monkeypatch):
    env = {
        'CEREBRAS_API_KEY': 'a' * 30,
        'GROQ_API_KEY': 'b' * 30,
    }
    module = _fresh_module(monkeypatch, env=env)
    fakes = _patch_clients(module, {
        'cerebras': lambda kw: RuntimeError('insufficient_quota for today'),
        'groq': lambda kw: 'groq-saved-the-day',
    })

    result = module.generate('hi')
    assert result == 'groq-saved-the-day'
    # Cerebras was tried exactly once (no retry on quota errors).
    assert len(fakes['cerebras'].completions.calls) == 1
    assert len(fakes['groq'].completions.calls) == 1


def test_transient_error_triggers_retry_within_provider(monkeypatch):
    env = {'CEREBRAS_API_KEY': 'a' * 30}
    module = _fresh_module(monkeypatch, env=env)

    call_log: list[int] = []

    def behavior(kw):
        call_log.append(1)
        if len(call_log) < 2:
            return RuntimeError('429 rate limit exceeded')
        return 'ok-after-retry'

    # Patch time.sleep so retries don't slow the test down.
    with mock.patch.object(module.time, 'sleep'):
        _patch_clients(module, {'cerebras': behavior})
        result = module.generate('hi')

    assert result == 'ok-after-retry'
    assert len(call_log) == 2


def test_all_providers_fail_returns_none(monkeypatch):
    env = {
        'CEREBRAS_API_KEY': 'a' * 30,
        'GROQ_API_KEY': 'b' * 30,
    }
    module = _fresh_module(monkeypatch, env=env)
    with mock.patch.object(module.time, 'sleep'):
        _patch_clients(module, {
            'cerebras': lambda kw: RuntimeError('500 server error'),
            'groq': lambda kw: RuntimeError('503 unavailable'),
        })
        assert module.generate('hi') is None


# ---------------------------------------------------------------------------
# Parameter propagation
# ---------------------------------------------------------------------------

def test_temperature_and_max_tokens_from_env(monkeypatch):
    env = {
        'CEREBRAS_API_KEY': 'a' * 30,
        'LLM_TEMPERATURE': '0.7',
        'LLM_MAX_TOKENS': '512',
    }
    module = _fresh_module(monkeypatch, env=env)
    fakes = _patch_clients(module, {'cerebras': lambda kw: 'ok'})

    module.generate('hi')
    call = fakes['cerebras'].completions.calls[0]
    assert call['temperature'] == pytest.approx(0.7)
    assert call['max_tokens'] == 512


def test_generate_json_sets_response_format(monkeypatch):
    env = {'CEREBRAS_API_KEY': 'a' * 30}
    module = _fresh_module(monkeypatch, env=env)
    fakes = _patch_clients(module, {'cerebras': lambda kw: '{"k": 1}'})

    out = module.generate_json('hi')
    call = fakes['cerebras'].completions.calls[0]
    assert call['response_format'] == {'type': 'json_object'}
    assert out == '{"k": 1}'


def test_explicit_kwargs_override_env(monkeypatch):
    env = {
        'CEREBRAS_API_KEY': 'a' * 30,
        'LLM_TEMPERATURE': '0.7',
        'LLM_MAX_TOKENS': '512',
    }
    module = _fresh_module(monkeypatch, env=env)
    fakes = _patch_clients(module, {'cerebras': lambda kw: 'ok'})

    module.generate('hi', temperature=0.1, max_tokens=64)
    call = fakes['cerebras'].completions.calls[0]
    assert call['temperature'] == pytest.approx(0.1)
    assert call['max_tokens'] == 64


# ---------------------------------------------------------------------------
# Reinit
# ---------------------------------------------------------------------------

def test_reinit_picks_up_new_env_var(monkeypatch):
    module = _fresh_module(monkeypatch, env={})
    assert module.is_available() is False

    monkeypatch.setenv('GROQ_API_KEY', 'b' * 30)
    # Without reinit, the module would still think no providers exist.
    _patch_clients(module, {'groq': lambda kw: 'now-online'})
    assert module.is_available() is True
    assert module.generate('hi') == 'now-online'
