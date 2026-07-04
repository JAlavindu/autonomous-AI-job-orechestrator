import threading
import time

from src.core.config import settings
from src.core.logging_config import get_logger, setup_logging
from src.db.lease_store import lease_store
from src.db.stream_queue import StreamMessage, job_stream
from src.models.job import JobStatus
from src.orchestrator.executors.registry import execute_job
from src.orchestrator.job_manager import job_manager

setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


def _start_heartbeat(job_id: str, worker_id: str) -> threading.Event:
    stop_event = threading.Event()

    def _loop() -> None:
        while not stop_event.wait(settings.LEASE_HEARTBEAT_SECONDS):
            if not lease_store.renew(job_id, worker_id):
                logger.warning(
                    "[%s] Lost lease for job %s during heartbeat",
                    worker_id,
                    job_id,
                )
                break

    thread = threading.Thread(target=_loop, daemon=True, name=f"heartbeat-{job_id[:8]}")
    thread.start()
    return stop_event


def _process_message(message: StreamMessage, worker_id: str, reclaimed: bool = False) -> None:
    job_id = message.job_id
    job = job_manager.get_job(job_id)

    if not job:
        logger.warning("[%s] Invalid job ID %s; acking stream message", worker_id, job_id)
        job_stream.ack(message.message_id)
        return

    if job.status == JobStatus.CANCELLED:
        logger.info("[%s] Job %s cancelled; acking message", worker_id, job.name)
        job_stream.ack(message.message_id)
        return

    if reclaimed and job.status == JobStatus.RUNNING:
        logger.warning(
            "[%s] Reclaimed stale RUNNING job %s; treating prior attempt as lost",
            worker_id,
            job.name,
        )

    if not lease_store.acquire(job_id, worker_id):
        holder = lease_store.get_holder(job_id)
        logger.info(
            "[%s] Lease busy for job %s (holder=%s); leaving message pending",
            worker_id,
            job_id,
            holder,
        )
        return

    stop_heartbeat = _start_heartbeat(job_id, worker_id)
    try:
        logger.info("[%s] Processing job: %s", worker_id, job.name)
        job_manager.update_job_status(job_id, JobStatus.RUNNING, worker_id=worker_id)
        run = job_manager.start_run(job_id, worker_id)
        if not run:
            logger.error("[%s] Could not start run for job %s", worker_id, job_id)
            job_stream.ack(message.message_id)
            return

        result = execute_job(job)

        if result.success:
            job_manager.finish_run(run.id, JobStatus.COMPLETED, result)
            job_manager.update_job_status(job_id, JobStatus.COMPLETED)
            logger.info(
                "[%s] Finished job %s (%.2fs)",
                worker_id,
                job.name,
                result.duration_seconds,
            )
            if result.stdout:
                logger.debug("[%s] stdout: %s", worker_id, result.stdout[:500])
            job_stream.ack(message.message_id)
            return

        action, delay = job_manager.handle_execution_failure(
            job_id,
            run.id,
            result,
            source_message_id=message.message_id,
        )
        if action == "retry":
            job_stream.ack(message.message_id)
            logger.info("[%s] Retrying job %s after %.1fs backoff", worker_id, job.name, delay)
            if delay > 0:
                time.sleep(delay)
            job_manager.enqueue_job(job_id)
        else:
            job_stream.ack(message.message_id)
            logger.warning(
                "[%s] Failed job %s (%.2fs) action=%s",
                worker_id,
                job.name,
                result.duration_seconds,
                action,
            )
            if result.error_message:
                logger.warning("[%s] error: %s", worker_id, result.error_message)
            if result.stderr:
                logger.debug("[%s] stderr: %s", worker_id, result.stderr[:500])

    finally:
        stop_heartbeat.set()
        lease_store.release(job_id, worker_id)


def run_worker(worker_id: str):
    job_stream.ensure_group()
    logger.info("Worker %s started; consuming stream %s", worker_id, settings.JOB_STREAM_KEY)

    loop_count = 0
    while True:
        loop_count += 1
        try:
            if loop_count % settings.RECLAIM_EVERY_N_LOOPS == 0:
                for reclaimed in job_stream.claim_stale_messages(worker_id):
                    _process_message(reclaimed, worker_id, reclaimed=True)

            message = job_stream.read(worker_id)
            if not message:
                continue

            _process_message(message, worker_id, reclaimed=False)

        except Exception as e:
            logger.exception("Worker error: %s", e)
            time.sleep(2)


if __name__ == "__main__":
    import sys

    w_id = sys.argv[1] if len(sys.argv) > 1 else "worker-1"
    run_worker(w_id)