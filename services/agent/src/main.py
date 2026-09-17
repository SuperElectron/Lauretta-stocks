"""Entrypoint: `chat` talks to the assistant; `research TICKER` runs the team once.

Both act for `--user` (default: the owner, the first of ALLOWED_USERS), through the same
runtime context and thread keys as the worker, so the CLI and the API share a user's threads.
"""

import argparse
import asyncio
import sys

from langchain_core.messages import HumanMessage
from loguru import logger

from src.app import App, open_app
from src.errors import AgentError
from src.graph.ctx import Ctx
from src.queue import keys
from src.report import render_report
from src.settings import Settings

CLI_CHATTING = "chatting on thread {thread!r}; ctrl-d to quit"
CLI_TURN_FAILED = "[turn failed: {error}; see the log above]"
CLI_RESEARCHING = "researching {ticker}: Analyst, Checker, Strategist (a minute or two)..."
CLI_REPLY = "\nassistant> {reply}\n"
CLI_THREAD_HELP = "conversation to continue"
CLI_USER_HELP = "the user to act for (default: the owner, first in ALLOWED_USERS)"
CLI_UNKNOWN_USER = "{user!r} is not in ALLOWED_USERS"


async def chat(app: App, user: str, thread: str) -> None:
    config = {"configurable": {"thread_id": keys.thread(user, thread)}}
    context = Ctx(user_id=user)
    await app.record_signals(user, {"channel": "cli"}, "cli")
    print(CLI_CHATTING.format(thread=thread))
    while True:
        try:
            text = (await asyncio.to_thread(input, "you> ")).strip()
        except EOFError:
            print()
            return
        if not text:
            continue
        try:
            final = await app.chat.ainvoke(
                {"messages": [HumanMessage(text)]}, config, context=context
            )
        except Exception as exc:
            # The thread stays usable: unanswered tool calls are repaired on the next turn.
            logger.exception("cli.turn_failed")
            print(CLI_REPLY.format(reply=CLI_TURN_FAILED.format(error=type(exc).__name__)))
            continue
        print(CLI_REPLY.format(reply=final["messages"][-1].text))


async def research(app: App, user: str, ticker: str) -> None:
    print(CLI_RESEARCHING.format(ticker=ticker.upper()))
    final = await app.research(ticker, Ctx(user_id=user))
    # Printed only: the thesis is saved in the database for the user, and devices get it through
    # the API, chat or MCP. Nothing is written to disk.
    print(render_report(final))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", help=CLI_USER_HELP)
    commands = parser.add_subparsers(dest="command", required=True)
    chat_command = commands.add_parser("chat")
    chat_command.add_argument("--thread", default="main", help=CLI_THREAD_HELP)
    research_command = commands.add_parser("research")
    research_command.add_argument("ticker")
    args = parser.parse_args()

    settings = Settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.LOG_LEVEL)
    user = args.user or settings.owner()
    if user not in settings.allowed_users():
        sys.exit(CLI_UNKNOWN_USER.format(user=user))
    try:
        async with open_app(settings) as app:
            if args.command == "chat":
                await chat(app, user, args.thread)
            else:
                await research(app, user, args.ticker)
    except AgentError as exc:
        sys.exit(f"{exc.code}: {exc.message}")


if __name__ == "__main__":
    asyncio.run(main())
