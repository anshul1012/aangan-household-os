# Aangan — Household OS

A conversational household ledger that runs in a private Discord server. Send a text message in `#money` ("1800 groceries", "paid maid 4000") and it becomes a clean, categorized ledger entry. No app, no form, no friction.

V1 is the expense-tracking module. See `vision.md`, `spec.md`, and `tech.md` for full context.

---

## Code structure

```
main.py                        # entry point — loads config, connects to Discord, runs forever
aangan/
  config.py                    # loads env vars into a typed Config object
  bot.py                       # Discord gateway client; holds the WebSocket connection
  router.py                    # maps channel name → handler module (add new channels here)
  channels/
    dev/handler.py             # #dev — logs incoming messages (smoke-test handler)
Dockerfile
docker-compose.yml             # bot + Postgres; secrets injected via env_file: .env
requirements.txt
.env.example
```

**How routing works:** `bot.py` receives every message and hands it to `router.py`, which looks up the channel name in a `dict` and calls the matching handler. Adding a new channel is one new `channels/<name>/` package plus one line in `router.py`.

---

## Running locally

### 1. Prerequisites

- Python 3.11+
- A Discord bot token with the **Message Content** privileged intent enabled in the [Discord Developer Portal](https://discord.com/developers/applications)

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
# edit .env and set bot_token=<your token>
```

### 4. Run

```bash
python main.py
```

The bot connects to the Discord gateway and prints a log line when ready:

```
INFO aangan.bot | Connected as alfred#0115 (id=...)
```

Post a message in `#dev` and you'll see it logged:

```
INFO aangan.channels.dev.handler | [#dev] YourName: hello
```

`Ctrl-C` to stop.

---

## Running with Docker

```bash
cp .env.example .env
# edit .env — fill in bot_token and POSTGRES_PASSWORD at minimum

docker compose up --build
```

Secrets in `.env` are injected as env vars at runtime via `env_file:` — the file is never copied into the image. On the production VM, place `.env` manually after provisioning (`chmod 600 .env`).

To stop and tear down:

```bash
docker compose down        # stops containers, keeps the pgdata volume
docker compose down -v     # also deletes the volume (wipes the database)
```
