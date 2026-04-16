import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from datetime_bot.parser import (
    parse_to_iso_utc,
    MultipleDatetimesFound,
    OutOfRangeDatetime,
    DEFAULT_TIMEZONE,
    MAX_FUTURE_DAYS,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("16th April 26 12:00 AM", "2026-04-16T00:00:00.000Z"),
        ("16 Apr 2026 23:00", "2026-04-16T23:00:00.000Z"),
        ("16 Apr 2026 23:00 PM", "2026-04-16T23:00:00.000Z"),
        ("April 16, 2026 6:00 AM", "2026-04-16T06:00:00.000Z"),
        ("16/04/2026 00:30", "2026-04-16T00:30:00.000Z"),  # DMY
        ("04/05/26 10:00 AM", "2026-05-04T10:00:00.000Z"),  # DMY default: 4 May

        ("2026-04-16 00:30:00", "2026-04-16T00:30:00.000Z"),
        ("16th April 2026 12:30 AM", "2026-04-16T00:30:00.000Z"),
        ("Apr 16 2026 11:59 PM", "2026-04-16T23:59:00.000Z"),
        ("16 April 2026", "2026-04-16T00:00:00.000Z"),
        ("16th April 26 12:00 AM", "2026-04-16T00:00:00.000Z"),
        ("16 Apr 26 06:00 AM", "2026-04-16T06:00:00.000Z"),
        ("25 Nov 23 8:00 PM", "2023-11-25T20:00:00.000Z"),
        ("30 Aug'25 01:00 AM", "2025-08-30T01:00:00.000Z"),
        ("3rd Aug 24 12:00 AM", "2024-08-03T00:00:00.000Z"),
        # Rule: "Month NN ..." -> NN is YEAR
        ("Apr 25 6:00 AM", "2025-04-01T06:00:00.000Z"),
        ("Aug 24 12:00 AM", "2024-08-01T00:00:00.000Z"),
        # Space-separated disambiguation (year = 4-digit, day > 12 forces month)
        ("2026 25 04 08 00 AM", "2026-04-25T08:00:00.000Z"),
        ("2026 04 25 08 00 AM", "2026-04-25T08:00:00.000Z"),
        ("2025 30 08 01 00 AM", "2025-08-30T01:00:00.000Z"),
        ("2025 08 30 01 00 AM", "2025-08-30T01:00:00.000Z"),
        ("2024 26 10 10 00 PM", "2024-10-26T22:00:00.000Z"),
        ("2023 25 11 08 00 PM", "2023-11-25T20:00:00.000Z"),
        # "2024 03 08 12 00 AM" is ambiguous — silently defaults to DMY (day=3, month=8);
        # the MDY override is tested separately below.
        # Space-separated without AM/PM — date only
        ("2026 25 04", "2026-04-25T00:00:00.000Z"),
        ("2023 31 12", "2023-12-31T00:00:00.000Z"),
    ],
)
def test_single_datetime_utc(text, expected):
    # Format-parsing tests use historical dates; bypass range check.
    assert parse_to_iso_utc(text, tz="UTC", check_range=False) == expected


def test_timezone_conversion_pakistan():
    # 05:00 PKT (+05:00) -> 00:00 UTC
    result = parse_to_iso_utc("16 Apr 2026 05:00", tz="Asia/Karachi", check_range=False)
    assert result == "2026-04-16T00:00:00.000Z"


def test_timezone_conversion_india():
    # 05:30 IST (+05:30) -> 00:00 UTC
    result = parse_to_iso_utc("16 Apr 2026 05:30", tz="Asia/Kolkata", check_range=False)
    assert result == "2026-04-16T00:00:00.000Z"


def test_timezone_in_text_pkt():
    result = parse_to_iso_utc("16 Apr 2026 05:00 PKT", check_range=False)
    assert result == "2026-04-16T00:00:00.000Z"


def test_missing_timezone_defaults_to_india():
    result = parse_to_iso_utc("16 Apr 2026 12:00 AM", check_range=False)
    assert result == "2026-04-15T18:30:00.000Z"


def test_multiple_datetimes_rejected():
    with pytest.raises(MultipleDatetimesFound):
        parse_to_iso_utc(
            "16th April 26 12:00 AM to 16th April 26 06:00 AM",
            tz="UTC",
            check_range=False,
        )


def _ist_now_plus(days=0, hours=0):
    now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    return now + timedelta(days=days, hours=hours)


def test_range_accepts_tomorrow():
    target = _ist_now_plus(days=1)
    text = target.strftime("%d %b %Y %I:%M %p")
    result = parse_to_iso_utc(text)
    assert result is not None


