# datetime_bot

A Python bot that accepts natural-language datetime text and returns a strict ISO 8601 UTC string, wrapped in a JSON envelope with machine-readable status codes. Used primarily to schedule GST portal downtime windows.

## Defaults

- **Timezone**: `Asia/Kolkata` (India) if none given.
- **Date order**: `DMY` (Indian convention, e.g. `04/05/2026` = 4 May 2026).
- **Future-preferred**: partial inputs resolve to the next future occurrence.
- **Valid window**: `[now_IST, now_IST + 3 days]`. Past dates are allowed (flagged); far-future (>3 days) is rejected.
- **One datetime at a time**: ranges like `X to Y` are rejected.
- **Output**: always JSON; the `datetime` field is always `YYYY-MM-DDTHH:MM:SS.sssZ`.

## JSON output structure

All metadata fields are `{code, label}` pairs.

| Field          | Shape                              | Codes                                                                                                                                  |
| -------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `datetime`     | `2026-04-16T16:30:00.000Z` (unchanged strict format) | —                                                                                                                                      |
| `assumption`   | array of `{code, label}`           | `0`=none, `1`=default_timezone_india, `2`=default_date_order_dmy, `3`=current_year_injected, `4`=two_digit_year_expanded, `5`=space_separated_normalized, `6`=llm_fallback |
| `treated_as`   | `{code, label}`                    | `1`=past, `2`=within_window, `3`=far_future                                                                                            |
| `valid_window` | `{code, label, start, end}`        | `1`=in_window, `2`=past_allowed, `3`=out_of_range_future                                                                               |
| `error.code`   | int                                | `10`=multiple_datetimes, `11`=out_of_range_future, `12`=unparseable, `13`=ambiguous_date, `14`=llm_bad_response                        |

Past dates are allowed and flagged (code `1`); only far-future (>3 days) is rejected.

## Example outputs

**Success (within window):**

```json
{
  "datetime": "2026-04-16T16:30:00.000Z",
  "assumption": [
    {"code": 1, "label": "default_timezone_india"},
    {"code": 2, "label": "default_date_order_dmy"}
  ],
  "treated_as":   {"code": 2, "label": "within_window"},
  "valid_window": {"code": 1, "label": "in_window",
                   "start": "2026-04-15T22:52:27.521Z",
                   "end":   "2026-04-18T22:52:27.521Z"}
}
```

**Past (allowed, flagged):**

```json
{
  "datetime": "2024-10-26T16:30:00.000Z",
  "treated_as":   {"code": 1, "label": "past"},
  "valid_window": {"code": 2, "label": "past_allowed", "start": "...", "end": "..."}
}
```

**Far-future (rejected, HTTP 422 / CLI exit 3):**

```json
{
  "error": {"code": 11, "label": "out_of_range_future", "message": "..."},
  "window": {"start": "...", "end": "..."},
  "parsed": "2026-12-24T18:30:00.000Z"
}
```

## Quick start (in plain English)

**What this program does:** You type a date/time in any common way (e.g. `16 Apr 2026 10pm`, `25/Apr/26 6:00 AM`, `tomorrow 3pm`). The program reads it, figures out what you meant, and prints back the exact UTC time in a single standard format — wrapped in a small JSON report that also tells you what assumptions it had to make.

### 1. Open a terminal inside the project

Navigate to the folder that holds this project (wherever you cloned/extracted it):

```bash
# Windows example:
cd C:\projects\Chatbot-DateTime

# macOS / Linux example:
cd ~/projects/Chatbot-DateTime
```

### 2. Turn on the virtual environment (one-time setup, then every session)

A virtual environment is just a private box of Python tools for this project. First time only, create one:

```bash
python -m venv .venv
```

Then activate it every time you open a new terminal:

```bash
# on Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# on Git Bash / WSL / Mac / Linux:
source .venv/Scripts/activate
```

You'll know it's active because the prompt shows `(.venv)` at the start.

### 3. Install the libraries (one time)

```bash
pip install -r datetime_bot/requirements.txt
```

### 4. Use it

**Ask a one-off question (CLI):**

```bash
python -m datetime_bot "16 Apr 2026 10:00 PM"
```

Output is a JSON block. The only thing you usually care about is the `"datetime"` line — that's the UTC time you wanted.

**Start the REST server (for apps that need to call it):**

```bash
python -m datetime_bot --serve
```

Then your other program can `POST` to `http://127.0.0.1:8000/parse` with `{"text": "16 Apr 2026 10:00 PM"}`. Open `http://127.0.0.1:8000/docs` in a browser to try it from a friendly web page.

**Run the tests (to make sure everything still works):**

```bash
python -m pytest datetime_bot/tests/
```

## What's inside `config.py` (and why you'd touch it)

`datetime_bot/config.py` is the one place where the program's behavior is tuned. Open it in any text editor and change a value — no other file needs to be touched.

