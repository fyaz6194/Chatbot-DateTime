"""Thin wrappers over jsonschema for strict input/output validation."""

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as _JSValidationError

from .schemas import (
    INPUT_SCHEMA,
    OUTPUT_SUCCESS_SCHEMA,
    OUTPUT_ERROR_SCHEMA,
    LLM_RESPONSE_SCHEMA,
)


class ValidationError(Exception):
    """Raised when a payload doesn't match its JSON schema."""

    def __init__(self, message: str, errors: list[str]):
        self.errors = errors
        super().__init__(message + ": " + "; ".join(errors))


_input_v = Draft202012Validator(INPUT_SCHEMA)
_output_ok_v = Draft202012Validator(OUTPUT_SUCCESS_SCHEMA)
_output_err_v = Draft202012Validator(OUTPUT_ERROR_SCHEMA)
_llm_v = Draft202012Validator(LLM_RESPONSE_SCHEMA)


def _check(validator: Draft202012Validator, payload, label: str) -> None:
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        msgs = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
        raise ValidationError(f"invalid {label}", msgs)


def validate_input(payload) -> None:
    """Raise ValidationError if payload doesn't match the /parse input schema."""
    _check(_input_v, payload, "input")


def validate_output_success(payload) -> None:
    """Raise ValidationError if payload isn't a well-formed success envelope."""
    _check(_output_ok_v, payload, "success output")


def validate_output_error(payload) -> None:
    """Raise ValidationError if payload isn't a well-formed error envelope."""
    _check(_output_err_v, payload, "error output")


def validate_llm_response(payload) -> None:
    """Raise ValidationError if payload doesn't match the LLM response schema."""
    _check(_llm_v, payload, "LLM response")
