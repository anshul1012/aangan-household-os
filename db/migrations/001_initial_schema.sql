-- V1 initial schema: expense tracking module
-- No BEGIN/COMMIT here — the migration runner wraps each file in a transaction.
-- Categories are TEXT (not enum) so new categories can be added without ALTER TYPE migrations.

CREATE TYPE message_source AS ENUM ('text', 'voice');
CREATE TYPE expense_status AS ENUM ('confirmed', 'pending', 'auto');

-- Core table: every logged expense is one row

CREATE TABLE expenses (
    id                BIGSERIAL PRIMARY KEY,
    amount            NUMERIC(12, 2)  NOT NULL,               -- negative = reimbursement/return
    currency          VARCHAR(3)      NOT NULL DEFAULT 'INR',
    category          TEXT            NOT NULL,               -- validated against ExpenseCategory in Python
    tags              TEXT[],                                 -- optional drill-down, e.g. {Swiggy, Blinkit}
    payer_person      TEXT            NOT NULL,
    payer_account     TEXT,                                   -- null unless mentioned in the message
    occurred_on       DATE            NOT NULL,               -- financial date; all reports key off this
    logged_at         TIMESTAMPTZ     NOT NULL DEFAULT now(), -- when it was recorded (distinct from occurred_on)
    raw_text          TEXT            NOT NULL,               -- verbatim original message; never dropped
    source            message_source  NOT NULL DEFAULT 'text',
    confidence        TEXT,                                   -- LLM confidence label: "high" / "mid" / "low"
    status            expense_status  NOT NULL DEFAULT 'pending',
    source_message_id BIGINT                                  -- Discord message that created/is refining this row
);

-- Reports always filter/group by financial date
CREATE INDEX expenses_occurred_on_idx ON expenses (occurred_on);

-- Nullable: future non-thread insert paths (e.g. APScheduler recurring-expense
-- confirmations) may not originate from a single message. A partial unique index
-- (not a plain UNIQUE column) lets multiple historical/future NULLs coexist.
CREATE UNIQUE INDEX expenses_source_message_id_idx
    ON expenses (source_message_id)
    WHERE source_message_id IS NOT NULL;

-- Household glossary: maps freeform names → canonical person + category
-- e.g. "sharma" → display_name="Sharma", category="Housing", note="landlord"
-- Every user correction writes here; injected into parse prompts.

CREATE TABLE household_glossary (
    id            SERIAL PRIMARY KEY,
    raw_name      TEXT            NOT NULL UNIQUE,  -- lowercased lookup key
    display_name  TEXT            NOT NULL,
    category      TEXT            NOT NULL,
    note          TEXT,
    updated_at    TIMESTAMPTZ     NOT NULL DEFAULT now()
);

-- Known accounts: normalises payer_account aliases to one canonical name
-- e.g. "hdfc", "HDFC card", "HDFC credit" → "HDFC Credit Card"

CREATE TABLE known_accounts (
    id             SERIAL PRIMARY KEY,
    alias          TEXT        NOT NULL UNIQUE,
    canonical_name TEXT        NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
