import asyncio
import traceback
from typing import List
from datetime import datetime

from src.core.config import settings
from src.core.logging_config import get_logger, setup_logging
from src.models.job import Job, JobStatus
from src.orchestrator.job_manager import job_manager
from src.rl_engine.agent import RLAgent
from src.rl_engine.environment import encode_state, INPUT_DIM, MAX_JOBS_INPUT

setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


def select_by_edf(runnable_jobs: List[Job]) -> int:
    """Earliest-Deadline-First with priority tie-break. Returns the index to run."""
    def sort_key(i: int):
        job = runnable_jobs[i]
        deadline = job.deadline.timestamp() if job.deadline else float("inf")
        return (deadline, -job.priority)

    return min(range(len(runnable_jobs)), key=sort_key)


class Scheduler:
    def __init__(self, check_interval: float = 2.0):
        self.check_interval = check_interval
        self.is_running = False
        self.mode = settings.SCHEDULER_MODE
        self.agent = RLAgent(state_dim=INPUT_DIM, action_dim=MAX_JOBS_INPUT, epsilon=0.0)
        self.agent.load_model(settings.RL_MODEL_PATH)

        logger.info(
            "AI agent initialized on %s (mode=%s, model=%s)",
            self.agent.device,
            self.mode,
            settings.RL_MODEL_PATH,
        )

    async def run(self):
        """Main loop of the scheduler with heuristic or AI decision making."""
        JOB_TIMEOUT_SECONDS = 30.0
        self.is_running = True
        logger.info("Scheduler started (mode=%s)", self.mode)

        while self.is_running:
            try:
                all_jobs = job_manager.list_jobs()
                pending_jobs = [j for j in all_jobs if j.status == JobStatus.PENDING]
                runnable_jobs = [j for j in pending_jobs if job_manager.are_dependencies_met(j)]

                running_jobs = [j for j in all_jobs if j.status == JobStatus.RUNNING]
                now = datetime.utcnow()

                for job in running_jobs:
                    if job.started_at:
                        runtime = (now - job.started_at).total_seconds()
                        if runtime > JOB_TIMEOUT_SECONDS:
                            logger.warning(
                                "Job %s (%s) timed out after %.2fs; marking FAILED",
                                job.name,
                                job.id,
                                runtime,
                            )
                            job_manager.update_job_status(job.id, JobStatus.FAILED)

                if runnable_jobs:
                    if self.mode == "ai":
                        try:
                            current_state = encode_state(runnable_jobs)
                            valid_count = min(len(runnable_jobs), MAX_JOBS_INPUT)
                            action_index = self.agent.select_action(
                                current_state, valid_actions_count=valid_count
                            )
                            if action_index >= len(runnable_jobs):
                                action_index = select_by_edf(runnable_jobs)
                        except Exception as e:
                            logger.warning("AI decision failed, falling back to heuristic: %s", e)
                            action_index = select_by_edf(runnable_jobs)
                    else:
                        action_index = select_by_edf(runnable_jobs)

                    selected_job = runnable_jobs[action_index]
                    logger.info("Enqueueing job %s (mode=%s)", selected_job.name, self.mode)
                    job_manager.update_job_status(selected_job.id, JobStatus.RUNNING, worker_id="queued")
                    job_manager.enqueue_job(selected_job.id)

                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.exception("Scheduler loop error: %s", e)
                await asyncio.sleep(5)

    def stop(self):
        self.is_running = False
        logger.info("Scheduler stopping")


scheduler = Scheduler()