| Setting               | What it means in plain English                                                                                             | Default       | When to change it |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------- | ----------------- |
| `DEFAULT_TIMEZONE`    | The clock the program assumes you're speaking in, if you don't say.                                                         | `Asia/Kolkata` (India) | If the bot will serve users in another country. |
| `DEFAULT_DATE_ORDER`  | How to read an ambiguous date like `04/05/2026`. `"DMY"` = 4 May (Indian/European). `"MDY"` = 5 April (American).          | `"DMY"`       | If most of your users write dates the American way. |
| `MAX_FUTURE_DAYS`     | How far into the future the program is willing to accept. Anything further is rejected.                                     | `3` days      | If you later want a longer/shorter planning window. |
| `PREFER_DATES_FROM`   | When the input is partial (`"Friday"`, `"9 AM"`), pick the next future occurrence vs. the most recent past one.              | `"future"`    | Rarely. Change to `"past"` if you're logging historical events. |
| `PREFER_DAY_OF_MONTH` | If the user gives only month + year (`"Apr 2025"`), should the day default to `1st`, today's date, or end of month?         | `"first"`     | Rarely. |
| `TZ_SUGGESTIONS`      | The friendly list of timezones shown in the API docs as examples.                                                           | India, PK, UK... | Add your region so it appears in Swagger UI. |
| `ASSUMPTION_CODES`    | Numeric codes shown in the JSON `assumption` list — lets callers programmatically see what the bot had to guess.             | see file      | Don't change existing numbers; downstream apps rely on them. Only add new ones. |
| `TREATED_AS_CODES`    | Numeric codes telling you whether the result was in the past, inside the 3-day window, or too far future.                    | see file      | Same rule — only extend. |
| `VALID_WINDOW_CODES`  | Codes for the allowed window (`in_window`, `past_allowed`, `out_of_range_future`).                                          | see file      | Same rule — only extend. |
| `ERROR_CODES`         | Numeric codes for things that can go wrong (can't parse, multiple dates, etc.). Also used to interpret LLM error responses.  | see file      | Same rule — only extend. |

**Rule of thumb:** the first 5 settings are safe to change — they're behavior knobs. The code tables (`*_CODES`) are a public contract with anything consuming the JSON output; you can **add** new entries but don't **renumber** existing ones.

## Usage

### Install

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# bash / git-bash:
source .venv/Scripts/activate

pip install -r datetime_bot/requirements.txt
```

### CLI

```bash
python -m datetime_bot "16 Apr 2026 10:00 PM"
python -m datetime_bot "25/Apr/2026 06:00 AM" --tz UTC
python -m datetime_bot "2026 25 04 08 00 AM"   # space-separated disambiguation
python -m datetime_bot "04/05/26 10:00 AM" --date-order MDY   # force US interpretation
```

CLI flags: `--tz <IANA>`, `--date-order DMY|MDY`, `--serve` (run REST API), `--host`, `--port`.

Exit codes: `0`=ok, `1`=unparseable, `2`=multiple_datetimes, `3`=out_of_range_future.

### REST API

```bash
python -m datetime_bot --serve
# POST http://127.0.0.1:8000/parse
# {"text": "16 Apr 2026 10:00 PM", "timezone": "Asia/Kolkata", "date_order": "DMY"}
```

### Tests

```bash
python -m pytest datetime_bot/tests/ -v
```

## Supported input formats

- `16th April 2026 12:00 AM`, `16 Apr 2026 23:00 PM`, `Apr 16 2026 11:59 PM`
- `16/04/2026 00:30`, `2026-04-16 00:30:00`, `25/Apr/2026 06:00 AM`
- 2-digit years: `16 Apr 26 06:00 AM`, `30 Aug'25 01:00 AM`, `25 Nov 23 8:00 PM`
  - Pivot: `00-49` → `2000-2049`, `50-99` → `1950-1999`
- Month-name with 2-digit year: `Apr 25 6:00 AM` — `25` is treated as **year** (=2025)
- Day without year: `25 Apr 1:00 AM` — current IST year is injected
- Space-separated digits: `2026 25 04 08 00 AM` — disambiguated by size (`>12` = day, `4-digit` = year, trailing two = `HH MM` when AM/PM present)
- Timezone in text: `IST`, `PKT`, `UTC`, `+05:30`, country/region names

## Optional LLM fallback

> **Status: under development.** The LLM path is scaffolded (`llm.py`, `llm_config.py`, `parser.accept_llm_response()`) but `URL` is unset by default and `call_llm()` raises `LLMNotConfigured` until an endpoint is configured.

For inputs that the rule-based parser cannot handle, an optional LLM endpoint can be called.

### Configure `datetime_bot/llm_config.py` (or env vars)

| Setting          | Env var               | Purpose                                      |
| ---------------- | --------------------- | -------------------------------------------- |
| `URL`            | `DTB_LLM_URL`         | Endpoint to POST to                          |
| `API_TOKEN`      | `DTB_LLM_API_TOKEN`   | Sent as `Authorization: Bearer <token>`      |
| `USERNAME`       | `DTB_LLM_USERNAME`    | Used for Basic auth if `API_TOKEN` is unset  |
| `PASSWORD`       | `DTB_LLM_PASSWORD`    | Used for Basic auth if `API_TOKEN` is unset  |
| `HEADERS`        | —                     | Additional static headers                    |
| `DATA_TEMPLATE`  | —                     | Request body; `{text}` is substituted at call time |
| `TIMEOUT_SECONDS`| —                     | HTTP timeout                                 |

### Expected LLM response schema

```json
{"resultDateTime": "2026-04-16T16:30:00.000Z"}          // success
{"error": {"code": 12, "label": "unparseable"}}         // failure
```

`code` must be one of the `ERROR_CODES` in `config.py`. Any other shape maps to error code `14` (`llm_bad_response`).

### Integration

```python
from datetime_bot.llm import call_llm
from datetime_bot.parser import accept_llm_response

raw = call_llm("the tuesday after my birthday at 9")
result = accept_llm_response(raw)   # returns the same envelope as parse()
```

Results coming from the LLM are stamped with `assumption.code=6` (`llm_fallback`). The range rule still applies.

## Project rules (hard-coded)

1. `datetime` field always uses `YYYY-MM-DDTHH:MM:SS.sssZ` — never change format.
2. Default timezone = `Asia/Kolkata`.
3. Default date order = `DMY` (India).
4. Only one datetime per request.
5. Valid window = `[now_IST, now_IST + 3 days]`; past allowed (flagged), far-future rejected.
