# Aangan — Household OS — V1 Technical Spec & Decision Record

> Scope: the **technology and infrastructure** for V1 (the expense module). Product behavior lives in `spec.md`; the why and roadmap framing live in `vision.md`. This is a living doc — the stack will churn as modules are added; vision and spec should stay stable.
>
> A guiding principle for this whole document: **for a two-user, low-volume household tool, the selection criterion is not performance or scale — it's "what will still be running in 18 months when I've half-forgotten how it works."** Several choices here are deliberately *more* than V1 strictly needs, justified by the second goal: this project is a **deliberate learning vehicle**, first in a series of escalating-complexity builds. Where a decision is learning-optimized rather than engineering-optimized, that is stated explicitly.

---

## 1. System shape

**One small always-on process**, containerized, on a single VM.

This shape is forced, not chosen. The product reads **freeform messages** ("1800 groceries"), which on Discord requires the privileged Message Content intent over a **persistent gateway WebSocket** — a long-running, always-connected process. Serverless/ephemeral functions cannot hold that connection. **Voice** makes this absolute: a voice note is a *posted message with an audio attachment*, not a slash-command argument, so observing it also requires the gateway. Both committed V1 input methods (freeform text, voice) independently require an always-on listener. (See Decision Record: serverless rejected.)

A pleasant consequence: a process holding a live gateway connection and running scheduled jobs is **not idle**, which is what keeps a free-tier VM from being reclaimed for inactivity.

---

## 2. The stack

| Layer | Choice | Notes |
|---|---|---|
| Language | **Python** | Maintainer-fluency call; the LLM SDKs, charting, and data glue are pleasant here. |
| Discord | **discord.py** | Gateway connection + Message Content intent (freeform + voice). |
| Packaging | **Docker (arm64)** from day one | Two-container `docker-compose`: bot + Postgres. |
| Database | **PostgreSQL in a container** (`postgres:16`, pinned) | Behind a swappable data-access layer. See §4 and Decision Record. |
| Parsing | **Small LLM via API**, behind a swappable parser module | Parser, not system-of-record. Emits validated JSON. See §6. |
| Voice | **Whisper-class transcription API** | Pre-stage feeding the *same* text parser. One parsing path. |
| Scheduling | **APScheduler**, in-process | Recurring confirmations + Sunday digest. No queue/worker infra. |
| Reports | **matplotlib** → PNG posted to channel | No web server in V1. |
| Backup | **Nightly `pg_dump` → private GitHub repo** | Off-box. The thing that makes the VM disposable. See §5. |
| Host | **Oracle Cloud Always Free VM** | See §3. RackNerd (~$36/yr) is the documented fallback. |

Total running cost target: **~$0/month** (free VM) + small LLM/transcription API usage (order of magnitude: cents/month at two-user volume — verify exact model + pricing at build time, since these move).

---

## 3. Hosting & infrastructure

**Provider: Oracle Cloud Infrastructure (OCI) Always Free.** Chosen because it is the only major free tier that is *always* free (no 6/12-month cliff), with no charge until the account is deliberately upgraded to Pay-As-You-Go. (See Decision Record for the AWS/GCP comparison.)

**Instance:** `VM.Standard.A1.Flex` (Ampere ARM), **1 OCPU / 6 GB RAM**, 1 Gbps. Deliberately a *slice* of the 4-OCPU/24 GB free A1 allowance, not the whole thing — the remainder is banked to spin up a **second A1 node later** (V2 dashboard host, or a k3s worker), which is what turns k3s into real multi-node learning rather than single-node cosplay. **Fallback:** AMD micro (1 GB) if A1 capacity is unavailable — enough to run V1; swap to A1 when capacity frees up.

**Image:** Canonical **Ubuntu 24.04 LTS, aarch64 (Minimal)**. ARM build is mandatory on Ampere. Minimal = leaner host, smaller attack surface; everything runs in containers anyway.

