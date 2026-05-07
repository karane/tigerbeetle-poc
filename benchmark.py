#!/home/karane/.pyenv/versions/3.11.7/envs/poc-projects/bin/python3
"""
Benchmark: TigerBeetle vs PostgreSQL — batch insert throughput.

Two PostgreSQL modes are compared:
  • pg_bulk      — bare INSERT (no balance tracking)
  • pg_2entry    — proper double-entry: UPDATE debit + UPDATE credit +
                   INSERT transfer in one transaction; mirrors what
                   TigerBeetle enforces atomically at the DB level.

TigerBeetle note: the distributed binary (debug build) caps each request
at ~253 objects (~32 KB message limit). Large batches are automatically
chunked and total wall-clock time is measured.

Usage:
    docker compose up -d
    ./benchmark.py
"""
import os, subprocess, sys, time
import tigerbeetle as tb
import psycopg2, psycopg2.extras

# ── Config 

TB_IMAGE   = "ghcr.io/tigerbeetle/tigerbeetle"
TB_DB      = f"{os.getcwd()}/bench.tigerbeetle"
TB_PORT    = "3001"
TB_CLUSTER = 0
TB_CHUNK   = 250   # max objects/request in the debug binary

PG_DSN = "host=localhost port=5432 dbname=bench user=bench password=bench"

BATCH_SIZES = [100, 1_000, 10_000, 100_000]

# ── TigerBeetle (Docker) 

