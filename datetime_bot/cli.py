import argparse
import json
import sys

from .parser import (
    MultipleDatetimesFound,
    OutOfRangeDatetime,
    parse,
)


def main():
    p = argparse.ArgumentParser(
        description="Parse natural-language datetime text into strict ISO 8601 UTC JSON."
    )
    p.add_argument("text", nargs="*", help="Natural-language date/time text")
    p.add_argument(
        "--tz",
        help="IANA timezone for the input (defaults to Asia/Kolkata).",
    )
    p.add_argument(
        "--date-order",
        choices=["DMY", "MDY"],
        help="Override date order for ambiguous numeric inputs (default DMY).",
    )
    p.add_argument("--serve", action="store_true", help="Run the REST API instead of parsing.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()

    if args.serve:
        import uvicorn
        uvicorn.run("datetime_bot.api:app", host=args.host, port=args.port)
        return

    if not args.text:
        p.error("text is required unless --serve is used")

    text = " ".join(args.text)

    try:
        result = parse(text, tz=args.tz, date_order=args.date_order)
    except MultipleDatetimesFound as e:
        print(json.dumps({
            "error": {"code": 10, "label": "multiple_datetimes", "message": str(e)}
        }))
        sys.exit(2)
    except OutOfRangeDatetime as e:
        print(json.dumps({
            "error": {"code": 11, "label": "out_of_range_future", "message": str(e)},
            "window": {"start": e.window_start_iso, "end": e.window_end_iso},
            "parsed": e.parsed_iso,
        }))
        sys.exit(3)

    if result is None:
        print(json.dumps({
            "error": {"code": 12, "label": "unparseable", "input": text}
        }))
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
