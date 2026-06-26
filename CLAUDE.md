# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This repo is **pre-implementation**. There is no code yet — only three frozen planning docs. Before writing any code, read them; they are the source of truth and define hard invariants:

- `vision.md` — the why, the north star, design principles. Stable.
- `spec.md` — V1 product spec (the expense module only). The frozen behavioral contract.
- `tech.md` — the technical decision record: stack, hosting, and *why each choice was made* (including alternatives rejected and when to revisit).

When these conflict with a request, surface the conflict rather than silently overriding a documented decision. The decision record in `tech.md` §12 is deliberately load-bearing — changing a documented call means updating that record, not just the code.

## What Aangan is

A conversational, shared household ledger for **two people**, operated entirely through a private Discord `#money` channel. A text or voice message ("1800 groceries", "paid maid 4000") becomes a structured, categorized ledger entry. "Household OS" because expenses are the first of several intended modules (investments, TODOs, trips) — architecture should let later modules slot in per-channel without rework.

V1 scope is **spend tracking only**. Income / investments / transfers / budgets / settle-up / NL queries / auto-capture / any web UI are explicitly out of scope (see `spec.md` "Out of scope"). The schema reserves the inactive types so later modules aren't boxed in, but V1 only uses `type=expense`.

## Architecture (the big picture)

**One always-on containerized process** holding a persistent Discord gateway WebSocket. This shape is *forced*, not chosen: reading freeform messages requires the privileged Message Content intent, and voice notes are posted messages with audio attachments — both require a live gateway listener, so serverless is categorically rejected (`tech.md` §1).

The system is built around three swappable seams and one rule that ties them together:

1. **Parser layer (LLM) — "text in → validated JSON out."** The LLM is a *parser, not the system of record*. It translates messy human text into JSON matching the `entry` schema and nothing more. **It never does arithmetic on money and never holds state.** Per-parse it is fed three pieces of context: the fixed category enum, the household glossary, and the known-accounts list. Behind a one-interface module so the model is a one-file swap (models get deprecated — plan for it).

2. **Data-access layer — "queries in, typed results out."** All DB access goes through one module. All storage and all math are deterministic code. This isolates the engine choice (Postgres-in-compose today; the seam exists so SQLite or a later StatefulSet/managed Postgres is a localized edit).

3. **Voice = a pre-stage, not a second path.** Voice note → download audio → transcription API → the **same** text parser. There is exactly one parsing path.

**The load-bearing rule across all three:** the LLM's output is *validated data, never an executed instruction*. This is also why prompt-injection via expense text is harmless by construction — worst case is a wrong entry the user sees and corrects.

### The `entry` model

Everything logged is one `entry` (full field list in `spec.md` §2). Things that are easy to get wrong:

- **`amount` may be negative** — that is how reimbursements/returns are modeled (a negative expense in the *same category*, on the date money came back). No separate type, no link to the original. Full returns are *also* negatives, **not deletions** — deletion silently rewrites a past month/digest. Deletion is reserved only for bogus entries that never should have existed.
- **`occurred_on` vs `logged_at` are distinct.** `occurred_on` is the financial date (defaults to today; NL dates like "yesterday" override). **All reports key off `occurred_on`**, never `logged_at`. Logging is lumpy and retroactive, hence two timestamps.
- **`raw_text` is kept verbatim, always** — it is the audit trail, the re-parse source if the parser improves, and the future corpus for V2 NL queries.
- **Categories are a fixed enum** (`spec.md` §3), passed to the parser as a *constraint*. The parser must return an existing category or explicitly flag "none fit" — it must **never** invent ad-hoc category names, or month-over-month trends break.
- Two small side tables: the **household glossary** (e.g. `Sharma → landlord/Housing`) and **known accounts** (normalizes "hdfc"/"HDFC card" → one account). Every user correction writes to the glossary so the bot asks fewer questions over time.

### Interaction invariants (the UX *is* the product)

The north star is **logging fatigue is the enemy, not missing features**. Concretely:

- **Confidence-gated chattiness**: high → silent ✓ reaction + category emoji (the ~90% case); medium → one-line reply with buttons that also writes the glossary mapping; low → a real question. Driven by the LLM's `confidence` + `needs_clarification`.
- **Hard code rule (not a prompt instruction):** if `amount` is null/unparseable, **force a clarification regardless of the confidence the model claims.** Money is the one field the model may never guess.
- **Acknowledge fast, resolve on parse:** react immediately on receipt (👀) and resolve to ✓ once parsed, so the ~1–3s LLM round-trip never reads as a dropped message.
- **Voice always shows its parsed line before committing** (even at high confidence) — transcription stacks a second error layer, especially on numbers.
- **Everything is reversible** — react ❌ to delete the last entry, ✏️ or plain-language reply to correct. Reversibility *is* trustworthiness.
- **A dropped entry is the worst possible outcome.** Malformed/schema-invalid LLM JSON must never crash and never silently drop — always fall back to a clarification.

## Planned stack & infrastructure

(From `tech.md` — not yet built. Establish actual build/test/run commands as code lands; do not invent them before then.)

- **Python** + **discord.py** (gateway + Message Content intent).
- **Docker (arm64)** from day one — a two-container `docker-compose`: the bot + **PostgreSQL** (`postgres:16`, major version pinned).
- **APScheduler**, in-process — two jobs only: recurring-expense confirmation prompts and the Sunday digest. No queue/worker tier.
- **matplotlib → PNG** for `/report` (a gateway slash command, **not** an HTTP endpoint). No web server in V1.
- Small-to-mid LLM via API for parsing; Whisper-class API for transcription. **Verify the current model + pricing at build time** — the docs deliberately don't hard-code these.
- Host: **Oracle Cloud Always Free** ARM VM. The VM is disposable ("cattle, not pets"): all durable state is the DB, backed up nightly via `pg_dump` to a private GitHub repo. The backup is load-bearing, not housekeeping — it is what makes the terminable free VM safe for financial data.

### ARM / compose gotchas to respect

- **Every dependency must have an arm64 build** — check before adding anything with native binaries (the current stack is fine: official Python images are multi-arch, discord.py is pure Python, Postgres has arm64 images).
- Bot must not connect before Postgres is ready: db healthcheck + `depends_on: condition: service_healthy` **and** connection-retry logic in the bot.
- Postgres data dir lives in a **named Docker volume**, not the container layer. Bumping the Postgres *major* version needs a dump/restore (pinning `postgres:16` avoids surprise upgrades).

## Secrets

Credentials (Discord token, LLM/transcription API keys, Postgres user/password) come from a **gitignored `.env`**, never committed, never baked into the cloud-init script. Note: `.env` already exists in the repo root but **there is no `.gitignore` yet** — add one before the first commit that could stage `.env`. Secrets are *not* in the DB dump, so "the backup" means the DB dump **plus** a secure off-box copy of secrets.