def tb_start():
    subprocess.run(["docker", "rm", "-f", "tb-bench"], capture_output=True)
    time.sleep(0.3)
    if os.path.exists(TB_DB):
        os.remove(TB_DB)
    subprocess.run([
        "docker", "run", "--rm",
        "--security-opt", "seccomp=unconfined",
        "-v", f"{os.getcwd()}:/data",
        TB_IMAGE,
        "format", f"--cluster={TB_CLUSTER}",
        "--replica=0", "--replica-count=1", "--development",
        "/data/bench.tigerbeetle",
    ], check=True, capture_output=True)

    server = subprocess.Popen([
        "docker", "run", "--rm", "--name", "tb-bench",
        "--security-opt", "seccomp=unconfined",
        "-v", f"{os.getcwd()}:/data",
        "-p", f"{TB_PORT}:{TB_PORT}",
        TB_IMAGE,
        "start", f"--addresses=0.0.0.0:{TB_PORT}", "--development",
        "/data/bench.tigerbeetle",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    client = tb.ClientSync(cluster_id=TB_CLUSTER, replica_addresses=f"127.0.0.1:{TB_PORT}")
    return server, client

def tb_stop(server, client):
    client.close()
    subprocess.run(["docker", "stop", "tb-bench"], capture_output=True)
    server.wait()

def tb_insert(client, items, fn):
    """Chunk items into TB_CHUNK-sized requests; return total elapsed seconds."""
    t0 = time.perf_counter()
    for i in range(0, len(items), TB_CHUNK):
        fn(items[i : i + TB_CHUNK])
    return time.perf_counter() - t0

# ── PostgreSQL 

def pg_connect():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS transfers;
            DROP TABLE IF EXISTS accounts;
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
        """)
    return conn

def pg_reset(conn):
    with conn.cursor() as cur:
        cur.execute("TRUNCATE transfers, accounts")

def pg_bulk_accounts(conn, rows):
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur, "INSERT INTO accounts (id, ledger, code) VALUES %s",
            rows, page_size=len(rows),
        )

def pg_bulk_transfers(conn, rows):
    """Bare INSERT only — no balance bookkeeping."""
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO transfers "
            "(id, debit_account_id, credit_account_id, ledger, code, amount) VALUES %s",
            rows, page_size=len(rows),
        )

def pg_double_entry_transfers(conn, rows):
    """
    Full double-entry in one transaction: the minimum PostgreSQL work
    needed to match TigerBeetle's atomic create_transfers guarantee.

      1. UPDATE accounts — add debits_posted for every debit account
      2. UPDATE accounts — add credits_posted for every credit account
      3. INSERT transfers
    """
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # (debit_account_id, amount) aggregated per account
            psycopg2.extras.execute_values(cur, """
                UPDATE accounts a
                SET debits_posted = a.debits_posted + v.amount
                FROM (VALUES %s) AS v(account_id, amount)
                WHERE a.id = v.account_id
            """, [(r[1], r[5]) for r in rows])   # (debit_id, amount)

            # (credit_account_id, amount) aggregated per account
            psycopg2.extras.execute_values(cur, """
                UPDATE accounts a
                SET credits_posted = a.credits_posted + v.amount
                FROM (VALUES %s) AS v(account_id, amount)
                WHERE a.id = v.account_id
            """, [(r[2], r[5]) for r in rows])   # (credit_id, amount)

            psycopg2.extras.execute_values(cur, """
                INSERT INTO transfers
                (id, debit_account_id, credit_account_id, ledger, code, amount)
                VALUES %s
            """, rows, page_size=len(rows))

        conn.commit()
    finally:
        conn.autocommit = True

# ── Reporting 

results = []

def record(label, n, elapsed):
    ops_s = int(n / elapsed)
    results.append((label, n, ops_s))
    print(f"    {label:<40} {n:>8,}  {elapsed:>7.3f}s  {ops_s:>12,} ops/s")

# ── Main

def main():
    print("Connecting to PostgreSQL...")
    try:
        pg = pg_connect()
    except psycopg2.OperationalError as e:
        print(f"  ERROR: {e}\n  Is 'docker compose up -d' running?")
        sys.exit(1)

    print(f"  (TigerBeetle: Docker image, chunked at {TB_CHUNK} obj/request)")
    print()
    print(f"    {'Operation':<40} {'Records':>8}  {'Time':>8}  {'Throughput':>13}")
    print("    " + "─" * 76)

    for n in BATCH_SIZES:
        print(f"\n  ┌─ n={n:,} ─────")

        # ── TigerBeetle
        tb_server, tb_client = tb_start()

        accounts = [tb.Account(id=i, ledger=1, code=1) for i in range(1, n + 1)]
        record("TigerBeetle  create_accounts", n,
               tb_insert(tb_client, accounts, tb_client.create_accounts))

        transfers = [
            tb.Transfer(id=i, debit_account_id=i,
                        credit_account_id=(i % n) + 1, ledger=1, code=1, amount=1)
            for i in range(1, n + 1)
        ]
        record("TigerBeetle  create_transfers", n,
               tb_insert(tb_client, transfers, tb_client.create_transfers))

        tb_stop(tb_server, tb_client)

        # ── PostgreSQL
        pg_reset(pg)

        pg_acc_rows = [(i, 1, 1) for i in range(1, n + 1)]
        t0 = time.perf_counter()
        pg_bulk_accounts(pg, pg_acc_rows)
        record("PostgreSQL   INSERT accounts (bulk)", n, time.perf_counter() - t0)

        pg_tr_rows = [(i, i, (i % n) + 1, 1, 1, 1) for i in range(1, n + 1)]

        t0 = time.perf_counter()
        pg_bulk_transfers(pg, pg_tr_rows)
        record("PostgreSQL   INSERT transfers (bulk)", n, time.perf_counter() - t0)

        # reset transfers only so accounts exist for double-entry updates
        with pg.cursor() as cur:
            cur.execute("TRUNCATE transfers")

        t0 = time.perf_counter()
        pg_double_entry_transfers(pg, pg_tr_rows)
        record("PostgreSQL   transfers (double-entry)", n, time.perf_counter() - t0)

    pg.close()

    # ── Summary
    print()
    print("  Summary")
    print("  " + "─" * 72)
    print(f"  {'n':>8}  {'TB vs PG bulk':>16}  {'TB vs PG double-entry':>22}")
    print("  " + "─" * 72)
    for n in BATCH_SIZES:
        row = {l: ops for l, rn, ops in results if rn == n}
        tb_tr      = row.get("TigerBeetle  create_transfers", 1)
        pg_bulk    = row.get("PostgreSQL   INSERT transfers (bulk)", 1)
        pg_2entry  = row.get("PostgreSQL   transfers (double-entry)", 1)
        print(f"  {n:>8,}  {'transfers':>10}  {tb_tr/pg_bulk:>5.1f}x  "
              f"{'transfers':>14}  {tb_tr/pg_2entry:>5.1f}x")

    print()
    print("  double-entry = UPDATE debits + UPDATE credits + INSERT transfer")
    print("  in one transaction — the minimum PostgreSQL needs to match")
    print("  TigerBeetle's atomic balance-tracking guarantee.")


if __name__ == "__main__":
    main()
