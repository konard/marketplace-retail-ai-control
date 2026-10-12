"""Command line: the morning run, follow-ups, the web app and questions.

Schedule ``retail-ai-control morning`` for 07:00 and ``followup`` every hour
(cron, a systemd timer or Bitrix24 business process); run ``serve`` behind
the company's single sign-on proxy.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from retail_ai_control.config import load_config
from retail_ai_control.pilot import Pilot

CONFIG_VARIABLE = "RETAIL_AI_CONTROL_CONFIG"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retail-ai-control", description="AI management loop for WB and Ozon"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get(CONFIG_VARIABLE, "pilot.toml")),
        help=f"settings file (default: ${CONFIG_VARIABLE} or pilot.toml)",
    )
    parser.add_argument("--verbose", action="store_true", help="log every step")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", help="load the sources for a date range")
    sync.add_argument("--from", dest="first", type=date.fromisoformat)
    sync.add_argument("--to", dest="last", type=date.fromisoformat)
    commands.add_parser("morning", help="sync, check, find, propose, send digest")
    commands.add_parser("followup", help="retry tasks and measure due effects")
    serve = commands.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument(
        "--user", type=int, help="act as this user without a sign-on proxy (demo)"
    )
    ask = commands.add_parser("ask", help="ask a question about the data")
    ask.add_argument("question")
    commands.add_parser("demo", help="load the concept's example into the database")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run one command; return the exit code."""
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    pilot = Pilot(load_config(args.config))
    if args.command == "sync":
        last = args.last or pilot.today() - timedelta(1)
        first = args.first or last - timedelta(pilot.config.sync_lookback_days - 1)
        report = pilot.sync(first, last)
        for entry in report:
            print(
                f"{entry['source']}: {entry['status']} {entry['rows']} {entry['message']}"
            )
        return 1 if any(entry["status"] == "failed" for entry in report) else 0
    if args.command == "morning":
        print(pilot.morning())
    elif args.command == "followup":
        pilot.retry_tasks()
        for item in pilot.run_followups():
            print(item)
    elif args.command == "serve":
        import uvicorn

        from retail_ai_control.web import create_app

        uvicorn.run(create_app(pilot, args.user), host=args.host, port=args.port)
    elif args.command == "ask":
        answer = pilot.ask(args.question)
        print(answer.text)
        for name, link in answer.links:
            base = pilot.config.web_url if link.startswith("/") else ""
            print(f"  {name}: {base}{link}")
    elif args.command == "demo":
        from retail_ai_control.demo import load_demo

        print(f"deviations: {load_demo(pilot)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
