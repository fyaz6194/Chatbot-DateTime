"""LLM client — calls the configured endpoint and returns its JSON response.

This module is deliberately thin: it packages auth/headers/body per
`llm_config.py`, POSTs, and returns the raw parsed JSON. Response validation
and mapping into our output envelope live in `parser.accept_llm_response`.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import urllib.request
import urllib.error

from . import llm_config as cfg


class LLMNotConfigured(Exception):
    """Raised when llm_config.URL is not set."""


class LLMRequestError(Exception):
    """Raised when the HTTP request fails or returns non-2xx."""


def _auth_header() -> dict[str, str]:
    if cfg.API_TOKEN:
        return {"Authorization": f"Bearer {cfg.API_TOKEN}"}
    if cfg.USERNAME and cfg.PASSWORD:
        raw = f"{cfg.USERNAME}:{cfg.PASSWORD}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode()}
    return {}


def _render_body(text: str) -> bytes:
    # Deep-copy-lite via json round-trip so {text} substitution only mutates
    # the payload we send, not the template.
    body = json.loads(json.dumps(cfg.DATA_TEMPLATE))

    def _substitute(obj: Any) -> Any:
        if isinstance(obj, str):
            return obj.replace("{text}", text)
        if isinstance(obj, list):
            return [_substitute(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _substitute(v) for k, v in obj.items()}
        return obj

    return json.dumps(_substitute(body)).encode()


def call_llm(text: str) -> dict:
    """POST the input text to the configured LLM endpoint and return its JSON.

    Raises LLMNotConfigured if no URL is set, LLMRequestError on HTTP failure.
    """
    if not cfg.URL:
        raise LLMNotConfigured("Set DTB_LLM_URL (or llm_config.URL) to enable the LLM fallback.")

    headers = {**cfg.HEADERS, **_auth_header()}
    req = urllib.request.Request(cfg.URL, data=_render_body(text), headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=cfg.TIMEOUT_SECONDS) as resp:
            payload = resp.read().decode()
    except urllib.error.HTTPError as e:
        raise LLMRequestError(f"HTTP {e.code}: {e.read().decode(errors='replace')}") from e
    except urllib.error.URLError as e:
        raise LLMRequestError(f"Network error: {e.reason}") from e

    try:
        return json.loads(payload)
    except json.JSONDecodeError as e:
        raise LLMRequestError(f"Non-JSON response: {payload[:200]}") from e
