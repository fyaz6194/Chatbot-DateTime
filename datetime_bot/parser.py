import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser
from dateparser.search import search_dates

from .config import (
    ASSUMPTION_CODES,
    ASSUMPTION_LLM_CODE,
    DEFAULT_DATE_ORDER,
    DEFAULT_TIMEZONE,
    ERROR_CODES,
    MAX_FUTURE_DAYS,
    PREFER_DATES_FROM,
    PREFER_DAY_OF_MONTH,
    TREATED_AS_CODES,
    TZ_SUGGESTIONS,
    VALID_WINDOW_CODES,
)

__all__ = [
    "parse",
    "parse_to_iso_utc",
    "accept_llm_response",
    "MultipleDatetimesFound",
    "OutOfRangeDatetime",
    "DEFAULT_TIMEZONE",
    "MAX_FUTURE_DAYS",
    "TZ_SUGGESTIONS",
]


# --- Regex patterns ---------------------------------------------------------

_MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)

# "Apr'25" apostrophe form (unambiguous)
_APOS_YY_RE = re.compile(rf"\b({_MONTHS})\s*'\s*(\d{{2}})\b", re.IGNORECASE)

# "16 Apr 25" / "16th April 25" — day-first with 2-digit year
_DAY_MONTH_YY_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})\s+(\d{{2}})\b(?!\d)",
    re.IGNORECASE,
)

# "Apr 25" — month followed by 1-2 digit number NOT followed by a 4-digit year
# or a colon (which would indicate a time). Project rule: treat that trailing
# number as the YEAR.
_MONTH_YY_RE = re.compile(
    rf"\b({_MONTHS})\s+(\d{{1,2}})\b(?!\s*,?\s*\d{{4}})(?!\s*:)(?!\d)",
    re.IGNORECASE,
)

# "25 Apr" / "25th April" with NO following year — inject current year.
_DAY_MONTH_NO_YEAR_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})\b(?!\s*,?\s*\d{{2,4}})",
    re.IGNORECASE,
)

# Space-separated all-digit date like "2026 25 04 08 00 AM"
_SPACE_DIGITS_RE = re.compile(
    r"^\s*(\d+(?:\s+\d+){2,5})\s*(AM|PM)?\s*$", re.IGNORECASE
)

# Tokens that signal an explicit timezone inside the input text.
_TZ_HINT_PATTERN = re.compile(
    r"\b(UTC|GMT|Z|EST|EDT|CST|CDT|MST|MDT|PST|PDT|IST|PKT|BST|CET|CEST|JST|AEST|"
    r"India|Pakistan|Saskatchewan|London|Tokyo|Karachi|Kolkata|Mumbai|Delhi|Regina|"
    r"Europe|Asia|America|Africa|Australia|Pacific)\b|[+-]\d{2}:?\d{2}",
    re.IGNORECASE,
)

# Strict ISO 8601 UTC output shape.
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


# --- Exceptions -------------------------------------------------------------


class MultipleDatetimesFound(Exception):
    """Raised when the text contains more than one datetime reference."""


class OutOfRangeDatetime(Exception):
    """Raised when the parsed datetime is more than MAX_FUTURE_DAYS ahead.

    Past datetimes are allowed (flagged via JSON codes); only far-future is
    rejected at parse time.
    """

    def __init__(self, parsed_iso: str, window_start_iso: str, window_end_iso: str):
        self.parsed_iso = parsed_iso
        self.window_start_iso = window_start_iso
        self.window_end_iso = window_end_iso
        super().__init__(
            f"{parsed_iso} is more than {MAX_FUTURE_DAYS} days in the future "
            f"(window: {window_start_iso} .. {window_end_iso})."
        )


# --- Helpers ----------------------------------------------------------------


def _pivot(yy: int) -> int:
    """Two-digit-year pivot: 00-49 -> 20YY, 50-99 -> 19YY."""
    return 2000 + yy if yy <= 49 else 1900 + yy


def _current_year(tz: str | None) -> int:
    if tz:
        try:
            return datetime.now(ZoneInfo(tz)).year
        except ZoneInfoNotFoundError:
            pass
    return datetime.now(timezone.utc).year


