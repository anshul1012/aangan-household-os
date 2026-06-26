# Aangan — Household OS — V1 Product Spec (Expense Module)

> Scope: this document specifies **V1 only** — the expense-tracking module. It is the frozen product spec. Tech decisions live in a separate `tech.md`. Vision and rationale live in `vision.md`.

V1 is a **spend tracker**: manual, natural-language logging of household expenses, with automatic categorization, payer attribution, reimbursements, recurring templates, reports, and a weekly digest. Income, investments, transfers, budgets, settle-up, NL queries, auto-capture, and any web UI are explicitly out of scope (see *Out of scope* at the end).

---

## 1. Money model

- **Joint pool with payer attribution.** All money is treated as shared. Who paid, and on which account, is recorded as descriptive metadata only. There is **no** owe/owed balance and **no** settle-up math anywhere in V1.

---

## 2. Data model

Every logged thing is an **`entry`**:

| Field | Meaning |
|---|---|
| `amount` | Numeric. **Negative is valid** (used for reimbursements/returns). |
| `currency` | Defaults to INR (₹). |
| `type` | `expense` \| `income` \| `investment` \| `transfer`. *V1 only uses `expense`*; the others exist in the enum so later modules aren't boxed in. |
| `category` | One value from the fixed enum (§3). |
| `payer_person` | Who fronted it. Defaults to the message sender; overridable by name. |
| `payer_account` | Instrument (UPI, HDFC card, Axis card, Cash…). Only set if mentioned; never prompted for. |
| `occurred_on` | The **financial** date of the transaction. Defaults to today; natural-language dates ("yesterday") override. **Reports key off this.** |
| `logged_at` | Audit timestamp of when it was recorded. Distinct from `occurred_on` because logging is lumpy and retroactive. |
| `raw_text` | The original message, verbatim. Kept always — it is the audit trail, the re-parse source if the parser improves, and the corpus for V2 NL queries. |
| `source` | `text` \| `voice`. |
| `confidence` | Parser's certainty (from the LLM, §6). |
| `status` | `confirmed` \| `pending` \| `auto`. |

**Household glossary** (separate small table): household-specific facts the parser can't guess — e.g. `Sharma → landlord (Housing)`, `Kumar → driver (Help/Services)`. Every correction the user makes writes here. The glossary is injected into the parse prompt so the bot asks fewer questions over time.

**Known accounts** (small user-defined list): normalizes `payer_account` so "hdfc", "HDFC card", "HDFC credit" all resolve to one account, keeping the field report-able later.

---

## 3. Categories (fixed enum, editable by the household)

**Expense categories:** Housing · Utilities · Groceries · Dining · Transport · Health · Help/Services (maid/cook/driver) · Shopping · Subscriptions · Entertainment · Travel · Personal Care · Gifts/Donations · Misc.

The enum is a constraint passed to the parser, not a suggestion. The parser must return an existing category, or explicitly flag "none fit" so a new one can be considered. It must **never** invent ad-hoc category names, or month-over-month trends break.

*(Income and investment categories are defined in the schema for later use but are not active in V1.)*

---

## 4. Interaction grammar

Logging is freeform natural language. The parser extracts: type, amount, category, payer_person, payer_account (if any), and occurred_on.

```
"1800 groceries"                  → Groceries · ₹1800 · today · payer=sender
                                    bot: ✓ 🛒  (silent — reaction only)
"paid maid 4000"                  → Help/Services · ₹4000
                                    bot: ✓ 🧹
"aditi paid 2000 medicines axis"  → Health · ₹2000 · person=Aditi · account=Axis card
                                    bot: ✓ ⚕️
"spent 500 on lunch yesterday"    → Dining · ₹500 · occurred_on=yesterday
                                    bot: ✓ 🍽 (1d ago)
"got back 2000 from the clothes"  → Shopping · −₹2000   (reimbursement, §5)
                                    bot: ✓ ↩️
"paid sharma 30000"               → ambiguous category → button prompt (§4.2)
```

### 4.1 Chattiness — minimal, confidence-gated

The LLM returns a confidence and a `needs_clarification` flag; code maps these to three behaviors:

- **High confidence** (amount clear, category known/learned): **silent** — a ✓ reaction plus a category emoji. No text reply. This is the ~90% common case and the reason logging doesn't feel like work.
- **Medium** (amount clear, category ambiguous): a one-line reply with buttons — e.g. `Paid Sharma ₹30,000 — what's this? [Housing] [Help] [Other]`. One tap logs it **and** writes the mapping to the glossary, so it isn't asked again.
- **Low** (amount or type unparseable): a real question — e.g. `Didn't catch the amount — how much was the groceries?`

