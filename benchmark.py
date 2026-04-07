import time
import uuid
import random
from datetime import datetime, timedelta, timezone
import copy
import json

# Adjust imports based on your actual class names
from src.models.job import Job
from src.rl_engine.agent import RLAgent
from src.rl_engine.environment import encode_state
import torch

NUM_JOBS = 100

def generate_test_jobs():
    """Generates a consistent batch of jobs to test across all schedulers."""
    
    # LOCK REPRODUCIBILITY FOR PRESENTATION 
    random.seed(42)  
    import torch
    import numpy as np
    np.random.seed(42)
    torch.manual_seed(42)
    # -----------------------------------
    
    jobs = []
    now = datetime.now(timezone.utc)
    for _ in range(NUM_JOBS):
        job = Job(
            id=str(uuid.uuid4()),
            name=f"BenchJob-{random.randint(1000, 9999)}",
            priority=random.randint(1, 10),
            estimated_duration=random.uniform(0.5, 3.0),
            deadline=now + timedelta(seconds=random.uniform(10.0, 175.0)),
            status="PENDING",
            created_at=now
        )
        jobs.append(job)
    return jobs

def evaluate_metrics(completed_jobs):
    """Calculates evaluation metrics for a specific run."""
    missed_deadlines = 0
    total_latency = 0
    high_priority_misses = 0

    for job in completed_jobs:
        if job.completed_at > job.deadline:
            missed_deadlines += 1
            if job.priority >= 8:
                high_priority_misses += 1
        
        latency = (job.completed_at - job.created_at).total_seconds()
        total_latency += latency

    avg_latency = total_latency / len(completed_jobs) if completed_jobs else 0
    return {
        "missed_deadlines": missed_deadlines,
        "high_priority_misses": high_priority_misses,
        "avg_latency": avg_latency
    }

def simulate_fifo(jobs):
    """Baseline 1: Processes jobs in the exact order they arrive."""
    print("Running FIFO Benchmark...")
    current_time = datetime.now(timezone.utc)
    completed = []
    
    # FIFO preserves the original generation/arrival order
    for job in jobs:
        current_time += timedelta(seconds=job.estimated_duration)
        job.completed_at = current_time
        job.status = "COMPLETED"
        completed.append(job)
        
    return evaluate_metrics(completed)

def simulate_priority(jobs):
    """Baseline 2: Processes jobs sorted by Priority (High to Low), then Deadline."""
    print("Running Priority Benchmark...")
    current_time = datetime.now(timezone.utc)
    completed = []
    
    # Sort by priority (descending), then deadline (ascending)
    sorted_jobs = sorted(jobs, key=lambda j: (-j.priority, j.deadline))
    
    for job in sorted_jobs:
        current_time += timedelta(seconds=job.estimated_duration)
        job.completed_at = current_time
        job.status = "COMPLETED"
        completed.append(job)
        
    return evaluate_metrics(completed)

def simulate_ai(jobs):
    """Baseline 3: Uses the trained DQN Agent to pick the best job index."""
    print("Running AI (DQN) Benchmark...")
    current_time = datetime.now(timezone.utc)
    completed = []
    
    # Setup AI components
    # (Assuming state size=15 and action size=5 based on standard DQN setup)
    state_size = 45  
    action_size = 15  
    agent = RLAgent(state_size, action_size)
    
    # Load pre-trained brain if it exists
    try:
        agent.policy_net.load_state_dict(torch.load("ai_brain.pth"))
        agent.epsilon = 0.0 # Force greedy/exploitation mode for benchmarking
    except Exception as e:
        print("  [Warn] Could not load ai_brain.pth. AI will run untrained.", e)

    pending_jobs = list(jobs)

    while pending_jobs:

        pending_jobs.sort(key=lambda j: j.deadline)
        
        # Take up to top 5 jobs for observation
        window = pending_jobs[:action_size]
        
        # Get AI decision
        state = encode_state(window, current_time)
        valid_count = len(window)
        action_idx = agent.select_action(state, valid_count)
        
        # Sanity check action
        if action_idx >= valid_count:
            action_idx = 0 
            
        selected_job = window[action_idx]
        pending_jobs.remove(selected_job)
        
        # Process job
        current_time += timedelta(seconds=selected_job.estimated_duration)
        selected_job.completed_at = current_time
        selected_job.status = "COMPLETED"
        completed.append(selected_job)

    return evaluate_metrics(completed)

def run_benchmarks():
    base_jobs = generate_test_jobs()
    
    # Deep copy jobs for each strategy so timestamps aren't overwritten
    fifo_jobs = copy.deepcopy(base_jobs)
    priority_jobs = copy.deepcopy(base_jobs)
    ai_jobs = copy.deepcopy(base_jobs)
    
    # Run algorithms
    results_fifo = simulate_fifo(fifo_jobs)
    results_priority = simulate_priority(priority_jobs)
    results_ai = simulate_ai(ai_jobs)
    
    # Print Report
    print("\n" + "="*50)
    print("🚀 BENCHMARK RESULTS")
    print("="*50)
    
    strategies = ["FIFO", "Priority", "AI (DQN)"]
    results = [results_fifo, results_priority, results_ai]
    
    for i, strat in enumerate(strategies):
        r = results[i]
        print(f"\n--- {strat} ---")
        print(f"Missed Deadlines:        {r['missed_deadlines']} / {NUM_JOBS}")
        print(f"High-Priority Misses:    {r['high_priority_misses']}")
        print(f"Avg Latency (Seconds):   {r['avg_latency']:.2f}s")
    
    print("\n" + "="*50)

    output_data = {
        "AI (DQN)": results_ai["missed_deadlines"],
        "FIFO": results_fifo["missed_deadlines"],
        "Strict Priority": results_priority["missed_deadlines"]
    }
    
    with open("benchmark_results.json", "w") as f:
        json.dump(output_data, f)

if __name__ == "__main__":
    run_benchmarks()