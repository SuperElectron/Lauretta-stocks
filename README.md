# Lauretta Stocks

A research desk for Max Lauretta's book, straight from the bullpen. Tell it how you invest and
what you hold, name a ticker, and a three-person team does the legwork: reads the filings,
checks every number, and tells you straight whether to buy, hold, trim or walk away. It never
places a trade. It suggests; you pull the trigger.

- **The Director** runs the desk: remembers your rules, your appetite for risk and every
  position, and leads with the call, then the why.
- **Andy, the Analyst**, writes the story: what the company does, what could move it, and what
  would prove it wrong.
- **Charlie, the Checker**, trusts nobody and sends the story back until the numbers hold up.
- **Sammy, the Strategist**, sizes it against your book.

Rename any of them in chat. Nothing here is financial advice.

## TLDR

Open https://lauretta.tailae2b1.ts.net on your phone or laptop (Tailscale on), sign in, and say
hey. The Director takes it from there.

To run it on your own machine:

```bash
cp .env.example .env    # fill in the keys
just up                 # start the database
just chat               # talk to the desk
just research MSFT      # put the whole team on one stock
```

## Details

- **Needs:** Docker, [uv](https://docs.astral.sh/uv/) and [just](https://just.systems). Run
  `just` to see every command.
- **Where it runs:** on a DGX Spark, reachable only over Tailscale, with the model
  (gpt-oss-120b) on the Spark itself. `just deploy` ships it.
- **Clients:** the web app, the AnythingLLM Android app, voice, and MCP clients such as Goose.
- **Data:** free sources only (SEC EDGAR, Yahoo Finance). Each person's memories, holdings and
  research are kept apart.
- **How it works:** see `AGENTS.md`.
