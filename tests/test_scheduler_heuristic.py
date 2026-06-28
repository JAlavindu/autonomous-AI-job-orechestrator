from datetime import datetime, timedelta, timezone
from src.models.job import Job
from src.orchestrator.scheduler import select_by_edf


def _job(name, deadline=None, priority=1):
    return Job(name=name, estimated_duration=1, priority=priority, deadline=deadline)


def test_edf_picks_earliest_deadline():
    now = datetime.now(timezone.utc)
    jobs = [
        _job("late", deadline=now + timedelta(hours=2)),
        _job("soon", deadline=now + timedelta(minutes=5)),
        _job("none", deadline=None),
    ]
    assert select_by_edf(jobs) == 1  # "soon"


def test_edf_is_deterministic():
    now = datetime.now(timezone.utc)
    jobs = [_job("a", now + timedelta(hours=1)), _job("b", now + timedelta(hours=3))]
    assert select_by_edf(jobs) == select_by_edf(jobs) == 0