def test_range_allows_past_but_flags():
    from datetime_bot.parser import parse
    target = _ist_now_plus(days=-1)
    text = target.strftime("%d %b %Y %I:%M %p")
    result = parse(text)
    assert result is not None
    assert result["treated_as"]["code"] == 1  # past
    assert result["valid_window"]["code"] == 2  # past_allowed


def test_range_rejects_far_future():
    target = _ist_now_plus(days=MAX_FUTURE_DAYS + 2)
    text = target.strftime("%d %b %Y %I:%M %p")
    with pytest.raises(OutOfRangeDatetime):
        parse_to_iso_utc(text)


def test_range_allows_historical_gst():
    from datetime_bot.parser import parse
    result = parse("26 Oct 2024 10:00 PM")
    assert result is not None
    assert result["treated_as"]["code"] == 1  # flagged as past
    assert result["datetime"] == "2024-10-26T16:30:00.000Z"


def test_ambiguous_date_defaults_to_dmy():
    result = parse_to_iso_utc("2024 03 08 12 00 AM", tz="UTC", check_range=False)
    assert result == "2024-08-03T00:00:00.000Z"


def test_ambiguous_date_mdy_override():
    result = parse_to_iso_utc(
        "2024 03 08 12 00 AM", tz="UTC", date_order="MDY", check_range=False
    )
    assert result == "2024-03-08T00:00:00.000Z"


def test_dmy_default_for_numeric_slash_format():
    result = parse_to_iso_utc("04/05/2026 10:00 AM", tz="UTC", check_range=False)
    assert result == "2026-05-04T10:00:00.000Z"


@pytest.mark.parametrize(
    "text",
    [
        "99 99 99",
        "2026 50 04 08 00 AM",
        "2026 13 13 08 00 AM",
    ],
)
def test_space_separated_invalid_returns_none(text):
    assert parse_to_iso_utc(text, tz="UTC", check_range=False) is None


def test_unparseable_returns_none():
    assert parse_to_iso_utc("complete gibberish xyzzy", tz="UTC", check_range=False) is None


def test_day_month_without_year_uses_current_year():
    # "25 Apr 1:00 AM" -> day=25, month=Apr, year=current (2026 at test time)
    result = parse_to_iso_utc("25 Apr 1:00 AM", tz="UTC", check_range=False)
    current_year = datetime.now(timezone.utc).year
    assert result == f"{current_year}-04-25T01:00:00.000Z"


def test_day_month_without_year_respects_user_timezone():
    # Year is derived from the user's timezone, then converted to UTC.
    result = parse_to_iso_utc("25 Apr 1:00 AM", tz="Asia/Kolkata", check_range=False)
    current_year = datetime.now(ZoneInfo("Asia/Kolkata")).year
    # 01:00 IST -> 19:30 UTC previous day
    assert result == f"{current_year}-04-24T19:30:00.000Z"


def test_llm_response_success():
    from datetime_bot.parser import accept_llm_response
    # pick a datetime guaranteed to be in-window
    target = _ist_now_plus(hours=2).astimezone(ZoneInfo("UTC"))
    iso = target.strftime("%Y-%m-%dT%H:%M:%S.") + f"{target.microsecond // 1000:03d}Z"
    result = accept_llm_response({"resultDateTime": iso})
    assert result["datetime"] == iso
    assert result["assumption"][0]["label"] == "llm_fallback"
    assert result["treated_as"]["code"] == 2


def test_llm_response_error_passthrough():
    from datetime_bot.parser import accept_llm_response
    result = accept_llm_response({"error": {"code": 12}})
    assert result["error"]["code"] == 12
    assert result["error"]["label"] == "unparseable"


def test_llm_response_bad_shape():
    from datetime_bot.parser import accept_llm_response
    result = accept_llm_response({"resultDateTime": "not-iso"})
    assert result["error"]["code"] == 14


def test_output_format_shape():
    import re
    result = parse_to_iso_utc("16 Apr 2026 00:30", tz="UTC", check_range=False)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", result)


# --- Strict input/output JSON-schema validation ----------------------------


def test_input_validation_rejects_empty_text():
    from datetime_bot.validation import ValidationError
    with pytest.raises(ValidationError):
        parse_to_iso_utc("", tz="UTC", check_range=False, strict=True)


def test_input_validation_rejects_bad_date_order():
    from datetime_bot.validation import ValidationError
    with pytest.raises(ValidationError):
        parse_to_iso_utc(
            "16 Apr 2026", tz="UTC", date_order="XYZ",
            check_range=False, strict=True,
        )


def test_output_envelope_matches_schema():
    from datetime_bot.parser import parse
    from datetime_bot.validation import validate_output_success
    result = parse("16 Apr 2026 10:00 PM")
    validate_output_success(result)  # external re-check
