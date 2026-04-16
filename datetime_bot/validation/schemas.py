"""JSON Schema definitions for strict input/output validation.

These schemas are the public contract of the bot. Any consumer (human or
machine) can validate their payload against these schemas without running
the parser itself.
"""

from ..config import ASSUMPTION_CODES, TREATED_AS_CODES, VALID_WINDOW_CODES, ERROR_CODES

_ISO_UTC_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
_IANA_TZ_PATTERN = r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z][A-Za-z0-9_+\-]*)*$"

_CODED_FIELD = {
    "type": "object",
    "required": ["code", "label"],
    "additionalProperties": False,
    "properties": {
        "code": {"type": "integer"},
        "label": {"type": "string", "minLength": 1},
    },
}

_VALID_WINDOW = {
    "type": "object",
    "required": ["code", "label", "start", "end"],
    "additionalProperties": False,
    "properties": {
        "code": {"type": "integer", "enum": sorted(VALID_WINDOW_CODES.keys())},
        "label": {"type": "string", "enum": sorted(VALID_WINDOW_CODES.values())},
        "start": {"type": "string", "pattern": _ISO_UTC_PATTERN},
        "end": {"type": "string", "pattern": _ISO_UTC_PATTERN},
    },
}


# --- Input ------------------------------------------------------------------

INPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ChatbotDateTime ParseRequest",
    "type": "object",
    "required": ["text"],
    "additionalProperties": False,
    "properties": {
        "text": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
            "description": "Natural-language datetime text.",
        },
        "timezone": {
            "type": ["string", "null"],
            "pattern": _IANA_TZ_PATTERN,
            "maxLength": 64,
            "description": "IANA timezone (defaults to Asia/Kolkata).",
        },
        "date_order": {
            "type": ["string", "null"],
            "enum": ["DMY", "MDY", None],
            "description": "DMY (default) or MDY.",
        },
    },
}


# --- Output (success) -------------------------------------------------------

OUTPUT_SUCCESS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ChatbotDateTime ParseSuccess",
    "type": "object",
    "required": ["datetime", "assumption", "treated_as", "valid_window"],
    "additionalProperties": False,
    "properties": {
        "datetime": {"type": "string", "pattern": _ISO_UTC_PATTERN},
        "assumption": {
            "type": "array",
            "minItems": 1,
            "items": {
                **_CODED_FIELD,
                "properties": {
                    "code": {"type": "integer", "enum": sorted(ASSUMPTION_CODES.keys())},
                    "label": {"type": "string", "enum": sorted(ASSUMPTION_CODES.values())},
                },
            },
        },
        "treated_as": {
            **_CODED_FIELD,
            "properties": {
                "code": {"type": "integer", "enum": sorted(TREATED_AS_CODES.keys())},
                "label": {"type": "string", "enum": sorted(TREATED_AS_CODES.values())},
            },
        },
        "valid_window": _VALID_WINDOW,
    },
}


# --- Output (error) ---------------------------------------------------------

OUTPUT_ERROR_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ChatbotDateTime ParseError",
    "type": "object",
    "required": ["error"],
    "properties": {
        "error": {
            "type": "object",
            "required": ["code", "label"],
            "properties": {
                "code": {"type": "integer", "enum": sorted(ERROR_CODES.keys())},
                "label": {"type": "string", "enum": sorted(ERROR_CODES.values())},
                "message": {"type": "string"},
            },
        }
    },
}


# --- LLM response schema ----------------------------------------------------

LLM_RESPONSE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ChatbotDateTime LLMResponse",
    "oneOf": [
        {
            "type": "object",
            "required": ["resultDateTime"],
            "properties": {
                "resultDateTime": {"type": "string", "pattern": _ISO_UTC_PATTERN}
            },
        },
        {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {
                    "type": "object",
                    "required": ["code"],
                    "properties": {
                        "code": {"type": "integer", "enum": sorted(ERROR_CODES.keys())},
                        "label": {"type": "string"},
                        "message": {"type": "string"},
                    },
                }
            },
        },
    ],
}
