"""
Provider-agnostic LLM client for the iGaming Intelligence Dashboard.

Replaces the Google Gemini SDK with OpenAI-compatible open-source model providers.
Routes calls through a failover chain so the dashboard stays up if any single
provider rate-limits or has an outage.

Provider chain (ordered by speed + free-tier generosity):
  1. Cerebras    -> GPT-OSS 120B at ~2000 tok/s, 1M tokens/day free
  2. Groq        -> Llama 3.3 70B Versatile, 14.4k req/day free, native JSON schema
  3. OpenRouter  -> Llama 3.3 70B / Qwen2.5 72B (free tier) as last-resort failover

The Cerebras free tier only exposes ``gpt-oss-120b`` and ``zai-glm-4.7`` — Llama
3.3 70B is paid-only. ``gpt-oss-120b`` (OpenAI's open-weights 120B reasoning
model) gives the best free-tier quality on Cerebras hardware.

All providers expose OpenAI-compatible chat-completions endpoints, so we use the
official `openai` SDK with a custom `base_url` for each.

Environment variables (any subset enables that provider):
  CEREBRAS_API_KEY
  GROQ_API_KEY
  OPENROUTER_API_KEY

Optional overrides:
  LLM_PRIMARY_PROVIDER    -> default "cerebras"
  LLM_TEMPERATURE         -> default "0.3"
  LLM_MAX_TOKENS          -> default "4096"
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Iterable

try:
    from openai import OpenAI  # type: ignore
    from openai import APIError, APITimeoutError, RateLimitError
except ImportError:  # pragma: no cover - openai is in requirements.txt
    OpenAI = None  # type: ignore[assignment]
    APIError = APITimeoutError = RateLimitError = Exception  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Provider:
    name: str
    env_key: str
    base_url: str
    model: str
    timeout: float = 60.0


# Ordered by preference. Each entry maps to a single OpenAI-compatible endpoint.
# Models chosen for: strong reasoning, fast inference, generous free tier.
_PROVIDERS: tuple[_Provider, ...] = (
    _Provider(
        name='cerebras',
        env_key='CEREBRAS_API_KEY',
        base_url='https://api.cerebras.ai/v1',
        # Free tier on Cerebras only exposes gpt-oss-120b and zai-glm-4.7.
        # gpt-oss-120b is OpenAI's open-weights 120B reasoning model.
        model=os.getenv('LLM_CEREBRAS_MODEL', 'gpt-oss-120b'),
    ),
    _Provider(
        name='groq',
        env_key='GROQ_API_KEY',
        base_url='https://api.groq.com/openai/v1',
        model='llama-3.3-70b-versatile',
    ),
    _Provider(
        name='openrouter',
        env_key='OPENROUTER_API_KEY',
        base_url='https://openrouter.ai/api/v1',
        # Free-tier model with strong instruction-following.
        model='meta-llama/llama-3.3-70b-instruct:free',
    ),
)


# Backoff configuration mirrors the previous Gemini retry policy.
_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 10.0
_MAX_RETRIES_PER_PROVIDER = 2

# Lazy-initialized client cache keyed by provider name.
_CLIENTS: dict[str, object] = {}
_INIT_DONE = False
_AVAILABLE_PROVIDERS: list[_Provider] = []


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def _primary_first(providers: Iterable[_Provider]) -> list[_Provider]:
    """Reorder providers so the user-selected primary is tried first.

    Python's sort is stable, so providers other than the primary keep their
    original ordering — no need to track indices manually.
    """
    primary = os.getenv('LLM_PRIMARY_PROVIDER', 'cerebras').strip().lower()
    items = list(providers)
    items.sort(key=lambda p: 0 if p.name == primary else 1)
    return items


def _build_client(provider: _Provider) -> object | None:
    api_key = os.getenv(provider.env_key)
    if not api_key or len(api_key) < 20:
        return None
    if OpenAI is None:
        return None
    try:
        return OpenAI(api_key=api_key, base_url=provider.base_url, timeout=provider.timeout)
    except Exception as exc:  # pragma: no cover - defensive
        print(f'LLM init error ({provider.name}): {exc}')
        return None


def _ensure_initialized() -> bool:
    """Discover which providers have credentials configured. Idempotent."""
    global _INIT_DONE, _AVAILABLE_PROVIDERS

    if _INIT_DONE:
        return bool(_AVAILABLE_PROVIDERS)

    ordered = _primary_first(_PROVIDERS)
    available: list[_Provider] = []
    for provider in ordered:
        client = _build_client(provider)
        if client is not None:
            _CLIENTS[provider.name] = client
            available.append(provider)

    _AVAILABLE_PROVIDERS = available
    _INIT_DONE = True
    return bool(_AVAILABLE_PROVIDERS)


def reinit() -> bool:
    """Force re-discovery of providers (e.g. after env vars change)."""
    global _INIT_DONE, _AVAILABLE_PROVIDERS
    _CLIENTS.clear()
    _AVAILABLE_PROVIDERS = []
    _INIT_DONE = False
    return _ensure_initialized()


def is_available() -> bool:
    """Cheap availability check without re-running discovery."""
    if _INIT_DONE:
        return bool(_AVAILABLE_PROVIDERS)
    return _ensure_initialized()


def active_providers() -> list[str]:
    """Names of providers that are currently usable. Useful for diagnostics."""
    _ensure_initialized()
    return [p.name for p in _AVAILABLE_PROVIDERS]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _is_retryable(exc: BaseException) -> bool:
    """True for transient errors worth retrying within the same provider."""
    if isinstance(exc, (RateLimitError, APITimeoutError)):
        return True
    msg = str(exc).lower()
    return any(token in msg for token in (
        'rate', 'limit', 'quota', 'timeout', 'unavailable',
        '429', '503', '500', 'overloaded', 'capacity', 'temporarily',
    ))


def _is_quota_exhausted(exc: BaseException) -> bool:
    """True for errors that mean this provider is dead for this call.

    Includes 404 (model not found / no access) so a stale model ID fails
    over to the next provider instantly instead of burning retries.
    """
    msg = str(exc).lower()
    return any(token in msg for token in (
        'quota', 'insufficient_quota', '401', '403', '404',
        'does not exist', 'do not have access',
    ))


def _call_provider(
    provider: _Provider,
    prompt: str,
    temperature: float,
    max_tokens: int,
    response_format: dict | None,
) -> str | None:
    """Single-provider call with retry on transient errors."""
    client = _CLIENTS.get(provider.name)
    if client is None:
        return None

    backoff = _INITIAL_BACKOFF
    last_exc: BaseException | None = None

    for attempt in range(_MAX_RETRIES_PER_PROVIDER + 1):
        try:
            kwargs: dict = {
                'model': provider.model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': temperature,
                'max_tokens': max_tokens,
            }
            if response_format is not None:
                kwargs['response_format'] = response_format

            response = client.chat.completions.create(**kwargs)  # type: ignore[attr-defined]
            content = response.choices[0].message.content
            return content.strip() if content else None
        except Exception as exc:
            last_exc = exc
            if _is_quota_exhausted(exc):
                # Give up on this provider so the failover chain advances.
                print(f'LLM provider {provider.name} quota/auth error: {exc}')
                break
            if _is_retryable(exc) and attempt < _MAX_RETRIES_PER_PROVIDER:
                print(
                    f'LLM transient error on {provider.name} '
                    f'(attempt {attempt + 1}/{_MAX_RETRIES_PER_PROVIDER + 1}): {exc}'
                )
                time.sleep(min(backoff, _MAX_BACKOFF))
                backoff *= 2
                continue
            print(f'LLM error on {provider.name}: {exc}')
            break

    if last_exc is not None:
        # Don't raise; caller handles None as "fall back to next provider".
        return None
    return None


def generate(
    prompt: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict | None = None,
) -> str | None:
    """
    Generate a completion using the configured failover chain.

    Returns:
        Response text, or None if every provider fails. Callers should treat
        None as a graceful-degradation signal (use a deterministic fallback).
    """
    if not _ensure_initialized():
        return None

    temp = temperature if temperature is not None else float(os.getenv('LLM_TEMPERATURE', '0.3'))
    max_t = max_tokens if max_tokens is not None else int(os.getenv('LLM_MAX_TOKENS', '4096'))

    for provider in _AVAILABLE_PROVIDERS:
        result = _call_provider(provider, prompt, temp, max_t, response_format)
        if result:
            return result

    return None


def generate_json(prompt: str, **kwargs) -> str | None:
    """
    Generate with JSON response_format hint (where supported).

    Most OpenAI-compatible providers accept {'type': 'json_object'}. If a
    provider rejects it, the failover chain moves on transparently.
    """
    return generate(prompt, response_format={'type': 'json_object'}, **kwargs)