**ARM caveat:** every image/binary must have an arm64 build. Non-issue for this stack (official Python images are multi-arch; discord.py is pure Python; Postgres has arm64 images), but check ARM compatibility before adding any dependency with native binaries.

**Networking posture (the secure config and the simple config are the same config):**
- Public subnet, ephemeral public IPv4 (a changing IP is irrelevant for an outbound-only bot; convert to reserved IP only at the V2-dashboard stage).
- **Egress:** allow all (bot dials out to Discord, APIs, GitHub).
- **Ingress: SSH (22) only**, ideally locked to your own source IP. **No other inbound ports** — Discord connects *from* you, never *to* you, so there is nothing to expose. Open 443 only when the V2 dashboard exists.
- Two firewall layers: the OCI **Security List** *and* the host **iptables**. If SSH hangs despite a correct Security List, the host firewall is the usual culprit.

**Instance metadata: enforce IMDSv2-only** (token-required) and disable legacy v1. The metadata endpoint can leak instance credentials via SSRF; v2's required token closes the easy attack. Relevant because the bot ingests untrusted-ish input.

**Provisioning:** a minimal **cloud-init** script installs Docker (arm64), the compose plugin, and git, and adds the default user to the docker group — making VM setup reproducible (infrastructure-as-code in its simplest honest form). Secrets are **not** baked into the init script (they'd sit in metadata in plaintext); they're injected after, by hand. Set a **$1 budget alert** at signup as a tripwire against accidental paid-resource creation.

**The disposable-VM principle:** the VM holds nothing irreplaceable. All durable state is the database, backed up off-box (§5). This is the "cattle not pets" posture, and it is what makes a *free, terminable* VM safe to trust with financial data — OCI may reclaim or terminate Always Free instances with little warning, and that becomes a shrug-and-redeploy rather than a disaster. **The system is stateful; the infrastructure is disposable. The statelessness of the VM is *purchased by* the backup — it is not free.**

---

## 4. Data layer

**PostgreSQL in a container** (`postgres:16`, major version pinned), run via `docker-compose` alongside the bot.

Schema follows the `entry` model in `spec.md` (one core entity, plus a small household-glossary table and a known-accounts list). All storage and math are **deterministic code** — the LLM never touches the database or does arithmetic on money.

**Behind a swappable data-access layer.** All DB access goes through one module ("queries in, typed results out"). This keeps the engine choice cheap to revise, isolates SQL dialect concerns, and provides the clean seam for the later "Postgres-in-compose → Postgres-in-k8s-StatefulSet (or managed Postgres)" step.

**Compose gotchas, handled explicitly:**
- **Startup ordering:** the bot must not connect before Postgres is ready. Use a healthcheck on the db service + `depends_on: condition: service_healthy`, *and* connection-retry logic in the bot (belt and suspenders).
- **Persistence:** the data dir (`/var/lib/postgresql/data`) lives in a **named Docker volume**, not the container layer.
- **Version upgrades:** bumping the Postgres *major* version requires a dump/restore of the data dir — it is not a transparent image swap. Pinning `postgres:16` avoids surprise upgrades.
- **Credentials:** Postgres user/password via env vars from a **gitignored `.env`**, never committed.

> **Alternative on record:** SQLite-in-process is the better *pure-engineering* choice for V1 — sufficient at two-user scale, simpler, fewer failure modes, file-copy backup. Postgres-via-compose was chosen as the **learning-optimized** option (richer multi-container ops, develop-on-target avoids migration dialect bugs, fits the multi-module roadmap). Flipping to SQLite is a localized edit: the data-access module, the compose file, and the backup step. The decision is owned, not accidental.

---

## 5. Backups & recovery

The backup is **not optional housekeeping — it is the load-bearing component** that makes the disposable-VM model real, especially on a terminable free tier.

- **Mechanism:** nightly `pg_dump` → committed to a **private GitHub repo** (off the host). The household ledger is tiny (KB–low MB for years), so a text SQL dump in git is entirely adequate and diff-friendly.
- **Window:** up to ~24h of data loss if the VM dies mid-day. Acceptable for an async household ledger. (Upgrade path if zero-loss ever matters: continuous WAL archiving / WAL-G to object storage — deferred, not needed.)
- **Recovery is a runbook, not magic:** provision new VM → install Docker (cloud-init) → pull/build images → `psql < latest_dump` → re-inject secrets → restart. **Test a restore on day one** — an untested backup is a hope, not a backup.
- **Secrets are state too:** the Discord token and API keys are *not* in the DB dump. Keep them off-box (password manager / reconstructable env). "The backup" = DB dump **plus** a secure copy of secrets.
- **Transient state is lost on restart and that's OK:** an in-flight clarification prompt held in memory evaporates on restart; user just re-logs. The bot is not literally stateless in operation, but loses nothing durable.

---

## 6. Parsing layer (LLM)

- **The LLM is a parser, not the system of record.** It converts messy human text → structured JSON matching the `entry` schema. Code validates the JSON, then owns all storage and math. The LLM never computes on money and never holds state.
- **Swappable parser module:** one interface, "text in → validated JSON out." Swapping models is a one-file change. This matters because models get deprecated/retired — a forced migration someday is a *when*, not an *if*.
- **Context injected per parse:** the fixed category enum, the household glossary, the known-accounts list.
- **Confidence-gated UX** (per `spec.md`): high → silent ✓; medium → button prompt; low → question. **Hard code rule:** if `amount` is null/unparseable, force a clarification regardless of model-claimed confidence — money is the one field the model may never guess.
- **Failure handling:** malformed/schema-invalid JSON → never crash, never silently drop → fall back to a clarification. Prompt-injection in expense text is harmless by construction (output is validated data, never an executed instruction).
- **Voice pipeline:** voice message → download audio attachment → transcription API → **same** text parser. Voice always shows its parsed line before committing (transcription stacks a second error layer, especially on numbers).
- **Model choice:** one small-to-mid model (Haiku-class / Flash-class / mini-class) for everything; no routing until a class of inputs is shown to fail. **Verify the specific current model + pricing at build time** rather than hard-coding figures that will be stale. Latency note: an LLM round-trip is ~1–3s, so the bot acknowledges on receipt (👀) and resolves on parse, so latency never reads as a dropped message.

---

## 7. Scheduling

**APScheduler, in-process.** Two jobs: recurring-expense confirmation prompts (on each template's due date) and the Sunday digest. Two scheduled jobs a week is not a distributed-systems problem — no Redis, no Celery, no worker tier.

## 8. Reports

`/report` (a gateway slash command — *not* an HTTP endpoint) → query → **matplotlib** renders a PNG → posted to the channel. No web server, no dashboard in V1.

## 9. Security posture (summary)

No inbound ports except SSH (ideally IP-locked); IMDSv2-only; secrets in gitignored env, never committed, never in init script; LLM output treated as validated data, never executed instruction; passive monitoring via OCI Cloud Guard + instance monitoring (free, left on).

---

## 10. Deliberately NOT in V1 (and why)

- **FastAPI** — no HTTP client exists yet (slash commands ride the gateway, not HTTP). Real job arrives with the V2 web dashboard (a browser client); add it then, where the learning is real rather than an endpoint nothing calls.
- **Managed database / Supabase / Firebase** — network hop on the hot path, free-tier idle-pause on a quiet bot, and (Firebase) wrong data shape for a relational ledger.
- **Serverless** — cannot hold the gateway connection; categorically incompatible with voice; and it's the opposite of the infra-learning goal.
- **Kubernetes / k3s** — single-node k8s orchestrates nothing; it's cosplay until there's a real fleet. Deferred to the multi-module phase.
- **Budgets-with-alerts, investment performance, NL queries, auto-capture, web dashboard** — product-side V2+ (see `spec.md` / `vision.md`).

---

## 11. Roadmap (technical)

1. **V1 — now:** `docker-compose` (bot + Postgres) on the OCI Always Free VM; cloud-init provisioning; nightly off-box backup; text first, then voice via the same parser.
2. **V2 — web dashboard:** introduce **FastAPI** (now there's a real browser client) + reserved IP + inbound 443; this is where real API/auth/ingress learning happens.
3. **V2 — NL insight queries** and **auto-capture (SMS/email)** — product features that exploit the stored `raw_text` corpus.
4. **Multi-module phase:** second module (investments / TODOs / trips) means *multiple services* — the real justification for **k3s**. Migrate compose → k3s; Postgres-in-compose → **Postgres StatefulSet** (or managed Postgres). This is the genuine stateful-orchestration learning, attached to a real problem.

Each step is a deliberate, documented migration attached to a real need — the migrations themselves (and the judgment behind them) are the resume value, more than any single technology.

---

## 12. Decision record

> The highest-value artifact here. On a resume and in interviews, **a tradeoff you can defend beats a technology you merely used.** Each entry: the call, why, the alternative, and when to revisit.

**Always-on process (not serverless).** *Why:* freeform message reading and voice both require a persistent gateway connection; serverless can't hold it. *Alternative:* slash-commands-only + serverless (rejected — taxes the frictionless UX and can't do voice). *Revisit:* never for the listener; managed always-on platforms (Railway/Render/Fly) are an option only if the infra-learning goal is later considered satisfied.

**Python + discord.py.** *Why:* maintainer fluency; pleasant ecosystem for LLM/charts/data. *Alternative:* Node + discord.js (equivalent; decided on maintainer comfort).

**Docker from day one.** *Why:* containerization is high-value, low-overhead, broadly transferable, and the prerequisite for the later orchestration step; also makes the host a swappable commodity. *Note:* distinct from k8s (orchestration), which is deferred.

**PostgreSQL via local compose (V1).** *Why:* learning-optimized — richer multi-container ops, develop-on-target avoids dialect-porting bugs, fits the multi-module trajectory; local compose has none of the network/idle-pause/StatefulSet problems of managed or k8s Postgres. *Alternative:* SQLite — the better pure-engineering choice at this scale (simpler, sufficient); flip is a localized edit via the data-access layer. *Revisit:* if maintenance simplicity ever outranks learning, or move to StatefulSet/managed at the k3s phase.

**Swappable data-access + parser layers.** *Why:* both the DB engine and the LLM model are things that will change (deprecation, scale, learning migrations); isolating them behind one interface each makes every future swap a one-module change. *Revisit:* never — this is load-bearing for the whole roadmap.

**Host: OCI Always Free.** *Why:* the only major free tier that is *always* free (no cliff) and won't charge until deliberately upgraded; generous spec (A1) with room for a second node. *Alternatives:* AWS new free plan (rejected as a base — 6-month self-closing clock; good only as a deliberate, time-boxed AWS-learning sprint with a migration planned by month 5); GCP always-free e2-micro (too small); Hetzner (~$9.50/mo, cheapest *paid*, no India DC); DigitalOcean Bangalore (~$24/mo, local DC but 2.5× Hetzner — premium not justified for an async bot); RackNerd (~$36/yr, documented fallback if OCI capacity/account friction annoys). *Revisit:* if OCI Always Free is reclaimed/terminated (disposable-VM design makes the move cheap).

**Backup: nightly `pg_dump` → private GitHub repo.** *Why:* off-box durability is what makes the disposable VM safe on a terminable free tier; tiny DB makes a git-committed SQL dump adequate. *Alternative:* continuous WAL archiving (zero-loss; deferred — unneeded at this scale). *Revisit:* if near-zero data loss ever becomes worth the extra moving parts.

**No FastAPI / no web server in V1.** *Why:* no HTTP client exists; slash commands ride the gateway. *Revisit:* the day the V2 dashboard gives a browser a reason to call an endpoint.

**No k8s in V1.** *Why:* single-node orchestration is cosplay; the learning is hollow without a fleet. *Revisit:* at the second module, migrating compose → k3s as a documented step.