**Hard rule (code, not prompt):** if `amount` is null or unparseable, force a clarification regardless of the confidence the model claims. The model may hallucinate a number; money is the one field it is never allowed to guess.

### 4.2 Acknowledge fast, resolve on parse

Because parsing involves an LLM round-trip (~1–3s), the bot reacts immediately on receipt (e.g. 👀 / typing indicator) and resolves to the ✓ once parsed, so latency never reads as a dropped message.

### 4.3 Voice

Voice note → transcription → the **same** text parser (one parsing path). Because transcription stacks a second error-prone stage (numbers especially: "fifteen hundred" → "fifty"), voice notes **always show their parsed line before committing** — `✓ Groceries ₹1800 — correct?` — even at high confidence. Text may stay silent; voice always shows its work.

### 4.4 Corrections (everything is reversible)

- React **❌** to delete the last entry.
- React **✏️** or just reply in plain language: "no, that's transport" / "make it 1900" / "undo".
- Every correction also updates the household glossary.

---

## 5. Reimbursements & returns

**Model: a reimbursement/return is a negative expense in the same category. No separate type, no linking to the original entry.**

- Partial return (returned ₹2000 of a ₹5000 order) → log `−2000` in that category → month nets to ₹3000.
- Full return (returned the whole ₹5000 order) → log `−5000` in that category → nets to ₹0.

One mental model covers every case: **money came back → log what came back as a negative, in the same category, on the date it came back.**

Why negatives and not deletion for full returns: returns cross period boundaries. Deleting the original silently rewrites a past month (one that may already be in a digest/report). A dated negative entry preserves reality — the original outflow stays in its month, the refund lands in its own. Deletion is reserved only for **bogus** entries that never should have existed.

The parser recognizes "got back / refund / reimbursed / returned" as the signal to emit a negative amount.

---

## 6. Parsing (LLM)

- The LLM is a **parser, not the system of record.** It converts messy human text into structured JSON matching the `entry` schema. Code validates that JSON, then owns all storage and all math. The LLM never does arithmetic on money and never holds state.
- Output shape (illustrative):
  ```json
  { "type": "expense", "amount": 1800, "category": "Groceries",
    "payer_person": "self", "payer_account": null,
    "occurred_on": "today", "confidence": 0.95,
    "needs_clarification": false, "clarification": null }
  ```
- Context injected into each parse: the fixed category enum, the household glossary, and the known-accounts list.
- **Failure handling:**
  - *Malformed / schema-invalid JSON* → never crash, never silently drop the entry → fall back to a clarification prompt. A dropped entry is the worst outcome.
  - *Prompt-injection via expense text* → harmless by construction: the LLM only emits JSON that code validates; its output is **data, never an instruction the system acts on.** Worst case is a wrong entry the user sees and corrects.
- **Model choice:** one good small-to-mid model for everything in V1. No routing to a stronger model unless a class of inputs is found to fail. (Specific model chosen in `tech.md`.)

---

## 7. Recurring expenses

Templates, defined once — never re-typed monthly.

- Define: e.g. `Rent · ₹30,000 · monthly · 1st · Housing`.
- On the due date the bot posts: `Rent ₹30,000 — paid? [✓] [change amount] [skip]`. One tap logs it.
- This both removes monthly re-entry and kills the "did we actually pay rent?" ambiguity — recurring items become the thing you *can't* forget rather than the thing you always do.

---

## 8. Reports

`/report week | month | year` plus custom ranges → a **chart image** + a text summary. Reports key off `occurred_on`.

Because income/investments are out of V1, reports are **spend-only**:
- Total spend for the period.
- Spend by category.
- Each category compared to the prior comparable period.

*(Net cashflow — income minus spend — is deferred to whenever income logging is enabled. Noted here so its absence is by design, not a gap.)*

---

## 9. Weekly digest (push)

Auto-posted every Sunday, unprompted:
- The week's total spend.
- Top 3 categories.
- Recurring items due in the coming week.
- One simple anomaly flag (e.g. "Dining up ~40% vs your 8-week average").

The push sustains the habit in weeks when nobody runs `/report`.

---

## 10. Channel

A single **`#money`** channel in the private Discord server is the entire V1 surface.

---

## Out of scope for V1 (deferred — see `vision.md` roadmap)

Income / investment / transfer logging as active flows · net-cashflow reports · budgets with alerts · settle-up / owe-owed math · reimbursement audit links · natural-language insight queries · auto-capture (SMS/email) · web dashboard · any second module (TODOs, trips, investment management).
