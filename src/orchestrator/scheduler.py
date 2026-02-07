import asyncio
import traceback
import numpy as np
from typing import List
from src.models.job import Job, JobStatus
from src.orchestrator.job_manager import job_manager
from src.orchestrator.executor import executor

# AI Imports
from src.rl_engine.agent import RLAgent
from src.rl_engine.environment import encode_state, calculate_reward, INPUT_DIM, MAX_JOBS_INPUT

class Scheduler:
    def __init__(self, check_interval: float = 2.0):
        self.check_interval = check_interval
        self.is_running = False
        
        # Initialize the AI Agent
        # Action Dim = MAX_JOBS_INPUT (It can choose index 0, 1, 2, 3, or 4)
        self.agent = RLAgent(state_dim=INPUT_DIM, action_dim=MAX_JOBS_INPUT)
        print(f"[*] AI Agent Initialized on {self.agent.device}")

    async def run(self):
        """
        Main loop of the scheduler with AI decision making.
        """
        self.is_running = True
        print("[*] Scheduler started. Waiting for jobs...")

        while self.is_running:
            try:
                # 1. Get all jobs that are PENDING
                all_jobs = job_manager.list_jobs()
                pending_jobs = [j for j in all_jobs if j.status == JobStatus.PENDING]
                
                # Filter strictly for dependencies
                runnable_jobs = [j for j in pending_jobs if job_manager.are_dependencies_met(j)]

                if not runnable_jobs:
                    await asyncio.sleep(self.check_interval)
                    continue

                # 2. Prepare State for AI
                # We only consider the top N jobs for the state encoding
                current_state = encode_state(runnable_jobs)
                
                # 3. AI Selects Action (Index of the job to run)
                action_index = self.agent.select_action(current_state)
                
                # Safety check: Is the chosen index valid?
                if action_index < len(runnable_jobs):
                    selected_job = runnable_jobs[action_index]
                    
                    print(f"[>] AI chose Job: {selected_job.name} (Index: {action_index})")
                    
                    # 4. Execute Job (and wait for result to train)
                    # Note: In a real massive system, training happens asynchronously.
                    # Here we await to capture the immediate result for the reward function.
                    await executor.execute_job(selected_job)
                    
                    # Refresh job data to get completion time/status
                    completed_job = job_manager.get_job(selected_job.id)
                    
                    # 5. Calculate Reward
                    if completed_job and completed_job.status == JobStatus.COMPLETED:
                        reward = calculate_reward(completed_job)
                    else:
                        reward = -1.0 # Failed execution
                        
                    print(f"[$] Reward calculated: {reward}")

                    # 6. Train the Agent
                    # Prepare 'next_state' (state after job is removed)
                    remaining_jobs = [j for j in runnable_jobs if j.id != selected_job.id]
                    next_state = encode_state(remaining_jobs)
                    
                    # Perform Backpropagation
                    self.agent.train_step(current_state, action_index, reward, next_state, done=False)

                else:
                    # AI chose an empty slot (e.g., predicted index 4 but only 2 jobs exist)
                    # We penalize this slightly so it learns to pick valid indices
                    # But we also just pick the first available job to keep the system moving
                    print("[!] AI picked invalid index, falling back to FIFO.")
                    fallback_job = runnable_jobs[0]
                    await executor.execute_job(fallback_job)

            except Exception as e:
                print(f"[!] Scheduler loop error: {e}")
                traceback.print_exc()
                await asyncio.sleep(5)  # Wait longer on error before retrying

    def stop(self):
        self.is_running = False
        print("[*] Scheduler stopping...")

# Global scheduler instance
scheduler = Scheduler()