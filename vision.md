# Aangan — Household OS — Vision

> **Aangan** (आँगन): the central courtyard of a traditional Indian home — the shared, open space the household gathers around and daily life flows through. The name is the vision: a warm, shared center for a household's life, with each concern (expenses, trips, tasks) opening onto it like rooms onto a courtyard.

## What this is

A **shared financial source-of-truth for a two-person household, where the interface is conversation instead of forms.**

Most personal-finance tools make you fill in fields. This one lets you *talk* — a text or voice message in a private Discord channel ("paid the maid 4000", "1800 groceries on hdfc card") becomes a clean, categorized ledger entry. No app to open, no form to fill, no friction.

It is built on top of a private Discord server, one channel per concern. Expense tracking is the first module. Investment management, TODOs, and trip planning are intended later modules of the same system — hence "Household OS," not "expense app."

## The north star

**The enemy is logging fatigue, not missing features.**

Every personal-finance tool dies the same death: around week three, someone forgets to log a few things, the numbers stop being trustworthy, and once the data is untrustworthy nobody opens it again. A feature-thin tool that you actually keep using beats a feature-rich one that rots.

Therefore every design decision is judged against one question: **does this make the conversational, shared, low-friction part better — or does it add a feature at the cost of friction?** When the two conflict, friction loses.

Three consequences of taking this seriously:

- **The common case must feel instant and silent.** Logging an obvious expense should take one short message and get a single ✓ back — no dialogue, no confirmation step. The bot is a fast colleague, not a chatbot.
- **The data must never silently rot.** Recurring expenses are confirmed, not forgotten. Anything ambiguous is surfaced, not guessed-and-buried. A dropped entry is the worst outcome, because it erodes trust invisibly.
- **Everything is reversible.** Reversibility *is* trustworthiness. If correcting a mistake is easy, people trust the system enough to keep feeding it.

## Who it's for

Primarily two people running a shared household (the builder and spouse). This shapes the money model: a **joint pool with payer attribution.** Money is treated as shared; who paid (and on which card) is recorded as descriptive metadata, never as a debt. There is no "you owe me" math. This is a household ledger, not a bill-splitter.

## What good looks like

- Logging an expense is faster than opening any app would be.
- After a month, the bot rarely has to ask what something is — it has learned the household's specifics.
- The weekly digest arrives unprompted and is actually read.
- Six months in, both people still trust the numbers — because they've never seen the system guess wrong and bury it.

## Design principles

1. **Conversational in, structured out.** Humans speak naturally; the system stores clean, disciplined data. An LLM bridges the two — it *translates*, it never computes. All storage and math are deterministic code the LLM never touches.
2. **Stable categories, flexible input.** You can phrase an expense any way you like, but it always lands in a fixed, comparable category. Flexibility on the input side, discipline on the data side — so month-over-month trends stay meaningful.
3. **Capture, don't interrogate.** The bot extracts what you mention and never nags for what you didn't. It asks only when the amount or the nature of the transaction is genuinely unclear.
4. **Push, not just pull.** The system reaches out (weekly digest, recurring confirmations) rather than waiting to be queried. The push is what sustains the habit in quiet weeks.
5. **Modular by channel.** Each household concern is its own Discord channel and its own module. Expenses first; the architecture should let later modules slot in without rework.

## Roadmap shape

**V1 — Spend tracker.** Manual natural-language logging of expenses (text + voice), automatic categorization into a fixed enum, payer attribution, reimbursements as negative expenses, recurring templates, spend reports by week/month/year, and a weekly digest. Deliberately small. (Full detail in `spec.md`.)

**V2 and beyond — in rough priority order:**
- **Natural-language insight queries** — "how much did we spend on groceries this month?" answered conversationally.
- **Auto-capture** — parsing UPI / bank SMS or email receipts so day-to-day spending logs itself and you only correct. This is the feature that attacks logging fatigue at its root.
- **Income, investments, transfers as first-class** — unlocking net-cashflow reporting (the schema already supports these; V1 simply doesn't use them).
- **Budgets with alerts** — added *after* a few months of real data exist, so limits are grounded in actual baselines rather than guesses.
- **A thin web dashboard** — for the structured browsing and slicing that Discord is genuinely bad at.
- **Further household modules** — investment management, TODOs, trip planning.

The ordering reflects the north star: things that reduce friction or deepen trust come before things that add surface area.
