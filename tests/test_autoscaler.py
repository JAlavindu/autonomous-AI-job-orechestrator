import pytest

import src.orchestrator.autoscaler as autoscaler_mod
from src.orchestrator.autoscaler import Autoscaler, compute_desired_workers


def test_no_backlog_means_min_workers():
    assert compute_desired_workers(0, min_workers=1, max_workers=5, backlog_per_worker=5) == 1


def test_backlog_scales_proportionally():
    assert compute_desired_workers(12, 1, 5, 5) == 3  # ceil(12/5)


def test_desired_clamped_to_max():
    assert compute_desired_workers(1000, 1, 5, 5) == 5


def test_desired_never_below_min():
    assert compute_desired_workers(1, 2, 5, 5) == 2


class FakeScaler:
    def __init__(self, current=1):
        self.current = current
        self.calls: list[int] = []

    def count(self):
        return self.current

    def scale_to(self, desired):
        self.calls.append(desired)
        self.current = desired


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def fast_settings(monkeypatch):
    s = autoscaler_mod.settings
    monkeypatch.setattr(s, "AUTOSCALE_MIN_WORKERS", 1)
    monkeypatch.setattr(s, "AUTOSCALE_MAX_WORKERS", 5)
    monkeypatch.setattr(s, "AUTOSCALE_BACKLOG_PER_WORKER", 5)
    monkeypatch.setattr(s, "AUTOSCALE_SCALE_DOWN_COOLDOWN_SECONDS", 60.0)
    return s


def test_scale_up_is_immediate(fast_settings):
    scaler = FakeScaler(current=1)
    a = Autoscaler(scaler=scaler, backlog_fn=lambda: 20, clock=FakeClock())
    a.step()
    assert scaler.calls == [4]  # ceil(20/5)


def test_scale_down_waits_for_cooldown(fast_settings):
    scaler = FakeScaler(current=4)
    clock = FakeClock()
    a = Autoscaler(scaler=scaler, backlog_fn=lambda: 0, clock=clock)

    a.step()            # starts the cooldown timer, no action yet
    assert scaler.calls == []
    clock.now = 30.0
    a.step()            # still inside cooldown
    assert scaler.calls == []
    clock.now = 61.0
    a.step()            # cooldown elapsed -> scale down
    assert scaler.calls == [1]


def test_backlog_spike_resets_cooldown(fast_settings):
    scaler = FakeScaler(current=4)
    clock = FakeClock()
    backlog = {"value": 0}
    a = Autoscaler(scaler=scaler, backlog_fn=lambda: backlog["value"], clock=clock)

    a.step()                      # low backlog: cooldown starts
    clock.now = 30.0
    backlog["value"] = 20         # spike! desired == current == 4
    a.step()                      # timer must reset
    backlog["value"] = 0
    clock.now = 59.0              # 29s since reset -> still waiting
    a.step()
    assert scaler.calls == []
