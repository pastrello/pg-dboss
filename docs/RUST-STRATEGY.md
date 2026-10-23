# Rust evaluation — DBOSS

## Decision
A selective migration, not an immediate rewrite. Language alone does not
improve PostgreSQL I/O latency. Existing PG Intelligence Python collectors
(0.1.8), SQL compatibility checks, repository migrations and operator-tested
installer remain intact until replacement is proven.

| Component | Initial language | Direction |
|---|---|---|
| PG18 query / statistics and historical repository | Python / psycopg | Keep; optional later rewrite |
| Linux/ZFS metrics (high-frequency, low overhead) | Rust prototype | Prefer Rust for new agent |
| eBPF instrumentation | Rust userspace + verified BPF | Research after prototype |
| Advisor rules and statistical models | Python | Keep while algorithms change rapidly |
| Fleet daemon / long-lived polling | Rust after parity | Candidate |
| Packaging / Rocky install and rollback | Bash | Stable entrypoint install.sh |
| PostgreSQL extension (only if justified) | Rust via pgrx | Future, optional |

## Engineering tradeoffs
Rust: predictable native binary, no interpreter/venv for probes, strict ownership
and memory safety; but more complex build, cross-arch linking, ABI/toolchain
management, TLS integration, libpq alternative and development iteration.
Python: fast prototyping and rich DB ecosystem, adequate for low-frequency
read-only polls when SQL dominates runtime. Psycopg 3 supports PostgreSQL 18.
Rust postgres/tokio-postgres are available; they do not imply performance
gains without profiling.

## Benchmarks before porting
Measure CPU time, RSS, allocation, end-to-end collection latency, repository
throughput and SQL observer effect. Use same PG18 dataset/load and same feature
set, with 24-hour burn-in and no privilege elevation. Record differences across
Rocky 9/10 and bare-metal/XCP-ng.

## Acceptance
Functional parity, safe error handling, secrets hygiene, bounded memory,
reliable reconnection/retries, PostgreSQL 18 + OpenZFS tests, signed release
artifacts, reproducible build, rollback and no surprise writes.
