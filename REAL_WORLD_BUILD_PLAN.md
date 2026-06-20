# Real-World Build Plan — Autonomous AI Job Orchestrator

**Goal:** Evolve the current prototype into a production-grade, multi-tenant, AI-driven job orchestration platform that organizations can deploy to schedule and run real workloads (data pipelines, ML training, batch ETL, CI tasks, report generation, etc.) with SLA guarantees.

This document is written from three perspectives, as requested:

- **System Architect** — target architecture, scalability, reliability, data model.
- **End User** — who uses it, what they need, and the experience we must deliver.
- **Software Engineer** — concrete code-level gaps, fixes, and an actionable, phased roadmap.

> Status legend used below: ✅ exists / works · ⚠️ exists but broken or unsafe · ❌ missing

---

## 1. Where the project is today (honest baseline)

### 1.1 What works
- ✅ FastAPI service with `POST/GET /api/v1/jobs/` endpoints and Pydantic models (`src/models/job.py`).
- ✅ Redis-backed state store + a Redis list used as a work queue (`src/db/redis_store.py`).
- ✅ A decoupled scheduler loop (`src/orchestrator/scheduler.py`) and pull-based worker (`src/orchestrator/worker.py`).
- ✅ A DQN agent + state/reward encoding (`src/rl_engine/`), an offline trainer (`train_model.py`), and a benchmark harness (`benchmark.py`).
- ✅ DAG dependency gating (`job_manager.are_dependencies_met`).
- ✅ Pluggable executors (`shell`, `python`, `sleep`) behind a registry.
- ✅ Streamlit observability dashboard and a Docker Compose dev cluster.

### 1.2 What is broken or unsafe (found in code review)
These must be fixed before any real use — several are correctness or security blockers:

| # | Severity | Location | Problem |
|---|----------|----------|---------|
| B1 | 🔴 Blocker | `src/orchestrator/executors/shell.py:16` | `subprocess.run(...)` passes `timeout=` **twice** → `SyntaxError`, the module cannot import. Shell jobs are completely broken. |
| B2 | 🔴 Blocker | `src/orchestrator/worker.py:30-55` | Worker runs the executor, sets `COMPLETED`, then **sleeps `estimated_duration` again and unconditionally sets `COMPLETED` a second time** — even for jobs that just `FAILED`. Failures are silently overwritten as success. |
| B3 | 🔴 Security | `shell.py` / `python_module.py` | Executors run **arbitrary shell commands (`shell=True`) and import arbitrary modules** from an unauthenticated API → remote code execution. |
| B4 | 🟠 Major | `src/orchestrator/scheduler.py:19,22` | Agent inits with `epsilon=1.0` and loads weights but **not epsilon/optimizer state** → a freshly started "production" scheduler makes ~100% **random** scheduling decisions and keeps mutating the live model. |
| B5 | 🟠 Major | `scheduler.py` (online `train_step`) | Training happens live, per single transition, with **no replay buffer and no target network** → unstable, non-reproducible, and couples model training to request serving. |
| B6 | 🟠 Major | `redis_store.py` | Redis is the **only** persistence layer (in-memory). No durable history, no audit trail, no relational queries; queue + state + (implicitly) model feedback all on one Redis. |
| B7 | 🟠 Major | scheduler timeout logic | "Zombie killer" marks a job `FAILED` by wall-clock only; it does **not** remove it from the Redis queue or use worker leases/heartbeats → races and duplicate execution. |
| B8 | 🟡 Minor | `encode_state` | Live scheduler feeds `pending_jobs[:15]` **unsorted**, so action-index→job mapping is arbitrary between loop iterations (trainer sorts by deadline; serving does not → train/serve skew). |
| B9 | 🟡 Minor | reward definitions | README (`+10/-5`), `environment.calculate_reward` (`+10/-10`), and scheduler failure penalty (`-5`) **disagree**. |
| B10 | 🟡 Cleanup | repo | Dead/empty files: `src/orchestrator/executor.py`, `src/models/dag.py`, `src/rl_engine/networks.py`, `src/rl_engine/reward.py`, `src/api/schemas.py`, `tests/test_scheduler.py`; plus a parallel in-process `src/core/orchestrator.py` that duplicates the worker. |

