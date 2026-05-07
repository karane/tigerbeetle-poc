#!/home/karane/.pyenv/versions/3.11.7/envs/poc-projects/bin/python3
import subprocess, os, signal, time, sys
import tigerbeetle as tb

DB = "./demo.tigerbeetle"
PORT = "3000"
CLUSTER = 0
TB = "./tigerbeetle"

# ── Setup ─────────────────────────────────────────────────────────────────────

print("🧹 Cleaning previous database...")
subprocess.run(["pkill", "-x", "tigerbeetle"], capture_output=True)
time.sleep(0.5)
if os.path.exists(DB):
    os.remove(DB)

print("⚙️  Formatting TigerBeetle database...")
subprocess.run(
    [TB, "format", f"--cluster={CLUSTER}", "--replica=0", "--replica-count=1", "--development", DB],
    check=True, capture_output=True,
)

print("🚀 Starting TigerBeetle...")
server = subprocess.Popen(
    [TB, "start", f"--addresses={PORT}", "--development", DB],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
time.sleep(1)

client = tb.ClientSync(cluster_id=CLUSTER, replica_addresses=PORT)

def check(results, label):
    for r in results:
        if r.status not in (tb.CreateAccountStatus.CREATED, tb.CreateTransferStatus.CREATED):
            print(f"  ⚠️  {label} error: {r}")

# ── Simple operations ─────────────────────────────────────────────────────────

print("--------------------------------------")
print("👤 SIMPLE OPERATIONS")
print("--------------------------------------")

print("➡️  Creating 2 accounts...")
check(client.create_accounts([
    tb.Account(id=1, ledger=1, code=1),
    tb.Account(id=2, ledger=1, code=1),
]), "create_accounts")

print("➡️  Single transfer (100 from 1 → 2)...")
check(client.create_transfers([
    tb.Transfer(id=1, debit_account_id=1, credit_account_id=2, ledger=1, code=1, amount=100),
]), "create_transfers")

print("➡️  Checking balances...")
for a in client.lookup_accounts([1, 2]):
    print(f"  Account {a.id}: debits_posted={a.debits_posted}  credits_posted={a.credits_posted}")

# ── Batch operations ──────────────────────────────────────────────────────────

print("--------------------------------------")
print("🚀 BATCH OPERATIONS")
print("--------------------------------------")

print("➡️  Creating 100 accounts in batch (IDs 3–102)...")
check(client.create_accounts([
    tb.Account(id=i, ledger=1, code=1) for i in range(3, 103)
]), "create_accounts batch")

print("➡️  Creating 100 transfers (account 1 → each batch account)...")
check(client.create_transfers([
    tb.Transfer(id=i, debit_account_id=1, credit_account_id=i, ledger=1, code=1, amount=10)
    for i in range(3, 103)
]), "create_transfers batch")

print("➡️  Checking a few balances...")
for a in client.lookup_accounts([1, 3, 50, 100]):
    print(f"  Account {a.id}: debits_posted={a.debits_posted}  credits_posted={a.credits_posted}")

# ── Teardown ──────────────────────────────────────────────────────────────────

print("--------------------------------------")
print("🧮 DONE")
print("--------------------------------------")

client.close()
print("🛑 Stopping TigerBeetle...")
server.terminate()
server.wait()
