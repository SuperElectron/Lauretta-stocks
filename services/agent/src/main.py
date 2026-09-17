"""Entrypoint: `chat` talks to the assistant; `research TICKER` runs the team once."""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

from langchain_core.messages import HumanMessage
from loguru import logger

from src.app import App, open_app
from src.errors import AgentError
from src.report import render_report
from src.settings import Settings

REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


async def chat(app: App, thread: str) -> None:
    config = {"configurable": {"thread_id": thread}}
    await app.record_signals({"channel": "cli"}, "cli")
    print(f"chatting on thread {thread!r}; ctrl-d to quit")
    while True:
        try:
            text = (await asyncio.to_thread(input, "you> ")).strip()
        except EOFError:
            print()
            return
        if not text:
            continue
        try:
            final = await app.chat.ainvoke({"messages": [HumanMessage(text)]}, config)
        except Exception as exc:
            # The thread stays usable: unanswered tool calls are repaired on the next turn.
            logger.exception("chat turn failed")
            print(f"\nassistant> [turn failed: {type(exc).__name__}; see the log above]\n")
            continue
        print(f"\nassistant> {final['messages'][-1].text}\n")


async def research(app: App, ticker: str) -> None:
    print(f"researching {ticker.upper()}: analyst, checker, advisor (a minute or two)...")
    final = await app.research(ticker)
    report = render_report(final)
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{final['ticker']}-{date.today().isoformat()}.md"
    path.write_text(report)
    print(report)
    print(f"saved to {path}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    chat_command = commands.add_parser("chat")
    chat_command.add_argument("--thread", default="main", help="conversation to continue")
    research_command = commands.add_parser("research")
    research_command.add_argument("ticker")
    args = parser.parse_args()

    settings = Settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.LOG_LEVEL)
    try:
        async with open_app(settings) as app:
            if args.command == "chat":
                await chat(app, args.thread)
            else:
                await research(app, args.ticker)
    except AgentError as exc:
        sys.exit(f"{exc.code}: {exc.message}")


if __name__ == "__main__":
    asyncio.run(main())
