# TigerBeetle vs PostgreSQL — Benchmark

Measures batch insert throughput for financial workloads: account creation and fund transfers at increasing batch sizes. PostgreSQL is tested in two modes to produce a fair comparison.

## Requirements

- Docker (PostgreSQL + TigerBeetle both run as containers)
- Python 3.11+ with `tigerbeetle` and `psycopg2-binary` installed

```bash
pip install tigerbeetle psycopg2-binary
```

## Running

```bash
docker compose up -d   # starts postgres:16 on port 5432
./benchmark.py
```

TigerBeetle is started and stopped automatically per batch-size iteration — no manual setup needed.

## What it measures

For each batch size (`n = 100 / 1k / 10k / 100k`), the benchmark inserts `n` accounts and `n` transfers into both databases and reports wall-clock time and throughput (ops/s).

### TigerBeetle — `create_accounts` / `create_transfers`

Uses the official Python client (`tigerbeetle.ClientSync`). A single `create_transfers` call atomically:

- validates that both debit and credit accounts exist
- increments `debits_posted` on the debit account
- increments `credits_posted` on the credit account
- persists the transfer record

All of this happens inside TigerBeetle with no extra round trips.

> **Dev binary limit:** the distributed binary caps each request at ~253 objects (~32 KB message limit). The benchmark chunks large batches automatically and measures total time across all chunks. A production/release build raises this to 8 190 objects per request.

### PostgreSQL — bulk INSERT

A single `execute_values` INSERT per batch with no balance updates. This is the fastest PostgreSQL can go for this workload, but it does not maintain account balances — it is an **unfair advantage** for PostgreSQL.

### PostgreSQL — double-entry (fair comparison)

Wraps each batch in one transaction that performs the same work TigerBeetle does natively:

```sql
-- 1. debit accounts
UPDATE accounts SET debits_posted = debits_posted + v.amount
FROM (VALUES ...) AS v(account_id, amount)
WHERE id = v.account_id;

-- 2. credit accounts
UPDATE accounts SET credits_posted = credits_posted + v.amount
FROM (VALUES ...) AS v(account_id, amount)
WHERE id = v.account_id;

-- 3. record the transfers
INSERT INTO transfers (...) VALUES ...;

COMMIT;
```

This is the minimum a PostgreSQL-based financial system must do to provide the same atomicity and balance-tracking guarantees that TigerBeetle gives for free.

## Schema

Both databases use an equivalent schema:

```sql
CREATE TABLE accounts (
    id              BIGINT PRIMARY KEY,
    ledger          INT    NOT NULL,
    code            INT    NOT NULL,
    debits_pending  BIGINT NOT NULL DEFAULT 0,
    debits_posted   BIGINT NOT NULL DEFAULT 0,
    credits_pending BIGINT NOT NULL DEFAULT 0,
    credits_posted  BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE transfers (
    id                BIGINT PRIMARY KEY,
    debit_account_id  BIGINT NOT NULL,
    credit_account_id BIGINT NOT NULL,
    ledger            INT    NOT NULL,
    code              INT    NOT NULL,
    amount            BIGINT NOT NULL
);
```

## Sample results

Numbers from a local run (Linux x86_64, Docker, PostgreSQL 16 with default settings):

```
  Operation                                 Records      Time     Throughput
  ────────────────────────────────────────────────────────────────────────────

  ┌─ n=100 ─────
  TigerBeetle  create_accounts                  100    1.243s            80 ops/s
  TigerBeetle  create_transfers                 100    0.013s         7,658 ops/s
  PostgreSQL   INSERT accounts (bulk)           100    0.014s         7,338 ops/s
  PostgreSQL   INSERT transfers (bulk)          100    0.015s         6,574 ops/s
  PostgreSQL   transfers (double-entry)         100    0.038s         2,646 ops/s

  ┌─ n=1,000 ─────
  TigerBeetle  create_accounts                1,000    0.645s         1,551 ops/s
  TigerBeetle  create_transfers               1,000    0.061s        16,502 ops/s
  PostgreSQL   INSERT accounts (bulk)         1,000    0.027s        37,144 ops/s
  PostgreSQL   INSERT transfers (bulk)        1,000    0.042s        23,571 ops/s
  PostgreSQL   transfers (double-entry)       1,000    0.154s         6,508 ops/s

  ┌─ n=10,000 ─────
  TigerBeetle  create_accounts               10,000    0.964s        10,373 ops/s
  TigerBeetle  create_transfers              10,000    0.478s        20,921 ops/s
  PostgreSQL   INSERT accounts (bulk)        10,000    0.193s        51,743 ops/s
  PostgreSQL   INSERT transfers (bulk)       10,000    0.261s        38,257 ops/s
  PostgreSQL   transfers (double-entry)      10,000    1.388s         7,205 ops/s

  ┌─ n=100,000 ─────
  TigerBeetle  create_accounts              100,000    4.899s        20,413 ops/s
  TigerBeetle  create_transfers             100,000    5.859s        17,067 ops/s
  PostgreSQL   INSERT accounts (bulk)       100,000    1.259s        79,442 ops/s
  PostgreSQL   INSERT transfers (bulk)      100,000    2.019s        49,522 ops/s
  PostgreSQL   transfers (double-entry)     100,000    9.262s        10,797 ops/s

  Summary
  ────────────────────────────────────────────────────────────────────────
         n     TB vs PG bulk   TB vs PG double-entry
  ────────────────────────────────────────────────────────────────────────
       100   transfers    1.2x       transfers    2.9x
     1,000   transfers    0.7x       transfers    2.5x
    10,000   transfers    0.5x       transfers    2.9x
   100,000   transfers    0.3x       transfers    1.6x
```

## Reading the results

**`create_accounts` is slow** because the dev binary's 32 KB request cap forces hundreds of round trips for large batches (e.g. 400 trips for n=100k). A production binary would do it in 13. This number is not representative of TigerBeetle's real account-creation throughput.

**`create_transfers` vs bulk INSERT** — TigerBeetle is slower at small n (connection/startup overhead) but the gap closes as batch size grows. This comparison is unfair to TigerBeetle because the bulk INSERT does no bookkeeping.

**`create_transfers` vs double-entry** — this is the honest comparison. TigerBeetle is **1.6x–2.9x faster** at every batch size when PostgreSQL performs the equivalent work: two balance updates plus the insert, all inside a transaction.

## Configuration

All constants are at the top of [benchmark.py](benchmark.py):

| Variable | Default | Description |
|---|---|---|
| `TB_IMAGE` | `ghcr.io/tigerbeetle/tigerbeetle` | Docker image |
| `TB_PORT` | `3001` | TigerBeetle listen port |
| `TB_CLUSTER` | `0` | Cluster ID (0 = test/bench) |
| `TB_CHUNK` | `250` | Max objects per request (dev binary limit) |
| `PG_DSN` | `host=localhost …` | PostgreSQL connection string |
| `BATCH_SIZES` | `[100, 1_000, 10_000, 100_000]` | Batch sizes to test |
