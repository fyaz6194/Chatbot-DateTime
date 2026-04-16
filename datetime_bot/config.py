"""Central configuration for datetime_bot.

All project-level defaults, hard rules, and JSON code tables live here so they
can be changed in one place and imported by the rest of the package.
"""

# --- Defaults / hard rules ---------------------------------------------------

DEFAULT_TIMEZONE = "Asia/Kolkata"  # India
DEFAULT_DATE_ORDER = "DMY"         # Indian convention (day-month-year)
MAX_FUTURE_DAYS = 3                # Reject datetimes > now_IST + 3 days
PREFER_DATES_FROM = "future"       # dateparser: bias partial inputs toward future
PREFER_DAY_OF_MONTH = "first"      # dateparser: use day=1 when missing

# --- Timezone suggestions ---------------------------------------------------
# Used by the /parse endpoint schema for documentation/examples.

TZ_SUGGESTIONS = {
    "India": "Asia/Kolkata",
    "Pakistan": "Asia/Karachi",
    "Saskatchewan, Canada": "America/Regina",
    "UK": "Europe/London",
    "USA Eastern": "America/New_York",
    "USA Pacific": "America/Los_Angeles",
    "UTC": "UTC",
}

# --- JSON output: numeric code tables ---------------------------------------
# Every metadata field in the JSON output is a {"code": N, "label": "..."} pair.
# Keep keys stable — downstream consumers depend on these integers.

ASSUMPTION_CODES = {
    0: "none",
    1: "default_timezone_india",
    2: "default_date_order_dmy",
    3: "current_year_injected",
    4: "two_digit_year_expanded",
    5: "space_separated_normalized",
    6: "llm_fallback",
}
ASSUMPTION_LLM_CODE = 6  # stamp for results coming from the LLM fallback

TREATED_AS_CODES = {
    0: "unknown",
    1: "past",
    2: "within_window",
    3: "far_future",
}

VALID_WINDOW_CODES = {
    1: "in_window",            # [now, now + MAX_FUTURE_DAYS]
    2: "past_allowed",         # before now — accepted per project rule
    3: "out_of_range_future",  # > now + MAX_FUTURE_DAYS — rejected
}

ERROR_CODES = {
    10: "multiple_datetimes",
    11: "out_of_range_future",
    12: "unparseable",
    13: "ambiguous_date",
    14: "llm_bad_response",
}
