# Aangan — Household OS

A conversational household ledger that runs in a private Discord server. Send a text message in `#expenses` 
("1800 groceries", "paid maid 4000") and it becomes a clean, categorized ledger entry. No app, no form, no friction.

V1 is the expense-tracking module.

---

## Code structure

```
main.py                          # entry point — loads config, connects to DB + Discord, runs forever
aangan/
  config/
    config.py                    # loads env vars into a typed, frozen Config object
  bot/
    bot.py                       # Discord gateway client; forwards every message to the router
  router/
    router.py                    # channel-ID whitelist, then channel-name → handler dispatch
  channels/
    base.py                      # BaseHandler — shared try/except so a handler bug never crashes the bot
    expenses/
      handler.py                 # #expenses — confidence-gates, persists, and threads clarifications
      parsed_entries.py          # Pydantic schema for the LLM's parsed expense output
      prompts.py                 # builds the Gemini prompts (single message + thread re-parse)
  data/
    db.py                        # connection pool, migration runner, all SQL (queries in, typed results out)
    models.py                    # dataclasses/enums mirroring the DB schema (Expense, ExpenseCategory, ...)
  llm/
    gemini.py                    # one function: generate_json(prompt, schema) → validated Pydantic object
db/
  migrations/                    # versioned schema SQL, applied automatically at startup
Dockerfile
docker-compose.yml                # dev: bot + local Postgres, secrets via env_file: .env
docker-compose.prod.yml           # prod: bot only — DB is hosted Supabase Postgres via DATABASE_URL
requirements.txt
.env.example / .env.prod.example
```

**How it fits together:** `bot.py` listens for every Discord message and hands it to `router.py`, which routes it by 
channel name to the corresponding handler. `channels/expenses/` parses the message using Gemini and persists the 
expense in postgres `data/db.py`.

---

## Running locally

### 1. Prerequisites

- Python 3.12+ (matches the Dockerfile's `python:3.12-slim`)
- A Discord server, channel, and bot application — see **Discord setup** below.
- A reachable Postgres instance — either `docker compose up db` from this repo (leave the bot process running outside Docker) with `POSTGRES_HOST=localhost` in `.env`, or any other Postgres you point `POSTGRES_HOST`/`POSTGRES_USER`/etc. at.

#### Discord setup

1. **Create the channel.** Use an existing private server, or create one, and add a channel for expense logging 
(e.g. `#expenses`). If you're running separate dev and prod bot instances (recommended), create two channels — 
one per environment — and note each channel's ID for `ALLOWED_CHANNEL_IDS`: enable **Developer Mode** 
(User Settings → Advanced), then right-click the channel → **Copy Channel ID**.
2. **Create the bot application** at the [Discord Developer Portal](https://discord.com/developers/applications) → 
**New Application**. Under the **Bot** tab, enable the **Message Content** privileged intent — required, 
since this is how the bot reads freeform expense text, not just slash-command arguments — then copy the token for 
`BOT_TOKEN`. If running dev and prod side by side, create a **separate application/token per environment**; 
a shared token means Discord's gateway broadcasts every message to both processes, making the channel whitelist the 
only thing standing between a dev bug and prod data.
3. **Invite the bot to the server.** Under **OAuth2 → URL Generator**, check the `bot` scope, then these permissions 
(matching what `channels/expenses/handler.py` actually does — reacting, opening/locking clarification threads): 
`View Channel`, `Send Messages`, `Create Public Threads`, `Send Messages in Threads`, `Manage Threads`, 
`Read Message History`, `Add Reactions`. Open the generated URL and add the bot to your server.
4. **Add household members** to the server and give them access to the channel — since this is a shared ledger, either 
person's messages in `#expenses` need to reach the bot.

### 2. Clone and install

```bash
git clone <repo>
cd aangan-household-os
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# edit .env — fill in BOT_TOKEN, ALLOWED_CHANNEL_IDS (your #expenses channel ID),
# GEMINI_API_KEY, and the POSTGRES_* vars
```

### 4. Run

```bash
python main.py
```

The bot connects to the DB, runs any pending migrations, then connects to the Discord gateway and prints a log line when ready:

```
INFO aangan.bot.bot | Connected as alfred#0115 (id=...)
```

Post a message in your configured `#expenses` channel and you'll see it logged:

```
INFO aangan.router.router | [ServerName][#expenses] YourName: 1800 groceries
```

`Ctrl-C` to stop.

---

## Running with Docker

```bash
cp .env.example .env
# edit .env — fill in BOT_TOKEN, ALLOWED_CHANNEL_IDS, GEMINI_API_KEY, and POSTGRES_PASSWORD at minimum

docker compose up --build
```

Secrets in `.env` are injected as env vars at runtime via `env_file:` — the file is never copied into the image. This is the **dev** setup (local Postgres in a container); see below for prod.

To stop and tear down:

```bash
docker compose down        # stops containers, keeps the pgdata volume
docker compose down -v     # also deletes the volume (wipes the database)
```

---

## Running in production

Prod uses a hosted Supabase Postgres project instead of a local container — there's no `db` service to run.

```bash
cp .env.prod.example .env.prod
# fill in BOT_TOKEN, ALLOWED_CHANNEL_IDS, GEMINI_API_KEY, and DATABASE_URL
# (Supabase Session Pooler connection string — see the comments in .env.prod.example
# for why it must be the pooler host, not the direct connection host)

docker compose -f docker-compose.prod.yml up --build -d
```