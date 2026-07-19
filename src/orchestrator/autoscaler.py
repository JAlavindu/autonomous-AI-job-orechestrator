"""Worker autoscaler: scales worker containers up/down based on queue backlog.

Runs as its own container (see docker-compose 'autoscaler' service) with the
Docker socket mounted. Every tick it measures waiting work (PENDING jobs in
Postgres + undelivered stream entries in Redis), computes how many workers
that needs, and starts/stops labeled clones of the compose-managed worker
container. The original compose worker is used as a template and is never
stopped by the autoscaler; scale-down only removes clones it created.
"""


from __future__ import annotations

import math
import time
import uuid

import docker
import redis
from sqlalchemy import select, func

from src.core.config import settings
from src.core.logging_config import get_logger
from src.db.models import JobRow
from src.db.session import SessionLocal
from src.db.stream_queue import job_stream


logger = get_logger(__name__)

AUTOSCALED_LABEL = "orchestrator.autoscaled"
COMPOSE_SERVICE_LABEL = "com.docker.compose.service"

def get_backlog() -> int:
    """Waiting work = PENDING jobs in Postgres + enqueued-but-undelivered stream entries."""
    with SessionLocal() as db:
        pending_db = (
            db.scalar(
                select(func.count())
                .select_from(JobRow)
                .where(JobRow.status == "PENDING")
            )
            or 0
        )

    stream_lag = 0
    try:
        for group in job_stream.client.xinfo_groups(settings.JOB_STREAM_KEY):
            if group.get("name") == settings.JOB_STREAM_GROUP:
                stream_lag = group.get("lag") or 0
    except redis.ResponseError:
        pass # stream or group doesn't exist yet, so lag is 0

    return pending_db + stream_lag

def compute_desired_workers(
    backlog: int, min_workers: int, max_workers: int, backlog_per_worker: int) -> int:
    """One worker per `backlog_per_worker` waiting jobs, clamped to [min, max]."""
    if backlog <= 0:
        return min_workers
    desired = math.ceil(backlog / backlog_per_worker)
    return max(min_workers, min(desired, max_workers))

class DockerWorkerScale:
    """Starts/stops worker containers by cloning the compose-managed worker."""

    def __init__(self, client: docker.DockerClient | None = None):
        self.client = client or docker.from_env()
    
    def _template(self):
        containers = self.client.containers.list(
            filters={"label": f"{COMPOSE_SERVICE_LABEL}=worker", "status": "running"}
        )
        return containers[0] if containers else None
    
    def count(self) -> int:
        return(1 if self._template() else 0) + len(self._clones())
    
    def scale_to(self, desired: int) ->None:
        current = self.count()
        if desired > current:
            for _ in range(desired - current):
                self._start_clone()
        elif desired < current:
            # Newest first; never the compose-managed template.
            clones = sorted(self._clones(), key=lambda c: c.attrs["Created"], reverse=True)
            for container in clones[: current - desired]:
                logger.info("Autoscaler stopping worker %s", container.name)
                container.stop(timeout=settings.AUTOSCALE_STOP_TIMEOUT_SECONDS)
                container.remove()

    def _start_clone(self) -> None:
        template = self._template()
        if not template:
            logger.error("No running compose worker found to clone; skipping scale-up")
            return
        attrs = template.attrs
        worker_id = f"worker-auto-{uuid.uuid4().hex[:8]}"
        self.client.containers.run(
            image=attrs["Config"]["Image"],
            command=["python", "src/orchestrator/worker.py", worker_id],
            environment=attrs["Config"]["Env"],
            volumes=attrs["HostConfig"]["Binds"],
            network=list(attrs["NetworkSettings"]["Networks"].keys())[0],
            labels={AUTOSCALED_LABEL: "true"},
            name=worker_id,
            detach=True,
        )
        logger.info("Autoscaler started worker %s", worker_id)


class Autoscaler:
    """Decision loop with scale-down hysteresis (up fast, down slow)."""

    def __init__(self, scaler, backlog_fn=get_backlog, clock=time.monotonic):
        self.scaler = scaler
        self.backlog_fn = backlog_fn
        self.clock = clock
        self._below_since: float | None = None

    def step(self) -> None:
        backlog = self.backlog_fn()
        current = self.scaler.count()
        desired = compute_desired_workers(
            backlog,
            settings.AUTOSCALE_MIN_WORKERS,
            settings.AUTOSCALE_MAX_WORKERS,
            settings.AUTOSCALE_BACKLOG_PER_WORKER,
        )

        if desired > current:
            logger.info("Backlog %d: scaling up %d -> %d workers", backlog, current, desired)
            self.scaler.scale_to(desired)
            self._below_since = None
        elif desired < current:
            now = self.clock()
            if self._below_since is None:
                self._below_since = now
            elif now - self._below_since >= settings.AUTOSCALE_SCALE_DOWN_COOLDOWN_SECONDS:
                logger.info("Backlog %d: scaling down %d -> %d workers", backlog, current, desired)
                self.scaler.scale_to(desired)
                self._below_since = None
        else:
            self._below_since = None


def main() -> None:
    autoscaler = Autoscaler(scaler=DockerWorkerScaler())
    logger.info(
        "Autoscaler started (min=%d max=%d backlog/worker=%d interval=%.0fs)",
        settings.AUTOSCALE_MIN_WORKERS,
        settings.AUTOSCALE_MAX_WORKERS,
        settings.AUTOSCALE_BACKLOG_PER_WORKER,
        settings.AUTOSCALE_INTERVAL_SECONDS,
    )
    while True:
        try:
            autoscaler.step()
        except Exception:
            logger.exception("Autoscaler tick failed; retrying next interval")
        time.sleep(settings.AUTOSCALE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()


