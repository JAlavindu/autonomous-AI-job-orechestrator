import numpy as np
from datetime import datetime
from typing import List
from src.models.job import Job

# Configuration
MAX_JOBS_INPUT = 5  # The AI looks at the top 5 jobs max at a time
FEATURES_PER_JOB = 3 # Priority, Duration, Slack Time
INPUT_DIM = MAX_JOBS_INPUT * FEATURES_PER_JOB

def get_job_features(job: Job) -> List[float]:
    """
    Extracts numerical features from a single job.
    1. Priority (Normalized 1-10)
    2. Estimated Duration (Normalized assumption: max 100s)
    3. Slack Time (Time until deadline in seconds)
    """
    now = datetime.utcnow()
    
    # 1. Priority
    prio = job.priority / 10.0
    
    # 2. Duration
    dur = job.estimated_duration / 100.0 # Normalize assuming max 100s tasks
    
    # 3. Slack Time (Deadline - Now - Duration)
    if job.deadline:
        time_left = (job.deadline - now).total_seconds()
        slack = (time_left - job.estimated_duration) / 3600.0 # In hours
    else:
        slack = 1.0 # High slack if no deadline
        
    return [prio, dur, slack]

def encode_state(pending_jobs: List[Job]) -> np.array:
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
        feature_list.extend(get_job_features(job))
        
    # Pad with zeros if we have fewer than MAX_JOBS_INPUT jobs
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