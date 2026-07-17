# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A distributed job orchestrator with an optional RL (DQN) scheduler. FastAPI control-plane API + PostgreSQL (source of truth) + Redis Streams (work queue/leases) + pluggable subprocess executors + a Streamlit dashboard. Multi-tenant with API-key/JWT auth and per-tenant quotas.

`REAL_WORLD_BUILD_PLAN.md` is a detailed (and mostly historical) architecture/roadmap doc written as a code review of an earlier prototype — most of its "Phase 0/1/2" items (Postgres persistence, Redis Streams with leases/DLQ, retries, AuthN/AuthZ, multi-tenancy) are already implemented. Treat it as background on *why* things are shaped this way, not as an accurate list of outstanding work — check current code before trusting a specific item in it.

## Commands

Local dev (no Docker):
```bash
docker run -d -p 6379:6379 redis:7-alpine   # Redis
# ...and a local Postgres reachable at DATABASE_URL (see .env.example)
pip install -r requirements.txt
alembic upgrade head                         # apply DB migrations (src/alembic)

uvicorn src.main:app --reload                # API + in-process scheduler loop
python src/orchestrator/worker.py [worker-id]  # a worker (run more for concurrency)
streamlit run src/dashboard/app.py           # dashboard at :8501
```

Docker Compose (full stack: api, worker, dashboard, redis, postgres):
```bash
docker-compose up --build
docker-compose up -d --scale worker=3        # scale workers
docker-compose --profile prod up --build     # immutable-image prod profile (no bind mounts)
```

Tests:
```bash
python -m pytest                 # full suite (~50 tests, uses sqlite in-memory via tests/conftest.py)
python -m pytest tests/test_worker.py -q
python -m pytest tests/test_worker.py::test_failed_job_is_not_overwritten_as_completed
```
Tests do not need Redis/Postgres running — `api_client` in `tests/conftest.py` swaps in an in-memory SQLite session factory and a fresh `JobManager`/`ApiKeyService`. Tests touching Redis Streams directly (e.g. `test_stream_queue.py`) need a real Redis at `REDIS_HOST`/`REDIS_PORT`.

DB migrations:
```bash
alembic revision -m "message"    # new migration under src/alembic/versions
alembic upgrade head
alembic downgrade -1
```

RL / benchmarking (optional, not required for normal API/worker operation):
```bash
python train_model.py     # offline DQN training -> writes ai_brain.pth (RL_MODEL_PATH)
python benchmark.py       # AI vs FIFO vs strict-priority, writes benchmark_results.json
python test_dag.py        # live DAG dependency smoke test (needs the stack running)
python test_script.py     # floods the live queue with random jobs (needs the stack running)
```

There is no configured linter/formatter/type-checker in this repo (no pyproject.toml, no ruff/mypy config) — don't assume one when validating changes.

## Architecture

### Three planes, one repo
- **Control plane (API)**: `src/main.py` builds the FastAPI app, wires middleware, and — in its `lifespan` — starts the scheduler loop as an `asyncio` task *inside the API process*. There is no separate scheduler service/container; `docker-compose.yml`'s `api`/`api-prod` service *is* the scheduler.
- **Execution plane (workers)**: `src/orchestrator/worker.py` runs as a standalone process/container, pulling from Redis Streams and executing jobs via `src/orchestrator/executors/`.
- **Data plane**: PostgreSQL is the durable source of truth (jobs, runs, dependencies, tenants, api keys, audit log — see `src/db/models/`, migrated via `src/alembic/versions/`). Redis is used only for the ephemeral work queue (Streams), leases, and rate limiting — never as a source of truth.

### Job lifecycle (scheduler → stream → worker)
1. `job_manager.create_job`/`create_dag` (`src/orchestrator/job_manager.py`) persists to Postgres, enforcing tenant quota/executor allowlist (`src/tenancy/policy.py`) and idempotency (`idempotency_key`).
2. `Scheduler.run()` (`src/orchestrator/scheduler.py`) polls all PENDING jobs every `check_interval`, filters to those whose dependencies are COMPLETED (`job_manager.are_dependencies_met`), picks one (EDF-with-priority-tiebreak heuristic, or the DQN agent if `SCHEDULER_MODE=ai`, with heuristic fallback on any AI error), marks it RUNNING, and enqueues it onto the Redis Stream (`src/db/stream_queue.py`).
3. A worker (`run_worker` in `worker.py`) reads from the stream's consumer group, acquires a per-job lease (`src/db/lease_store.py`) with a heartbeat thread, runs the job through `execute_job` (`src/orchestrator/executors/registry.py`, dispatched by `payload["type"]`), persists the run result, and ACKs the stream message only after the terminal state is durable. Messages left unacked past `JOB_STREAM_CLAIM_MIN_IDLE_MS` are reclaimed via `XAUTOCLAIM` (`claim_stale_messages`, called every `RECLAIM_EVERY_N_LOOPS`).
4. On failure, `job_manager.handle_execution_failure` decides retry (with exponential backoff, capped) vs. terminal FAILED + DLQ (`JOB_DLQ_STREAM_KEY`), up to `MAX_JOB_RETRIES`.

