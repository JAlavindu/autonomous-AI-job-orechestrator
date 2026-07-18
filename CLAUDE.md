# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A distributed job orchestrator with an optional RL (DQN) scheduler. FastAPI control-plane API + PostgreSQL (source of truth) + Redis Streams (work queue/leases) + isolated per-job subprocess runners + a Streamlit dashboard. Multi-tenant with API-key/JWT auth and per-tenant quotas.

Two docs in the repo are **historical, not current**:
- `README.md` describes the early prototype (Redis as the only datastore, no auth, no Postgres) — its Quick Start commands work but its architecture claims are outdated. Trust this file and the code.
- `REAL_WORLD_BUILD_PLAN.md` is a roadmap written as a code review of that prototype. Phases 0–2 (Postgres persistence, Redis Streams with leases/DLQ, retries, AuthN/AuthZ, multi-tenancy) are fully implemented, and Phase 3's first increment (isolated runner + per-job resource limits) is done. Still outstanding from Phase 3: worker autoscaling by queue depth, resource features in the DQN state vector, and a `DockerRunner` behind `RUNNER=docker`. Treat the doc as background on *why* things are shaped this way — check current code before trusting a specific item.

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
python -m pytest                 # full suite (69 tests, ~90s; uses sqlite in-memory via tests/conftest.py)
python -m pytest tests/test_worker.py -q
python -m pytest tests/test_worker.py::test_failed_job_is_not_overwritten_as_completed
```
Tests need no infrastructure: `api_client` in `tests/conftest.py` swaps in an in-memory SQLite session factory and a fresh `JobManager`/`ApiKeyService`. Infra-dependent tests **auto-skip** when their backend is unreachable: `test_db_schema.py` (needs Postgres at `DATABASE_URL`), `test_stream_queue.py` (needs Redis at `REDIS_HOST`/`REDIS_PORT`), and the memory-limit test in `test_subprocess_runner.py` (needs Unix `setrlimit`; always skips on Windows). A green run on a bare Windows machine is 64 passed / 5 skipped — those skips are unverified surface, not passing tests. `test_subprocess_runner.py` spawns real child interpreters, so it is slower than the rest.

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
- **Execution plane (workers)**: `src/orchestrator/worker.py` runs as a standalone process/container, pulling from Redis Streams and executing each job in an **isolated child process** via `src/orchestrator/runners/`.
- **Data plane**: PostgreSQL is the durable source of truth (jobs, runs, dependencies, tenants, api keys, audit log — see `src/db/models/`, migrated via `src/alembic/versions/`). Redis is used only for the ephemeral work queue (Streams), leases, and rate limiting — never as a source of truth.

### Job lifecycle (scheduler → stream → worker → runner)
1. `job_manager.create_job`/`create_dag` (`src/orchestrator/job_manager.py`) persists to Postgres, enforcing tenant quota/executor allowlist (`src/tenancy/policy.py`) and idempotency (`idempotency_key`). An optional `resource_req` (`ResourceReq` in `src/models/job.py`: `cpu_seconds`, `memory_mb`, `timeout_seconds`) round-trips through the `jobs.resource_req` JSONB column.
2. `Scheduler.run()` (`src/orchestrator/scheduler.py`) polls all PENDING jobs every `check_interval`, filters to those whose dependencies are COMPLETED (`job_manager.are_dependencies_met`), picks one (EDF-with-priority-tiebreak heuristic, or the DQN agent if `SCHEDULER_MODE=ai`, with heuristic fallback on any AI error), marks it RUNNING, and enqueues it onto the Redis Stream (`src/db/stream_queue.py`).
3. A worker (`run_worker` in `worker.py`) reads from the stream's consumer group, acquires a per-job lease (`src/db/lease_store.py`) with a heartbeat thread, runs the job through `runner.run(job, executor_allowlist=...)` (`src/orchestrator/runners/`), persists the run result, and ACKs the stream message only after the terminal state is durable. Messages left unacked past `JOB_STREAM_CLAIM_MIN_IDLE_MS` are reclaimed via `XAUTOCLAIM` (`claim_stale_messages`, called every `RECLAIM_EVERY_N_LOOPS`).
4. On failure, `job_manager.handle_execution_failure` decides retry (with exponential backoff, capped) vs. terminal FAILED + DLQ (`JOB_DLQ_STREAM_KEY`), up to `MAX_JOB_RETRIES`.

### Isolated runner (Phase 3)
`src/orchestrator/runners/` keeps job code out of the worker process. `get_runner()` in its `__init__.py` selects by `settings.RUNNER` (only `subprocess` exists; `docker` is the planned prod implementation) and exposes a module singleton `runner`. `SubprocessRunner`:
- rejects disallowed executor types **before** spawning, via the shared `executor_error_if_disallowed` helper in `executors/registry.py` (single-sourced with `execute_job`'s own check — don't duplicate allowlist logic);
- spawns `python -m src.orchestrator.runners.child` in a new process group/session, passing a JSON envelope (job, allowlist, limits, `result_path`) over **stdin**;
- the child applies `setrlimit` CPU/memory caps (**Unix only** — a graceful no-op on Windows), runs the existing `execute_job` dispatch, and writes its `ExecutionResult` JSON to `result_path` — a file, not stdout, so job code that prints cannot corrupt the protocol;
- the parent enforces the wall-clock timeout (`resource_req.timeout_seconds`, else `DEFAULT_JOB_TIMEOUT_SECONDS`) cross-platform, kills the whole process group on expiry, and returns exit code 124; a child that dies without writing a result (OOM kill, SIGXCPU, crash) is synthesized into a failure carrying the stderr tail.

Consequence: on Windows dev boxes only the timeout is actually enforced; memory/CPU caps require a Unix worker (the Docker `worker` container). The runner returns the same `ExecutionResult` dataclass as executors, so nothing downstream of the worker changed. Tests patch the seam as `worker.runner.run` (see `test_worker.py`).

Executors (`src/orchestrator/executors/`) are dispatched by `payload["type"]` against **both** a global `EXECUTOR_ALLOWLIST` and a per-tenant allowlist (`tenant_policy.executor_allowlist_for`, stored on `TenantRow.executor_allowlist`) — a job is only runnable if its type is in both. `shell` (arbitrary `subprocess.run(shell=True)`) and `python` (arbitrary module import) are RCE-capable and are **off by default**; only `sleep` is allowlisted out of the box. Isolation reduces blast radius but is not a sandbox — allowlisting is still the security boundary.

### RL scheduler
`SCHEDULER_MODE` is `heuristic` (deterministic EDF, safe default) or `ai`. In `ai` mode, `src/rl_engine/environment.py`'s `encode_state` turns up to `MAX_JOBS_INPUT=15` runnable jobs into a fixed-size feature vector (priority, duration, deadline slack — `FEATURES_PER_JOB=3`), and `RLAgent.select_action` (`src/rl_engine/agent.py`) picks an action index using weights loaded from `RL_MODEL_PATH` (default `ai_brain.pth`). The serving scheduler loads the model read-only and never trains online — training only happens offline via `train_model.py`. Any exception during AI selection falls back to the heuristic (`select_by_edf`) for that tick. `calculate_reward` in `environment.py` is the single definition of the reward function used by `train_model.py`/`benchmark.py`; don't duplicate reward logic elsewhere.

### Auth & multi-tenancy
- Two credential types: long-lived API keys (`src/auth/service.py`, header `X-API-Key` or `Authorization: Bearer`) and OAuth2 client-credentials for service accounts — `POST /api/v1/auth/token` (`src/api/auth_routes.py`, deliberately unauthenticated, JSON body not form-encoded) exchanges a `client_id`/`client_secret` (created via `/admin/service-accounts`, operator-only) for a short-lived JWT (`src/auth/jwt_service.py`, TTL `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`). `get_current_principal` (`src/auth/deps.py`) tries JWT decode **first** (cheap, no DB hit), then falls back to API-key lookup — both arrive as `Bearer` credentials and the two spaces can't collide. `JWT_ENABLED=false` is the kill switch for both issuing and accepting tokens. Both credential types resolve to a `Principal` (`src/models/auth.py`) with `subject_id`, `tenant_id`, a `Role`, and `auth_method`; `principal.api_key_id` is a read-only backward-compat alias for `subject_id`. Always construct with `subject_id=` — pydantic silently ignores unknown kwargs, so passing a wrong field name fails at request time, not import time (this exact bug once broke all API-key auth).
- Roles are ranked (`ROLE_RANK`): `viewer < producer < operator`. Routes declare a minimum role via `Depends(require_min_role(Role.X))` (see `src/auth/deps.py`); `AUTH_ENABLED=false` bypasses this entirely and treats every request as an operator on the default tenant — used implicitly by some scripts, be careful when reasoning about "is this endpoint protected" without checking the setting.
- Every `job_manager`/`tenant_policy` query is scoped by `tenant_id`; cross-tenant reads return 404, not 403 (see `test_tenant_isolation.py`) — preserve that pattern in new endpoints rather than leaking existence via a 403.
- All state-changing operations write `audit_log` entries **inside the same transaction** as the mutation: job transitions via `job_manager._audit`, admin credential operations (API-key/service-account create/import/revoke) via the shared `add_audit` helper in `src/db/audit.py` — use `add_audit` for new call sites, never commit inside it, and never put secrets in the payload (name/role/key_prefix/client_id only). Routes pass `actor=f"api:{principal.name}"`; service defaults attribute non-interactive calls to `"system"`. Failed operations (e.g. cross-tenant revoke probes) write nothing.
- Rate limiting (`src/tenancy/rate_limit.py`) and request-size limiting (`src/tenancy/middleware.py`) are tenant/request-level guards independent of RBAC.
- `settings.validate_secrets_for_environment()` (`src/core/config.py`) is called at API startup and refuses to boot with default/dev secrets when `ENVIRONMENT=production`.

### Known rough edges (don't be surprised)
- `POST /auth/token` has no rate limiting (tenant rate limits apply only *after* auth resolves) — a credential brute-force surface to harden before real exposure.
- JWT revocation is TTL-bound: revoking a service account stops new token issuance, but already-issued JWTs stay valid until they expire (60 min default) — there is no token denylist.
- `datetime.utcnow()` is used throughout (`job_manager`, `auth/service`) and emits deprecation warnings on Python 3.12+; prefer `datetime.now(timezone.utc)` in new code.
- On Windows, the runner's memory/CPU limits are silent no-ops — only the wall-clock timeout protects the worker. The `setrlimit` path has only ever been exercised on Linux.

### Logs & output storage
Run stdout/stderr/error are capped (`MAX_RUN_OUTPUT_CHARS`) and, past `LOG_SPILL_THRESHOLD_CHARS`, spilled to files under `LOG_STORAGE_ROOT` (`src/storage/run_logs.py`, `src/storage/log_store.py`) with only a short preview + `log_ref` kept inline in Postgres. `GET /jobs/{id}/runs/{run_id}/logs?full=true` reads the spilled file back via `load_full_run_logs`.

### Tests mirror the architecture
`tests/conftest.py`'s `api_client` fixture rebinds `job_manager`, `tenant_policy`, `api_key_service`, and `service_account_service` to a fresh in-memory SQLite-backed session factory per test (monkeypatching the module-level singletons), so tests never touch real Postgres/Redis unless they import `job_stream`/`lease_store` directly. When adding a new module-level singleton service, follow this pattern (constructor takes `session_factory=SessionLocal`) so it stays testable the same way.