### 1.3 What is missing for production
- ❌ AuthN/AuthZ, multi-tenancy, rate limiting, secrets management.
- ❌ Durable datastore + migrations; ❌ retries / dead-letter queue / idempotency.
- ❌ Worker isolation & resource limits (jobs run in the orchestrator's own process).
- ❌ Structured logging, metrics (Prometheus), tracing, alerting.
- ❌ Job lifecycle features users expect: cancel, pause, retry, schedules/cron, priorities per tenant, logs/artifacts retrieval.
- ❌ CI/CD, IaC, Kubernetes deployment, HA Redis, backups.
- ❌ Model lifecycle: versioning, offline eval gate, safe rollout, shadow mode, fallback heuristic.

---

## 2. System Architect view — target architecture

### 2.1 Guiding principles
1. **Separate the control plane from the data/execution plane.** The orchestrator decides *what* runs; isolated workers decide *how* it runs.
2. **Durable source of truth ≠ hot queue ≠ cache.** Postgres for truth/history, a real broker for work distribution, Redis for ephemeral cache/leases.
3. **The AI is an advisor, not a single point of failure.** Every AI decision must have a deterministic heuristic fallback and a kill-switch.
4. **At-least-once execution + idempotency**, not "hope nothing crashes."
5. **Everything observable**: logs, metrics, traces, and audit from day one.

### 2.2 Target component diagram

```text
                         ┌─────────────────────────────────────────────┐
                         │                Clients                       │
                         │  Web UI · CLI · SDK · CI systems · cron apps  │
                         └───────────────┬─────────────────────────────┘
                                         │ HTTPS (REST + WebSocket)
                                  ┌──────▼───────┐
                                  │  API Gateway │  auth, rate limit, tenancy
                                  └──────┬───────┘
                ┌────────────────────────┼───────────────────────────┐
                │                        │                           │
        ┌───────▼────────┐      ┌────────▼────────┐         ┌────────▼─────────┐
        │  Orchestrator  │      │  Job/State API  │         │  Observability   │
        │  (Scheduler)   │      │  (CRUD + query) │         │  /metrics /logs  │
        │  AI advisor +  │      └────────┬────────┘         └──────────────────┘
        │  heuristic     │               │
        └───┬────────┬───┘               │
            │decide  │enqueue            │
            │        ▼                   ▼
            │  ┌───────────────┐  ┌─────────────────────┐
            │  │ Message Broker│  │   Postgres (truth)  │  jobs, runs, deps,
            │  │ (Redis Streams│  │   + history/audit   │  tenants, schedules
            │  │  / RabbitMQ / │  └─────────────────────┘
            │  │  Kafka)       │            ▲
            │  └──────┬────────┘            │ state updates
            │         │ lease/ack           │
            │   ┌─────▼──────────────────────┐
            │   │   Worker Pool (autoscaled)  │  heartbeats, leases,
            │   │   isolated executors:       │  resource limits,
            │   │   container / k8s Job /     │  sandboxing
            │   │   subprocess (dev)          │
            │   └─────────────────────────────┘
            │
      ┌─────▼───────────────┐
      │ Model Registry + RL │  offline training, eval gate, versioned
      │ training pipeline   │  policies, shadow/canary rollout
      └─────────────────────┘
```

### 2.3 Key architectural decisions

| Concern | Prototype | Target | Rationale |
|---------|-----------|--------|-----------|
| Source of truth | Redis | **PostgreSQL** (SQLAlchemy + Alembic) | Durable history, relational queries, audit, transactions. |
| Work distribution | Redis list `rpush/blpop` | **Redis Streams** (consumer groups) → optionally RabbitMQ/Kafka | Acks, leases, consumer groups, redelivery, DLQ. |
| Cache / leases | n/a | Redis | Hot job state, worker heartbeats, distributed locks. |
| Execution | in-process subprocess/import | **Isolated runners**: subprocess (dev) → Docker/K8s Jobs (prod) | Resource limits, security, blast-radius containment. |
| Scheduler decision | live DQN, eps=1.0 | **Loaded frozen policy (eval mode) + heuristic fallback + kill switch** | Determinism, safety, reproducibility. |
| Training | online in serving loop | **Offline pipeline** with replay buffer, target net, eval gate | Stability, reproducibility, safe rollout. |
| Deploy | docker-compose, code mounted | **Containers + Helm/K8s**, immutable images | HA, autoscaling, rollbacks. |

### 2.4 Execution semantics (the contract)
- **At-least-once delivery** via broker consumer groups; workers must **ack** only after a terminal state is persisted.
- **Leases + heartbeats:** a worker holds a lease (visibility timeout). If heartbeats stop, the message is redelivered. This replaces the naive wall-clock "zombie killer".
- **Idempotency:** each run keyed by `(job_id, attempt)`; executors should be idempotent or guarded by an idempotency key so redelivery is safe.
- **Retry policy:** configurable `max_attempts`, backoff; exhausted attempts → **Dead Letter Queue** + `FAILED` terminal state.

---

## 3. End User view — who uses it and what they need

### 3.1 Personas & jobs-to-be-done
1. **Platform / DevOps engineer (operator):** deploy, scale, set quotas, watch SLAs, get paged on failures. Needs HA, dashboards, alerts, and a "pause the world" control.
2. **Application developer (producer):** submit jobs from code/CI, set priority + deadline + dependencies, poll status, fetch logs/artifacts, cancel/retry. Needs a clean SDK/CLI and predictable behavior.
3. **Data/ML engineer:** schedule recurring pipelines (cron), express multi-step DAGs, backfill. Needs schedules, DAG visualization, and run history.
4. **ML / optimization owner:** tune the reward function, evaluate the policy vs. baselines, promote new models safely. Needs the training pipeline, eval gate, and A/B comparison.

### 3.2 End-user features to build (beyond current CRUD)
- **Auth & tenancy:** API keys / OAuth, per-tenant isolation and quotas.
- **Full job lifecycle:** submit, **cancel**, **retry**, pause/resume, priority change, with status transitions exposed via API + WebSocket events.
- **Schedules:** cron-style recurring jobs and one-shot "run at" jobs.
- **DAG submission:** submit a whole workflow (multiple jobs + edges) atomically; visualize it.
- **Logs & artifacts:** capture stdout/stderr per run, store artifacts (object storage), retrievable via API.
- **Notifications:** webhooks / email / Slack on completion or failure.
- **Modern Web UI** (replacing the read-only Streamlit page): live queue, run timelines, DAG graph, SLA/missed-deadline analytics, AI-vs-baseline comparison, and operator controls (kill switch, scale, pause).
- **CLI + SDK:** `orchestrator submit job.yaml`, `orchestrator status <id>`, `orchestrator logs <id> -f`.

### 3.3 User-facing SLAs / expectations
- API responds to submission < 200 ms p95 (NFR-03 carried forward).
- Job picked up within scheduler tick (target < 1 s under normal load).
- No silent data loss: a submitted job is durably persisted before `201` is returned.
- Failures are visible, explained, and retriable.

---

## 4. Software Engineer view — phased roadmap

Each phase is independently shippable and leaves the system in a working state. Estimates assume 1–2 engineers; adjust to your team.

### Phase 0 — Stabilize & de-risk (1–2 weeks) 🔴 do first
**Fix correctness/security blockers and clean the repo so everything else stands on solid ground.**

- [ ] **B1** Fix `shell.py` duplicate `timeout=` kwarg; add output truncation + size limits.
- [ ] **B2** Rewrite `worker.py` so the executor result is the single source of truth (no double-complete, no overwrite of `FAILED`). Remove the redundant `time.sleep(duration)`.
- [ ] **B3** Gate dangerous executors: disable `shell`/`python` by default; put them behind config + allowlist; plan sandboxed execution (Phase 3).
- [ ] **B4/B5** In serving, load the model in **eval mode**, set `epsilon≈0`, and **stop training in the scheduler loop**. Add a deterministic heuristic fallback (EDF / weighted priority) and a feature flag `SCHEDULER_MODE=ai|heuristic`.
- [ ] **B9** Unify the reward definition in one place; make README match code.
- [ ] **B10** Delete dead/empty files (`executor.py`, `dag.py`, `networks.py`, `reward.py`, `schemas.py`, empty `test_scheduler.py`) and the duplicate `src/core/orchestrator.py`; keep one orchestration path.
- [ ] Add `.env.example`, pin dependency versions, pin base image, remove `apt-get` `gcc` if not needed (use wheels), stop bind-mounting source in the "prod" compose profile.
- [ ] Establish **structured logging** (replace `print`) with a `logging` config + request IDs.

**Exit criteria:** all modules import, `pytest` green, shell/python executors safe-by-default, scheduler is deterministic in `heuristic` mode.

### Phase 1 — Durable core & correct execution semantics (2–4 weeks)
- [ ] Introduce **PostgreSQL** as source of truth: `tenants`, `jobs`, `runs` (attempts), `dependencies`, `schedules`, `audit_log`. Add SQLAlchemy + **Alembic** migrations.
- [ ] Keep Redis for cache + leases; move the queue to **Redis Streams (consumer groups)** with explicit `XACK`.
- [ ] Implement **leases + heartbeats + visibility timeout**; replace the wall-clock zombie killer.
- [ ] Implement **retries with backoff** and a **dead-letter queue**; wire `RETRYING` status that already exists in the model.
- [ ] Add **idempotency keys** for run execution.
- [ ] Persist **stdout/stderr per run**; cap sizes; stream large output to object storage.
- [ ] Expand API: `cancel`, `retry`, `list with filters/pagination`, `get runs/logs`, submit-DAG endpoint.

**Exit criteria:** crash/restart of any component loses no jobs; failed jobs retry then DLQ; a job is durable before the API returns `201`.

### Phase 2 — Security, multi-tenancy, and the platform API (2–3 weeks)
- [ ] **AuthN** (API keys + OAuth2/JWT) and **AuthZ** (roles: operator/producer/viewer).
- [ ] **Multi-tenancy**: tenant scoping on every query, per-tenant quotas and rate limits.
- [ ] Input hardening, request size limits, and an **executor allowlist policy** per tenant.
- [ ] Secrets management (env/Vault), no secrets in images or compose.
- [ ] Audit logging of all state-changing operations.

**Exit criteria:** no unauthenticated mutation; tenants cannot see each other's jobs; secrets are externalized.

### Phase 3 — Isolated, scalable execution plane (3–4 weeks)
- [ ] Replace in-process execution with **isolated runners**: subprocess+resource limits for dev; **Docker / Kubernetes Jobs** for prod.
- [ ] Per-job **resource requests/limits** (CPU/mem/timeout) carried in the job spec and enforced.
- [ ] **Worker autoscaling** based on queue depth (KEDA on K8s, or a controller that scales worker deployments) — realizes the README's "dynamic scaling" goal.
- [ ] Add CPU/mem/IO requirements to the **AI state vector** (README future-improvement #2) so scheduling becomes resource-aware.

**Exit criteria:** a malicious/heavy job cannot take down the orchestrator; workers scale up/down with load.

### Phase 4 — Observability & SLOs (1–2 weeks, can parallelize)
- [ ] **Prometheus metrics**: queue depth, scheduling latency, run duration, success/fail rates, missed-deadline counter, AI vs. fallback decision counts.
- [ ] **Distributed tracing** (OpenTelemetry) across API → scheduler → broker → worker.
- [ ] **Grafana dashboards** + **alerting** (paging on SLA breach, DLQ growth, worker starvation).
- [ ] Health/readiness endpoints for all services.

**Exit criteria:** an operator can answer "why is this slow / failing?" from dashboards alone, and gets paged before users complain.

### Phase 5 — Productionize the AI (RL) lifecycle (3–4 weeks)
- [ ] Refactor RL into a proper **offline training pipeline**: experience replay buffer, **target network**, gradient clipping, seeded reproducibility, logged metrics.
- [ ] Build a **simulation environment** (Gym-style) that matches the production state/feature encoding (fix train/serve skew, **B8**) including resource features.
- [ ] **Model registry + versioning**; an **offline eval gate** (must beat FIFO/EDF/priority baselines on held-out scenarios before promotion).
- [ ] **Safe rollout**: shadow mode (AI suggests, heuristic decides, log divergence) → canary (% of decisions) → full, with one-click rollback and a global **kill switch** to fall back to heuristic.
- [ ] Periodic offline retraining on real production traces; never train in the serving loop.

**Exit criteria:** model changes are versioned, gated by eval, rolled out safely, and instantly reversible.

### Phase 6 — Delivery: CI/CD, IaC, and the Web UI (2–4 weeks, parallelizable)
- [ ] **CI**: lint (ruff), type-check (mypy), unit + integration tests, container build/scan on every PR.
- [ ] **CD**: build immutable images, push to registry, deploy via **Helm** to staging→prod.
- [ ] **IaC** for infra (Terraform) + **Kubernetes** manifests/Helm chart; **HA Redis** (Sentinel/Cluster) and managed Postgres with backups.
- [ ] **Modern Web UI** (React/Next.js) replacing read-only Streamlit: live queue, DAG graph, run timelines, analytics, operator controls.
- [ ] **CLI + SDK** packages.
- [ ] **Load & chaos testing** (Locust/k6 + fault injection) to validate NFRs.

**Exit criteria:** push-button deploys with rollback; UI/CLI/SDK cover the full lifecycle; load tests meet SLAs.

---

## 5. Target data model (Postgres)

```text
tenants(id, name, quota_cpu, quota_mem, rate_limit, created_at)
jobs(id, tenant_id, name, description, priority, deadline,
     est_duration, status, schedule_id?, idempotency_key,
     resource_req(cpu,mem,io), created_at, updated_at)
runs(id, job_id, attempt, worker_id, status, started_at, finished_at,
     exit_code, error, log_ref, metrics)          -- one row per execution attempt
dependencies(job_id, depends_on_job_id)            -- DAG edges
schedules(id, tenant_id, cron, next_run_at, enabled)
audit_log(id, tenant_id, actor, action, target, payload, ts)
model_versions(id, version, metrics, status[shadow|canary|active|retired], created_at)
```

Redis keeps only ephemeral/hot data: stream queues, worker heartbeats/leases, and short-TTL caches.

---

## 6. Technology choices (recommended)

| Layer | Choice | Notes |
|-------|--------|-------|
| API | FastAPI (keep) | Add auth deps, pagination, WebSocket events. |
| Truth store | PostgreSQL + SQLAlchemy + Alembic | Durable, relational, migratable. |
| Broker | Redis Streams (start) → RabbitMQ/Kafka (scale) | Consumer groups, acks, DLQ. |
| Cache/leases | Redis | Heartbeats, distributed locks. |
| Execution | Subprocess (dev) → K8s Jobs (prod) | Isolation + limits. |
| ML | PyTorch (keep) + replay/target net + registry (MLflow) | Offline training, eval gate. |
| Observability | OpenTelemetry + Prometheus + Grafana + Loki | Logs/metrics/traces/alerts. |
| Deploy | Docker + Helm + Kubernetes + Terraform | HA, autoscale, rollback. |
| UI | React/Next.js | Operator + producer experience. |
| CI/CD | GitHub Actions (or GitLab CI) | Lint, type, test, scan, deploy. |

---

## 7. Risks & mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| AI makes bad/random scheduling decisions in prod (B4) | Missed SLAs | Eval-mode policy, heuristic fallback, kill switch, eval gate before promotion. |
| Arbitrary code execution via executors (B3) | Full compromise | Disable by default, allowlist, sandboxed/isolated runners, per-tenant policy. |
| Data loss on Redis-only storage (B6) | Lost jobs/history | Postgres source of truth; Redis only ephemeral. |
| Duplicate/zombie execution (B7) | Wasted compute, wrong results | Leases + heartbeats + idempotency + at-least-once + DLQ. |
| Train/serve skew (B8) | AI underperforms baselines | Single shared feature-encoding module used by both trainer and scheduler. |
| Scope creep on UI/ML | Slipping timelines | Phases are independently shippable; keep heuristic scheduler as the always-working default. |

---

## 8. Definition of "real-world ready" (acceptance checklist)

- [ ] No unauthenticated mutation; multi-tenant isolation enforced.
- [ ] Submitted jobs are durably persisted before acknowledgment; survive component crashes.
- [ ] At-least-once execution with retries, backoff, idempotency, and DLQ.
- [ ] Jobs run in isolated runners with enforced resource limits; executors safe-by-default.
- [ ] Full lifecycle (submit/cancel/retry/schedule/DAG/logs) via API + CLI + UI.
- [ ] Metrics, traces, logs, dashboards, and alerts cover the system; SLOs defined.
- [ ] AI policy is versioned, eval-gated, rolled out safely, with a kill switch + heuristic fallback.
- [ ] CI/CD with tests + scans; Helm/K8s deploy with rollback; HA datastores with backups.
- [ ] Load and chaos tests pass against documented NFRs.

---

## 9. Suggested first sprint (concrete, ~1 week)

1. Fix **B1, B2** (executor + worker correctness) and add a regression test.
2. Flip scheduler to **heuristic-by-default** with AI behind a flag (**B4/B5**); load model in eval mode.
3. Delete dead files and the duplicate orchestrator (**B10**); make `pytest` green in CI.
4. Add structured logging + `.env.example` + pinned dependencies.
5. Write the Postgres schema + first Alembic migration (no behavior change yet — lay the foundation for Phase 1).

This delivers an immediately *safer and correct* system while setting up the durable foundation everything else builds on.