Executors (`src/orchestrator/executors/`) are dispatched by `payload["type"]` against **both** a global `EXECUTOR_ALLOWLIST` and a per-tenant allowlist (`tenant_policy.executor_allowlist_for`, stored on `TenantRow.executor_allowlist`) — a job is only runnable if its type is in both. `shell` (arbitrary `subprocess.run(shell=True)`) and `python` (arbitrary module import) are RCE-capable and are **off by default**; only `sleep` is allowlisted out of the box.

### RL scheduler
`SCHEDULER_MODE` is `heuristic` (deterministic EDF, safe default) or `ai`. In `ai` mode, `src/rl_engine/environment.py`'s `encode_state` turns up to `MAX_JOBS_INPUT=15` runnable jobs into a fixed-size feature vector (priority, duration, deadline slack — `FEATURES_PER_JOB=3`), and `RLAgent.select_action` (`src/rl_engine/agent.py`) picks an action index using weights loaded from `RL_MODEL_PATH` (default `ai_brain.pth`). The serving scheduler loads the model read-only and never trains online — training only happens offline via `train_model.py`. Any exception during AI selection falls back to the heuristic (`select_by_edf`) for that tick. `calculate_reward` in `environment.py` is the single definition of the reward function used by `train_model.py`/`benchmark.py`; don't duplicate reward logic elsewhere.

### Auth & multi-tenancy
- Two credential types: long-lived API keys (`src/auth/service.py`, header `X-API-Key` or `Authorization: Bearer`) and JWT/OAuth2 client-credentials for service accounts (`src/auth/jwt_service.py`, `src/auth/service_account_service.py`). Both resolve to a `Principal` (`src/models/auth.py`) with a `tenant_id` and a `Role`.
- Roles are ranked (`ROLE_RANK`): `viewer < producer < operator`. Routes declare a minimum role via `Depends(require_min_role(Role.X))` (see `src/auth/deps.py`); `AUTH_ENABLED=false` bypasses this entirely and treats every request as an operator on the default tenant — used implicitly by some scripts, be careful when reasoning about "is this endpoint protected" without checking the setting.
- Every `job_manager`/`tenant_policy` query is scoped by `tenant_id`; cross-tenant reads return 404, not 403 (see `test_tenant_isolation.py`) — preserve that pattern in new endpoints rather than leaking existence via a 403.
- Rate limiting (`src/tenancy/rate_limit.py`) and request-size limiting (`src/tenancy/middleware.py`) are tenant/request-level guards independent of RBAC.
- `settings.validate_secrets_for_environment()` (`src/core/config.py`) is called at API startup and refuses to boot with default/dev secrets when `ENVIRONMENT=production`.

### Known rough edges (don't be surprised)
- `src/models/auth.py` defines `Principal` **twice** — the second definition (with `subject_id`/`auth_method`, `api_key_id` as a backward-compat property) wins and is what's actually used.
- `src/main.py` has a stray module-level `validate_secrets_for_environment` function duplicating the method on `Settings` — dead code, not called.
- `src/core/orchestrator.py` is an empty leftover file from an earlier duplicate orchestration path; the real path is `src/orchestrator/`.

### Logs & output storage
Run stdout/stderr/error are capped (`MAX_RUN_OUTPUT_CHARS`) and, past `LOG_SPILL_THRESHOLD_CHARS`, spilled to files under `LOG_STORAGE_ROOT` (`src/storage/run_logs.py`, `src/storage/log_store.py`) with only a short preview + `log_ref` kept inline in Postgres. `GET /jobs/{id}/runs/{run_id}/logs?full=true` reads the spilled file back via `load_full_run_logs`.

### Tests mirror the architecture
`tests/conftest.py`'s `api_client` fixture rebinds `job_manager`, `tenant_policy`, and `api_key_service` to a fresh in-memory SQLite-backed session factory per test (monkeypatching the module-level singletons), so tests never touch real Postgres/Redis unless they import `job_stream`/`lease_store` directly. When adding a new module-level singleton service, follow this pattern (constructor takes `session_factory=SessionLocal`) so it stays testable the same way.