def _format(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def _coded(code: int, table: dict) -> dict:
    return {"code": code, "label": table[code]}


def text_has_timezone(text: str) -> bool:
    return bool(_TZ_HINT_PATTERN.search(text))


def _count_datetimes(text: str) -> int:
    found = search_dates(text, settings={"PREFER_DATES_FROM": PREFER_DATES_FROM})
    return len(found) if found else 0


# --- Preprocessing ----------------------------------------------------------


def _normalize_space_separated(
    text: str, date_order: str | None = None
) -> str:
    """Disambiguate space-only-separated date tokens like '2026 25 04 08 00 AM'.

    Heuristics:
      * A 4-digit number is the YEAR.
      * If AM/PM is present, the last two numbers are HOUR and MINUTE.
      * Of the remaining 1-2 numbers, any value > 12 must be the DAY; the
        other is the MONTH.
      * If both remaining values are <=12 and date_order == "MDY", treat as
        month-first; otherwise default to day-first (India/DMY).

    Returns a normalized "YYYY-MM-DD HH:MM AM" string, or the original text
    if the heuristics can't resolve the tokens.
    """
    m = _SPACE_DIGITS_RE.match(text)
    if not m:
        return text

    tokens = [int(t) for t in m.group(1).split()]
    ampm = (m.group(2) or "").upper()

    year_candidates = [t for t in tokens if t >= 1000]
    if len(year_candidates) != 1:
        return text
    year = year_candidates[0]
    rest = [t for t in tokens if t != year]

    hour = minute = None
    if ampm and len(rest) >= 4:
        minute = rest[-1]
        hour = rest[-2]
        rest = rest[:-2]
        if not (0 <= hour <= 12 and 0 <= minute <= 59):
            return text

    if len(rest) != 2:
        return text

    a, b = rest
    if a > 31 or b > 31 or a < 1 or b < 1:
        return text

    if a > 12 and b <= 12:
        day, month = a, b
    elif b > 12 and a <= 12:
        day, month = b, a
    elif a <= 12 and b <= 12:
        if date_order == "MDY":
            month, day = a, b
        else:
            day, month = a, b
    else:
        return text

    if not (1 <= month <= 12 and 1 <= day <= 31):
        return text

    if hour is not None:
        return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d} {ampm}"
    return f"{year:04d}-{month:02d}-{day:02d}"


def _expand_two_digit_year(
    text: str, tz: str | None = DEFAULT_TIMEZONE
) -> tuple[str, set[int]]:
    """Expand 2-digit years and inject the current year when missing.

    Returns the rewritten text plus the set of assumption codes triggered:
      * 4 — two_digit_year_expanded (any YY -> YYYY substitution)
      * 3 — current_year_injected  (DD Month without a year)
    """
    codes: set[int] = set()
    year = _current_year(tz or DEFAULT_TIMEZONE)

    def repl_month_yy(m):
        codes.add(4)
        return f"{m.group(1)} {_pivot(int(m.group(2)))}"

    def repl_day_month_yy(m):
        codes.add(4)
        return f"{m.group(1)} {m.group(2)} {_pivot(int(m.group(3)))}"

    def repl_month_yy_inject_day(m):
        codes.add(4)
        return f"1 {m.group(1)} {_pivot(int(m.group(2)))}"

    def repl_inject_year(m):
        codes.add(3)
        return f"{m.group(1)} {m.group(2)} {year}"

    text = _APOS_YY_RE.sub(repl_month_yy, text)
    text = _DAY_MONTH_YY_RE.sub(repl_day_month_yy, text)
    text = _MONTH_YY_RE.sub(repl_month_yy_inject_day, text)
    text = _DAY_MONTH_NO_YEAR_RE.sub(repl_inject_year, text)
    return text, codes


# --- Range / classification -------------------------------------------------


def _window_utc() -> tuple[datetime, datetime]:
    now_ist = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    start = now_ist.astimezone(timezone.utc)
    end = (now_ist + timedelta(days=MAX_FUTURE_DAYS)).astimezone(timezone.utc)
    return start, end


def _classify(
    dt_utc: datetime, start: datetime, end: datetime
) -> tuple[int, int]:
    """Return (treated_as_code, valid_window_code) for a parsed datetime."""
    if dt_utc > end:
        return 3, 3  # far future — caller raises
    if dt_utc < start:
        return 1, 2  # past — allowed, flagged
    return 2, 1  # within window


def _build_envelope(
    iso: str, assumptions: list[int], treated_code: int, window_code: int,
    start: datetime, end: datetime,
) -> dict:
    """Assemble the standard JSON envelope around a parsed datetime."""
    if not assumptions:
        assumptions = [0]
    return {
        "datetime": iso,
        "assumption": [_coded(c, ASSUMPTION_CODES) for c in assumptions],
        "treated_as": _coded(treated_code, TREATED_AS_CODES),
        "valid_window": {
            **_coded(window_code, VALID_WINDOW_CODES),
            "start": _format(start),
            "end": _format(end),
        },
    }


# --- Public API -------------------------------------------------------------


