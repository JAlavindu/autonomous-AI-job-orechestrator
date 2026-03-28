import numpy as np
from typing import List
from src.models.job import Job
from datetime import datetime, timezone

# Configuration
MAX_JOBS_INPUT = 5  # The AI looks at the top 5 jobs max at a time
FEATURES_PER_JOB = 3 # Priority, Duration, Slack Time
INPUT_DIM = MAX_JOBS_INPUT * FEATURES_PER_JOB

def get_job_features(job: Job, current_time=None) -> List[float]:
    """ ... """
    # Use simulated time if provided, else real time
    now = current_time if current_time else datetime.now(timezone.utc)
    
    prio = job.priority / 10.0
    dur = job.estimated_duration / 100.0
    
    if job.deadline:
        time_left = (job.deadline - now).total_seconds()
        slack_seconds = time_left - job.estimated_duration
        slack = slack_seconds / 50.0 
    else:
        slack = 5.0
        
    return [prio, dur, slack]

def encode_state(pending_jobs: List[Job], current_time=None) -> np.array:
    """
    Converts a list of pending Job objects into a flat numpy array
    suitable for the Neural Network.
    Shape: (MAX_JOBS_INPUT * FEATURES_PER_JOB,)
    """
    # Sort roughly by submission or simple priority first to get a candidate list
    # For now, we take the first N jobs available
    candidates = pending_jobs[:MAX_JOBS_INPUT]
    feature_list = []
    
    for job in candidates:
        # Pass current_time down to the feature extractor
        feature_list.extend(get_job_features(job, current_time))
        
    remaining_slots = MAX_JOBS_INPUT - len(candidates)
    if remaining_slots > 0:
        feature_list.extend([0.0] * (remaining_slots * FEATURES_PER_JOB))
        
    return np.array(feature_list, dtype=np.float32)

def calculate_reward(job: Job) -> float:
    """
    Determines the reward after a job finishes.
    """
    # Base reward for finishing
    reward = 1.0
    
    # Bonus for Priority
    reward += job.priority * 0.5
    
    # Check Deadline
    if job.deadline and job.completed_at:
        if job.completed_at <= job.deadline:
            reward += 5.0 # Big bonus for meeting deadline
        else:
            reward -= 5.0 # Penalty for missing it
            
    return reward