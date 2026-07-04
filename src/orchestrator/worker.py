import time

from src.core.config import settings
from src.core.logging_config import get_logger, setup_logging
from src.db.stream_queue import job_stream
from src.models.job import JobStatus
from src.orchestrator.executors.registry import execute_job
from src.orchestrator.job_manager import job_manager

setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


def run_worker(worker_id: str):
    job_stream.ensure_group()
    logger.info("Worker %s started; consuming stream %s", worker_id, settings.JOB_STREAM_KEY)

    while True:
        message = None
        try:
            message = job_stream.read(worker_id)
            if not message:
                continue

            job_id = message.job_id
            job = job_manager.get_job(job_id)
            if not job:
                logger.warning("[%s] Invalid job ID %s; acking stream message", worker_id, job_id)
                job_stream.ack(message.message_id)
                continue

            logger.info("[%s] Processing job: %s", worker_id, job.name)
            job_manager.update_job_status(job_id, JobStatus.RUNNING, worker_id=worker_id)
            run = job_manager.start_run(job_id, worker_id)

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
            else:
                job_manager.finish_run(run.id, JobStatus.FAILED, result)
                job_manager.update_job_status(job_id, JobStatus.FAILED)
                logger.warning(
                    "[%s] Failed job %s (%.2fs)",
                    worker_id,
                    job.name,
                    result.duration_seconds,
                )
                if result.error_message:
                    logger.warning("[%s] error: %s", worker_id, result.error_message)
                if result.stderr:
                    logger.debug("[%s] stderr: %s", worker_id, result.stderr[:500])

            # ACK only after terminal state is persisted in Postgres.
            job_stream.ack(message.message_id)

        except Exception as e:
            logger.exception("Worker error: %s", e)
            # Do NOT ack on error — message stays pending for Step 3 reclaim.
            time.sleep(2)


if __name__ == "__main__":
    import sys

    w_id = sys.argv[1] if len(sys.argv) > 1 else "worker-1"
    run_worker(w_id)