def parse(
    text: str,
    tz: str | None = None,
    date_order: str | None = None,
    check_range: bool = True,
    strict: bool = True,
) -> dict | None:
    """Parse text and return a JSON-ready dict with datetime + metadata codes.

    When strict=True (default), the input is validated against INPUT_SCHEMA
    and the output envelope is validated against OUTPUT_SUCCESS_SCHEMA.
    Returns None when the text is unparseable.
    Raises MultipleDatetimesFound, OutOfRangeDatetime, or ValidationError.
    """
    if strict:
        from .validation import validate_input
        payload: dict = {"text": text}
        if tz is not None:
            payload["timezone"] = tz
        if date_order is not None:
            payload["date_order"] = date_order
        validate_input(payload)

    iso, assumptions = _parse_text(text, tz, date_order)
    if iso is None:
        return None

    dt_utc = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    start, end = _window_utc()
    treated_code, window_code = _classify(dt_utc, start, end)

    if check_range and window_code == 3:
        raise OutOfRangeDatetime(
            parsed_iso=iso,
            window_start_iso=_format(start),
            window_end_iso=_format(end),
        )

    envelope = _build_envelope(iso, assumptions, treated_code, window_code, start, end)
    if strict:
        from .validation import validate_output_success
        validate_output_success(envelope)
    return envelope


def parse_to_iso_utc(
    text: str,
    tz: str | None = None,
    date_order: str | None = None,
    check_range: bool = True,
    strict: bool = False,
) -> str | None:
    """Convenience wrapper — returns only the ISO datetime string."""
    result = parse(
        text, tz=tz, date_order=date_order, check_range=check_range, strict=strict
    )
    return result["datetime"] if result else None


def accept_llm_response(
    response: dict, check_range: bool = True, strict: bool = True
) -> dict:
    """Validate an LLM response and convert it into our standard JSON envelope.

    Expected shapes:
        {"resultDateTime": "YYYY-MM-DDTHH:MM:SS.sssZ"}      -> success
        {"error": {"code": <int>, ...}}                      -> error passthrough

    Malformed / unknown payloads map to error code 14 (llm_bad_response).
    When strict=True (default), output envelopes are validated against
    OUTPUT_SUCCESS_SCHEMA or OUTPUT_ERROR_SCHEMA.
    """
    if not isinstance(response, dict):
        return {
            "error": _coded(14, ERROR_CODES),
            "detail": "response is not a JSON object",
        }

    if "error" in response:
        err = response["error"]
        if isinstance(err, dict) and err.get("code") in ERROR_CODES:
            extras = {k: v for k, v in err.items() if k not in {"code", "label"}}
            return {"error": {**_coded(err["code"], ERROR_CODES), **extras}}
        return {
            "error": _coded(14, ERROR_CODES),
            "detail": f"unknown error payload: {err!r}",
        }

    iso = response.get("resultDateTime")
    if not isinstance(iso, str) or not _ISO_RE.match(iso):
        return {
            "error": _coded(14, ERROR_CODES),
            "detail": f"resultDateTime missing or wrong format: {iso!r}",
        }

    dt_utc = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    start, end = _window_utc()
    treated_code, window_code = _classify(dt_utc, start, end)

    if check_range and window_code == 3:
        raise OutOfRangeDatetime(
            parsed_iso=iso,
            window_start_iso=_format(start),
            window_end_iso=_format(end),
        )

    envelope = _build_envelope(
        iso, [ASSUMPTION_LLM_CODE], treated_code, window_code, start, end
    )
    if strict:
        from .validation import validate_output_success
        validate_output_success(envelope)
    return envelope


# --- Internal parse pipeline ------------------------------------------------


def _parse_text(
    text: str, tz: str | None, date_order: str | None
) -> tuple[str | None, list[int]]:
    """Run preprocessors + dateparser, returning (iso_or_None, assumption_codes)."""
    assumptions: list[int] = []

    before = text
    text = _normalize_space_separated(text, date_order=date_order)
    if text != before:
        assumptions.append(5)

    text, yy_codes = _expand_two_digit_year(text, tz=tz)
    assumptions.extend(sorted(yy_codes))

    if _count_datetimes(text) > 1:
        raise MultipleDatetimesFound(
            "Multiple datetimes detected. Please input only one datetime at a time."
        )

    has_tz_in_text = text_has_timezone(text)

    if not has_tz_in_text and not tz:
        tz = DEFAULT_TIMEZONE
        assumptions.append(1)

    if date_order is None:
        assumptions.append(2)

    settings = {
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": PREFER_DATES_FROM,
        "PREFER_DAY_OF_MONTH": PREFER_DAY_OF_MONTH,
    }
    # DATE_ORDER applies only to fully-numeric inputs. ISO-shaped text
    # (YYYY-...) already encodes its order and would be mis-parsed if forced.
    is_iso_shaped = bool(re.match(r"^\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}", text))
    if not is_iso_shaped:
        settings["DATE_ORDER"] = date_order or DEFAULT_DATE_ORDER
    if tz and not has_tz_in_text:
        settings["TIMEZONE"] = tz
        settings["TO_TIMEZONE"] = "UTC"

    dt = dateparser.parse(text, settings=settings)
    if dt is None:
        return None, assumptions

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return _format(dt), assumptions
