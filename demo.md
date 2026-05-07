# Getting Started with TigerBeetle

TigerBeetle is a financial transactions database built around **double-entry bookkeeping** — every transfer debits one account and credits another, atomically. It is designed for high-throughput, append-only ledger workloads.

This guide walks you through the core concepts using this project's demo script.

---

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

This installs the `tigerbeetle` Python client (v0.17.1) and `psycopg2-binary` into your active Python environment. Make sure your virtualenv (or pyenv env) is activated before running this.

---

## 2. Run the demo

```bash
python3 tigerbeetle_demo.py
```

The script does everything automatically:

- Kills any leftover TigerBeetle process
- Formats a fresh database (`demo.tigerbeetle`)
- Starts a local single-node server on port `3000`
- Runs the examples below
- Shuts the server down cleanly

---

## 3. What the demo does — step by step

### Format a new database

Before TigerBeetle can start, you must format the data file. This is a one-time operation per file:

```bash
./tigerbeetle format --cluster=0 --replica=0 --replica-count=1 --development demo.tigerbeetle
```

- `--cluster=0` — logical cluster ID (just `0` for local dev)
- `--replica=0` — this node's index
- `--replica-count=1` — single node (no replication)
- `--development` — disables production safety checks (OK for local use)

### Start the server

```bash
./tigerbeetle start --addresses=3000 --development demo.tigerbeetle
```

Leave this running in a terminal. The Python client connects to `localhost:3000`.

---

### Create accounts

In TigerBeetle, an **account** is a ledger entry — a wallet, a user balance, a cost center, anything with money flowing in or out.

```python
client.create_accounts([
    tb.Account(id=1, ledger=1, code=1),
    tb.Account(id=2, ledger=1, code=1),
])
```

- `id` — unique u128, you assign it (use UUIDs or sequential IDs)
- `ledger` — groups accounts by currency or business unit (e.g. `1` = USD)
- `code` — user-defined category (e.g. `1` = savings, `2` = checking)

After this, both accounts have zero balance.

---

### Transfer funds

A **transfer** moves value from one account to another — atomically.

```python
client.create_transfers([
    tb.Transfer(id=1, debit_account_id=1, credit_account_id=2, ledger=1, code=1, amount=100),
])
```

- `debit_account_id=1` — money leaves account 1 (debits go up)
- `credit_account_id=2` — money arrives at account 2 (credits go up)
- `amount=100` — in your ledger's smallest unit (e.g. cents)
- `ledger` must match both accounts

TigerBeetle enforces that debit and credit are always equal — you can never create or destroy money.

---

### Check balances

```python
for a in client.lookup_accounts([1, 2]):
    print(f"Account {a.id}: debits_posted={a.debits_posted}  credits_posted={a.credits_posted}")
```

Expected output after the transfer above:

```
Account 1: debits_posted=100  credits_posted=0
Account 2: debits_posted=0    credits_posted=100
```

- `debits_posted` — total amount debited (money sent out)
- `credits_posted` — total amount credited (money received)
- Net balance = `credits_posted - debits_posted`

---

### Batch operations

TigerBeetle is optimized for batches — sending many operations in a single call is far more efficient than one-by-one.

```python
# Create 100 accounts at once
client.create_accounts([
    tb.Account(id=i, ledger=1, code=1) for i in range(3, 103)
])

# Send 100 transfers at once
client.create_transfers([
    tb.Transfer(id=i, debit_account_id=1, credit_account_id=i, ledger=1, code=1, amount=10)
    for i in range(3, 103)
])
```

This is the core of TigerBeetle's performance — batching hundreds of transfers into a single consensus round rather than one round per transfer.

---

## 4. Key concepts to remember

| Concept | Meaning |
|---|---|
| **Ledger** | Groups accounts by currency or business unit |
| **Code** | User-defined account/transfer category |
| **Debit** | Money leaving an account |
| **Credit** | Money entering an account |
| **Batch** | Multiple operations in one call — always prefer this |
| **Immutability** | Transfers are append-only; you cannot edit or delete them |

---

## 5. Next steps

- Read [`benchmark.md`](benchmark.md) to see how TigerBeetle compares to PostgreSQL double-entry at scale
- Run `python3 benchmark.py` (requires `docker compose up -d` for Postgres) to reproduce the numbers locally
- Explore [linked transfers](https://docs.tigerbeetle.com/reference/transfers#flags.linked) — atomically chain multiple transfers so they all succeed or all fail together
