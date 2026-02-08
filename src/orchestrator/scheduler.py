import asyncio
import traceback
import numpy as np
from typing import List
from src.models.job import Job, JobStatus
from src.orchestrator.job_manager import job_manager
# from src.orchestrator.executor import executor  <-- REMOVED unused import

# AI Imports
from src.rl_engine.agent import RLAgent
from src.rl_engine.environment import encode_state, calculate_reward, INPUT_DIM, MAX_JOBS_INPUT

class Scheduler:
    def __init__(self, check_interval: float = 2.0):
        self.check_interval = check_interval
        self.is_running = False

        # Initialize the AI Agent
        self.agent = RLAgent(state_dim=INPUT_DIM, action_dim=MAX_JOBS_INPUT)

        # [NEW] Load previous training if available
        self.agent.load_model("ai_brain.pth")

        # [NEW] Buffer to track jobs currently with workers
        # Map: job_id -> (state, action_index)
        self.pending_feedback = {}

        print(f"[*] AI Agent Initialized on {self.agent.device}")

    async def run(self):
        """
        Main loop of the scheduler with AI decision making.
        """
        self.is_running = True
        print("[*] Scheduler started (Distributed Mode). Waiting for jobs...")

        while self.is_running:
            try:
                # 1. Get all jobs that are PENDING
                all_jobs = job_manager.list_jobs()
                pending_jobs = [j for j in all_jobs if j.status == JobStatus.PENDING]
                
                # Filter strictly for dependencies
                runnable_jobs = [j for j in pending_jobs if job_manager.are_dependencies_met(j)]

                if runnable_jobs:
                    # AI Decision
                    current_state = encode_state(runnable_jobs)
                    valid_count = min(len(runnable_jobs), MAX_JOBS_INPUT)
                    
                    action_index = self.agent.select_action(current_state, valid_actions_count=valid_count)

                    if action_index < len(runnable_jobs):
                        selected_job = runnable_jobs[action_index]
                        print(f"[>] Scheduler Enqueueing Job: {selected_job.name}")
                        
                        # 1. Store state for later training
                        self.pending_feedback[selected_job.id] = (current_state, action_index)
                        
                        # 2. Set status to RUNNING immediately so we don't pick it again
                        job_manager.update_job_status(selected_job.id, JobStatus.RUNNING, worker_id="queued")
                        
                        # 3. Push to Redis Queue using job_manager's internal db reference
                        # (job_manager.db is the redis_client instance)
                        job_manager.db.add_to_queue(selected_job.id)
                    else:
                        # Fallback for invalid index
                        job = runnable_jobs[0]
                        job_manager.update_job_status(job.id, JobStatus.RUNNING, worker_id="queued")
                        job_manager.db.add_to_queue(job.id)

                completed_ids = []
                # We need to use list() here because we might delete keys during iteration in some edge cases
                # though strictly safe here since we delete in a separate loop, it's good practice.
                for jid, (state, action) in list(self.pending_feedback.items()):
                    job = job_manager.get_job(jid)
                    
                    # Check if job is finished
                    if job and job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                        if job.status == JobStatus.COMPLETED:
                            reward = calculate_reward(job)
                            print(f"[$] Job Completed: {job.name}. Reward: {reward}")
                        else:
                            reward = -5.0 # Penalty for failure
                            print(f"[!] Job Failed: {job.name}. Penalty: {reward}")

                        # Estimate next state
                        latest_jobs = [j for j in job_manager.list_jobs() if j.status == JobStatus.PENDING]
                        next_state = encode_state(latest_jobs)
                        
                        self.agent.train_step(state, action, reward, next_state, done=False)
                        completed_ids.append(jid)

                # Cleanup buffer
                for jid in completed_ids:
                    del self.pending_feedback[jid]

                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                print(f"[!] Scheduler loop error: {e}")
                traceback.print_exc()
                await asyncio.sleep(5)

    def stop(self):
        self.is_running = False
        print("[*] Scheduler stopping...")
        self.agent.save_model("ai_brain.pth")


scheduler = Scheduler()




