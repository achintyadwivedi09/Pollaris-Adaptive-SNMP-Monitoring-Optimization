import pytest
import time
from app.adaptive_engine import (
    ActivityScorer,
    AdaptiveScheduler,
    INTERVAL_HIGH,
    INTERVAL_MEDIUM,
    INTERVAL_STABLE,
    STABILITY_HYSTERESIS_THRESHOLD
)

def test_activity_scoring_logic():
    # 1. Quiescent link (~20 kbps on 1 Gbps link, steady)
    stable_score = ActivityScorer.calculate_score(
        current_rate_bps=20_000.0,
        previous_rate_bps=20_000.0,
        link_speed_mbps=1000
    )
    assert stable_score < 30.0

    # 2. High traffic burst (~60 Mbps on 1 Gbps link)
    burst_score = ActivityScorer.calculate_score(
        current_rate_bps=60_000_000.0,
        previous_rate_bps=5_000_000.0,
        link_speed_mbps=1000
    )
    assert burst_score >= 70.0

    # 3. Interface state transition (link down)
    down_score = ActivityScorer.calculate_score(
        current_rate_bps=0.0,
        previous_rate_bps=10_000_000.0,
        oper_status="DOWN",
        prev_oper_status="UP"
    )
    assert down_score == 100.0

def test_hysteresis_prevention_of_flapping():
    scheduler = AdaptiveScheduler(hysteresis_threshold=3)
    dev_id = "test-hysteresis"
    scheduler.register_device(dev_id, initial_interval=INTERVAL_STABLE)

    # Step 1: Initial stable state -> 30s
    d1 = scheduler.evaluate_device(dev_id, 20_000.0, 20_000.0)
    assert d1.new_interval == INTERVAL_STABLE

    # Step 2: Sudden traffic burst -> Immediate jump to 5s (no delay)
    d2 = scheduler.evaluate_device(dev_id, 65_000_000.0, 20_000.0)
    assert d2.new_interval == INTERVAL_HIGH
    assert d2.hysteresis_count == 0
    assert "Activity surge" in d2.reason

    # Step 3: Traffic drops back to stable (Observation 1)
    # Hysteresis must HOLD at 5s!
    d3 = scheduler.evaluate_device(dev_id, 20_000.0, 20_000.0)
    assert d3.new_interval == INTERVAL_HIGH
    assert d3.hysteresis_count == 1
    assert "Hysteresis hold" in d3.reason

    # Step 4: Observation 2
    d4 = scheduler.evaluate_device(dev_id, 20_000.0, 20_000.0)
    assert d4.new_interval == INTERVAL_HIGH
    assert d4.hysteresis_count == 2
    assert "Hysteresis hold" in d4.reason

    # Step 5: Observation 3 -> Threshold reached, relax back to 30s
    d5 = scheduler.evaluate_device(dev_id, 20_000.0, 20_000.0)
    assert d5.new_interval == INTERVAL_STABLE
    assert "Stability verified" in d5.reason

def test_starvation_prevention():
    scheduler = AdaptiveScheduler()
    dev_id = "starved-dev"
    scheduler.register_device(dev_id, initial_interval=INTERVAL_STABLE)

    # Artificially set last polled time to 35 seconds ago (> 30s limit)
    st = scheduler.devices[dev_id]
    st.last_polled_monotonic = time.monotonic() - 35.0
    st.next_poll_due_monotonic = time.monotonic() + 10.0 # theoretically not due for 10s

    due_devices = scheduler.get_devices_due_for_poll()
    assert dev_id in due_devices # Starvation guard forces polling

def test_comparison_metrics_calculation():
    scheduler = AdaptiveScheduler()
    scheduler.register_device("dev-01", initial_interval=INTERVAL_HIGH)
    scheduler.register_device("dev-02", initial_interval=INTERVAL_STABLE)

    # Set mock start time 50 seconds ago
    scheduler.start_time_monotonic = time.monotonic() - 50.0
    # In 50s with 2 devices:
    # Fixed polling (every 5s) would send: (50 / 5) * 2 = 20 requests
    # Suppose adaptive only sent 8 requests:
    scheduler.total_adaptive_requests = 8

    comp = scheduler.get_comparison_metrics()
    assert comp["total_fixed_requests"] == 20
    assert comp["total_adaptive_requests"] == 8
    assert comp["requests_saved"] == 12
    assert comp["percent_reduction"] == 60.0
