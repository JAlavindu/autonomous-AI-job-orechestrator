from datetime import datetime, timedelta, timezone
from src.models.job import Job, JobStatus
from src.rl_engine.environment import calculate_reward, DEADLINE_BONUS, FAILURE_PENALTY

def test_reward_on_time():
    now = datetime.now(timezone.utc)
    job = Job(
        name="ok", estimated_duration=1, priority=4,
        deadline=now + timedelta(hours=1),
        status=JobStatus.COMPLETED, completed_at=now,
    )
    # 1.0 + 4*0.5 + 10.0 = 13.0
    assert calculate_reward(job) == 1.0 + 4 * 0.5 + DEADLINE_BONUS

def test_reward_failed():
    job = Job(name="fail", estimated_duration=1, status=JobStatus.FAILED)
    assert calculate_reward(job) == FAILURE_PENALTY