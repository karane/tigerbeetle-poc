# tigerbeetle-poc

Proof-of-concept exploring [TigerBeetle](https://tigerbeetle.com) — a financial transactions database built on double-entry bookkeeping — and benchmarking it against PostgreSQL.

## Project structure

```
tigerbeetle          # TigerBeetle binary (Linux x86_64)
tigerbeetle_demo.py  # demo: create accounts, transfer funds, check balances
benchmark.py         # benchmark: TigerBeetle vs PostgreSQL batch throughput
benchmark.md         # benchmark documentation and sample results
docker-compose.yml   # spins up postgres:16 for the benchmark
requirements.txt     # Python dependencies
```

## Setup

**1. Python dependencies**

Activate your virtualenv first, then:

```bash
pip install -r requirements.txt
```

**2. TigerBeetle binary** (Linux x86_64)

```bash
curl -Lo tigerbeetle.zip https://linux.tigerbeetle.com && unzip -o tigerbeetle.zip && chmod +x tigerbeetle
```

**3. Docker** (required for the benchmark only)

```bash
docker compose up -d
```

## Running the demo

Starts a local TigerBeetle instance, creates accounts, runs transfers, and prints balances.

```bash
python3 tigerbeetle_demo.py
```

## Running the benchmark

Compares TigerBeetle and PostgreSQL batch insert throughput across three modes:

- **TigerBeetle** — native `create_accounts` / `create_transfers`
- **PostgreSQL bulk** — plain `INSERT` with no balance tracking
- **PostgreSQL double-entry** — `UPDATE debits` + `UPDATE credits` + `INSERT` in one transaction (equivalent workload to TigerBeetle)

```bash
docker compose up -d   # start PostgreSQL first
python3 benchmark.py
```

See [benchmark.md](benchmark.md) for a full explanation of the methodology and sample results.
