# TigerBeetle Manual Demo

Step-by-step guide to spin up a local TigerBeetle node and issue commands by hand.

---

## 1. Format a data file

TigerBeetle stores everything in a single binary file. You must format it before first use.

```bash
./tigerbeetle format --cluster=0 --replica=0 --replica-count=1 manual.tigerbeetle
```

| Flag | Meaning |
|------|---------|
| `--cluster=0` | Cluster ID (just `0` for local dev) |
| `--replica=0` | This replica's index (0-based) |
| `--replica-count=1` | Single-node cluster |

---

## 2. Start the server

Open a **first terminal** and keep it running:

```bash
./tigerbeetle start --addresses=3000 manual.tigerbeetle
```

TigerBeetle listens on port `3000`. Leave this terminal open.

---

## 3. Open the REPL

Open a **second terminal**:

```bash
./tigerbeetle repl --cluster=0 --addresses=127.0.0.1:3000
```

You'll see a `>` prompt. Everything below is typed there.

---

## 4. Create accounts

TigerBeetle accounts use **double-entry bookkeeping**: every transfer debits one account and credits another.

```
> create_accounts id=1 ledger=700 code=10, id=2 ledger=700 code=10;
```

- `id` — unique u128 (use simple integers for demos)
- `ledger` — groups accounts by currency/asset (e.g. 700 = USD)
- `code` — user-defined category (e.g. 10 = checking)

A successful response prints nothing (empty results = no errors).

---

## 5. Check account balances

```
> lookup_accounts id=1, id=2;
```

You should see both accounts with:
- `debits_posted = 0`
- `credits_posted = 0`
- `debits_pending = 0`
- `credits_pending = 0`

---

## 6. Transfer funds

Send 500 units from account 1 → account 2:

```
> create_transfers id=1 debit_account_id=1 credit_account_id=2 ledger=700 code=1 amount=500;
```

| Field | Meaning |
|-------|---------|
| `debit_account_id` | Money leaves this account |
| `credit_account_id` | Money enters this account |
| `ledger` | Must match the accounts' ledger |
| `amount` | Units transferred (integer, no decimals) |

---

## 7. Verify the balances changed

```
> lookup_accounts id=1, id=2;
```

Expected:
- Account 1: `debits_posted = 500` (sent)
- Account 2: `credits_posted = 500` (received)

---

## 8. Do another transfer (account 2 → account 1)

```
> create_transfers id=2 debit_account_id=2 credit_account_id=1 ledger=700 code=1 amount=200;
```

Check again:
```
> lookup_accounts id=1, id=2;
```

Expected net:
- Account 1: `debits_posted=500, credits_posted=200` → net balance = −300
- Account 2: `debits_posted=200, credits_posted=500` → net balance = +300

Net balance formula: `credits_posted - debits_posted`

---

## 9. Linked transfers (atomic chain)

Linked transfers form a **chain**: every transfer in the chain gets `flags=linked` except the last one. TigerBeetle commits all of them or none — if any single one fails, the entire chain is rolled back.

**Scenario:** a three-leg settlement where account 3 acts as an intermediary.

First, create the third account:

```
> create_accounts id=3 ledger=700 code=10;
```

Now issue three transfers as one atomic chain — id=3, id=4, id=5:

```
> create_transfers id=3 debit_account_id=1 credit_account_id=3 ledger=700 code=1 amount=100 flags=linked, id=4 debit_account_id=3 credit_account_id=2 ledger=700 code=1 amount=60  flags=linked, id=5 debit_account_id=3 credit_account_id=2 ledger=700 code=1 amount=40;
```

The three steps:
1. Account 1 → Account 3 : 100 (fund the intermediary)
2. Account 3 → Account 2 :  60 (first payout leg)
3. Account 3 → Account 2 :  40 (second payout leg, **no** `flags=linked` — marks the end of the chain)

Verify the chain landed atomically:

```
> lookup_accounts id=1, id=2, id=3;
```

Expected (on top of the balances from steps 6–8):
- Account 3: `debits_posted=100, credits_posted=100` → net zero (intermediary fully settled)

**To see the rollback in action**, try a chain where the last transfer has a duplicate id that already exists:

```
> create_transfers id=6 debit_account_id=1 credit_account_id=2 ledger=700 code=1 amount=50 flags=linked,
                  id=7 debit_account_id=1 credit_account_id=2 ledger=700 code=1 amount=50 flags=linked,
                  id=3 debit_account_id=1 credit_account_id=2 ledger=700 code=1 amount=50;
```

`id=3` already exists, so the whole chain (id=6, id=7, id=3) is rejected. Account balances stay unchanged.

---

## 10. Look up a transfer

```
> lookup_transfers id=1;
```

Returns the full transfer record including timestamp, amount, and both account IDs.

---

## 10. Cleanup

Stop the server with `Ctrl+C` in the first terminal. Delete the data file to start fresh:

```bash
rm manual.tigerbeetle
```

---

## Quick reference

| Command | What it does |
|---------|-------------|
| `create_accounts id=N ledger=L code=C` | Create one or more accounts |
| `lookup_accounts id=N, id=M` | Fetch account state |
| `create_transfers id=N debit_account_id=A credit_account_id=B ledger=L code=C amount=X` | Transfer funds |
| `... flags=linked, ... flags=linked, ... ;` | Atomic chain — all succeed or all roll back |
| `lookup_transfers id=N` | Fetch a transfer record |

**Separate multiple objects with `,` and end the statement with `;`.**


## Check transfers

```bash
get_account_transfers account_id=1 limit=2
```