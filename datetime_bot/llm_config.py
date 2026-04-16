"""LLM / external API configuration for datetime_bot.

Fill these in (or override via environment variables) to enable an LLM fallback
for unparseable inputs. The parser treats the LLM response as trusted data —
the LLM is expected to return JSON of the form:

    {"resultDateTime": "2026-04-16T16:30:00.000Z"}       # success
    {"error": {"code": 12, "label": "unparseable"}}      # failure

`code` / `label` must match the ERROR_CODES table in `config.py`.
"""

import os


# --- Endpoint --------------------------------------------------------------

URL: str | None = os.getenv("DTB_LLM_URL")  # e.g. "https://api.anthropic.com/v1/messages"

# --- Auth ------------------------------------------------------------------

API_TOKEN: str | None = os.getenv("DTB_LLM_API_TOKEN")
USERNAME: str | None = os.getenv("DTB_LLM_USERNAME")
PASSWORD: str | None = os.getenv("DTB_LLM_PASSWORD")

# --- Headers ---------------------------------------------------------------
# Static headers. `Authorization` is injected at request time from API_TOKEN or
# USERNAME/PASSWORD, so don't duplicate it here.

HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    # "anthropic-version": "2023-06-01",   # example for Anthropic API
    # "x-api-key": "<set via API_TOKEN instead>",
}

# --- Request body template -------------------------------------------------
# `{text}` is substituted with the user's input at call time.

DATA_TEMPLATE: dict = {
    "model": "claude-opus-4-6",
    "max_tokens": 256,
    "messages": [
        {
            "role": "user",
            "content": (
                "Extract a single datetime from the following text and return "
                "ONLY JSON of the form "
                '{"resultDateTime": "YYYY-MM-DDTHH:MM:SS.sssZ"} on success, or '
                '{"error": {"code": 12, "label": "unparseable"}} on failure. '
                "Codes: 10=multiple_datetimes, 11=out_of_range_future, "
                "12=unparseable, 13=ambiguous_date.\n\nInput: {text}"
            ),
        }
    ],
}

# --- Timeouts --------------------------------------------------------------

TIMEOUT_SECONDS: float = 10.0
