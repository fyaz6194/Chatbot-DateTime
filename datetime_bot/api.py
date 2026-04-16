from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .parser import (
    MultipleDatetimesFound,
    OutOfRangeDatetime,
    parse,
)

app = FastAPI(
    title="datetime_bot",
    version="1.0.0",
    description=(
        "Rule-based natural-language datetime parser with a strict ISO 8601 UTC "
        "output format and numeric status codes. Defaults: timezone Asia/Kolkata, "
        "date order DMY, valid window [now, now + 3 days]."
    ),
)


class ParseRequest(BaseModel):
    text: str = Field(
        ...,
        description="Natural-language datetime text.",
        examples=["16 Apr 2026 10:00 PM", "25/Apr/2026 06:00 AM", "2026 25 04 08 00 AM"],
    )
    timezone: str | None = Field(
        None,
        description="IANA timezone for the input. Defaults to Asia/Kolkata.",
        examples=["Asia/Kolkata", "UTC", "Asia/Karachi"],
    )
    date_order: str | None = Field(
        None,
        description='Date-order hint for ambiguous numeric inputs. "DMY" (default) or "MDY".',
        examples=["DMY", "MDY"],
        pattern="^(DMY|MDY)$",
    )


class CodedField(BaseModel):
    code: int = Field(..., description="Stable numeric code.")
    label: str = Field(..., description="Human-readable label for the code.")


class ValidWindow(CodedField):
    start: str = Field(..., description="Window start (inclusive), ISO 8601 UTC.")
    end: str = Field(..., description="Window end (inclusive), ISO 8601 UTC.")


class ParseSuccess(BaseModel):
    datetime: str = Field(
        ...,
        description="Parsed datetime in the fixed format YYYY-MM-DDTHH:MM:SS.sssZ.",
        examples=["2026-04-16T16:30:00.000Z"],
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$",
    )
    assumption: list[CodedField] = Field(
        ...,
        description=(
            "Assumptions applied during parsing. Codes: 0=none, 1=default_timezone_india, "
            "2=default_date_order_dmy, 3=current_year_injected, 4=two_digit_year_expanded, "
            "5=space_separated_normalized, 6=llm_fallback."
        ),
    )
    treated_as: CodedField = Field(
        ...,
        description="How the parsed datetime relates to the valid window. 1=past, 2=within_window, 3=far_future.",
    )
    valid_window: ValidWindow = Field(
        ...,
        description="Allowed window [now_IST, now_IST + 3 days]. 1=in_window, 2=past_allowed, 3=out_of_range_future.",
    )


class ErrorDetail(CodedField):
    message: str | None = None


class ParseError(BaseModel):
    error: ErrorDetail = Field(
        ...,
        description=(
            "Error codes: 10=multiple_datetimes, 11=out_of_range_future, "
            "12=unparseable, 13=ambiguous_date, 14=llm_bad_response."
        ),
    )


class Health(BaseModel):
    status: str = Field(..., examples=["ok"])


@app.post(
    "/parse",
    response_model=ParseSuccess,
    responses={422: {"model": ParseError, "description": "Validation or range error."}},
    summary="Parse a natural-language datetime into strict ISO 8601 UTC.",
)
def parse_endpoint(req: ParseRequest):
    try:
        result = parse(req.text, tz=req.timezone, date_order=req.date_order)
    except MultipleDatetimesFound as e:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": 10, "label": "multiple_datetimes", "message": str(e)}},
        )
    except OutOfRangeDatetime as e:
        return JSONResponse(
            status_code=422,
            content={
                "error": {"code": 11, "label": "out_of_range_future", "message": str(e)},
                "window": {"start": e.window_start_iso, "end": e.window_end_iso},
                "parsed": e.parsed_iso,
            },
        )
    if result is None:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": 12, "label": "unparseable", "input": req.text}},
        )
    return result


@app.get("/health", response_model=Health, summary="Liveness probe.")
def health():
    return {"status": "ok"}
