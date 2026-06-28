import numpy as np
from typing import List
from datetime import datetime, timezone
from src.models.job import Job, JobStatus

# Configuration
MAX_JOBS_INPUT = 15
FEATURES_PER_JOB = 3
INPUT_DIM = MAX_JOBS_INPUT * FEATURES_PER_JOB
BASE_COMPLETION_REWARD = 1.0
PRIORITY_WEIGHT = 0.5
DEADLINE_BONUS = 10.0
DEADLINE_MISS_PENALTY = 10.0
FAILURE_PENALTY = -10.0 

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

def  encode_state(pending_jobs: List[Job], current_time=None) -> np.array:
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
    if job.status == JobStatus.FAILED:
        return FAILURE_PENALTY
    reward = BASE_COMPLETION_REWARD
    reward += job.priority * PRIORITY_WEIGHT
    if job.deadline and job.completed_at:
        if job.completed_at <= job.deadline:
            reward += DEADLINE_BONUS
        else:
            reward -= DEADLINE_MISS_PENALTY
            
    return reward