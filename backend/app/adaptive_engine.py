import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models import MetricSnapshot

# Polling Interval Standards for the Prototype
INTERVAL_HIGH = 5.0      # High activity / anomaly
INTERVAL_MEDIUM = 15.0   # Moderate traffic activity
INTERVAL_STABLE = 30.0   # Stable / quiescent network
INTERVAL_MIN = 5.0
INTERVAL_MAX = 30.0

# Hysteresis Configuration
STABILITY_HYSTERESIS_THRESHOLD = 3  # consecutive stable cycles required to relax interval

# Starvation Prevention
MAX_STARVATION_DELAY = 30.0  # seconds

@dataclass
class IntervalDecision:
    device_id: str
    activity_score: float
    previous_interval: float
    new_interval: float
    priority_level: int       # 1 = Urgent/High, 2 = Medium, 3 = Low
    reason: str
    hysteresis_count: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class ActivityScorer:
    """
    Computes explainable activity score [0.0 - 100.0] derived from:
    1. Traffic throughput relative to link capacity
    2. Rate of change (delta between consecutive polls)
    3. Interface operational state changes
    """
    @staticmethod
    def calculate_score(
        current_rate_bps: float,
        previous_rate_bps: float,
        link_speed_mbps: int = 1000,
        oper_status: str = "UP",
        prev_oper_status: str = "UP"
    ) -> float:
        # Component 1: Operational Status Transition
        if oper_status != prev_oper_status or oper_status == "DOWN":
            return 100.0  # Highest urgency on link failure or state change

        # Component 2: Bandwidth Activity (up to 50 points)
        # Rates: > 25 Mbps -> 40-50 pts; 1-25 Mbps -> 15-40 pts; < 1 Mbps -> 0-15 pts
        if current_rate_bps >= 25_000_000.0:
            bw_score = 40.0 + min(10.0, (current_rate_bps - 25_000_000.0) / 25_000_000.0 * 10.0)
        elif current_rate_bps >= 1_000_000.0:
            bw_score = 20.0 + ((current_rate_bps - 1_000_000.0) / 24_000_000.0) * 20.0
        elif current_rate_bps >= 100_000.0:
            bw_score = 8.0 + ((current_rate_bps - 100_000.0) / 900_000.0) * 12.0
        else:
            bw_score = (current_rate_bps / 100_000.0) * 8.0

        # Component 3: Traffic Delta / Volatility (up to 50 points)
        baseline = max(previous_rate_bps, 50_000.0)
        rate_diff = abs(current_rate_bps - previous_rate_bps)
        ratio = rate_diff / baseline
        # Large jump (e.g. 5x or more) gets 45-50 points
        if ratio >= 5.0:
            delta_score = 50.0
        elif ratio >= 1.0:
            delta_score = 25.0 + (ratio - 1.0) / 4.0 * 25.0
        else:
            delta_score = ratio * 25.0

        total_score = bw_score + delta_score
        return round(max(0.0, min(100.0, total_score)), 1)


@dataclass
class DeviceScheduleState:
    device_id: str
    current_interval: float = INTERVAL_STABLE
    activity_score: float = 0.0
    priority_level: int = 3
    last_polled_monotonic: float = 0.0
    last_polled_at: Optional[datetime] = None
    next_poll_due_monotonic: float = 0.0
    consecutive_stable_count: int = 0
    last_decision_reason: str = "Initial baseline interval"
    total_polls: int = 0


class AdaptiveScheduler:
    def __init__(self, hysteresis_threshold: int = STABILITY_HYSTERESIS_THRESHOLD):
        self.hysteresis_threshold = hysteresis_threshold
        self.devices: Dict[str, DeviceScheduleState] = {}
        self.decisions_log: List[IntervalDecision] = []
        self.mode: str = "adaptive"  # "adaptive" or "fixed"
        self.fixed_interval: float = INTERVAL_HIGH

        # Global Request Statistics for fair comparison
        self.total_adaptive_requests: int = 0
        self.total_fixed_requests: int = 0
        self.start_time_monotonic = time.monotonic()
        self.comparison_history: List[dict] = []
        self._last_history_sample_time: float = 0.0

    def set_mode(self, mode: str):
        if mode in ("adaptive", "fixed"):
            self.mode = mode

    def reset_statistics(self):
        self.total_adaptive_requests = 0
        self.total_fixed_requests = 0
        self.start_time_monotonic = time.monotonic()
        self.comparison_history.clear()
        self._last_history_sample_time = 0.0

    def register_device(self, device_id: str, initial_interval: float = INTERVAL_STABLE):
        if device_id not in self.devices:
            now_m = time.monotonic()
            self.devices[device_id] = DeviceScheduleState(
                device_id=device_id,
                current_interval=initial_interval,
                next_poll_due_monotonic=now_m
            )

    def evaluate_device(
        self,
        device_id: str,
        current_rate_bps: float,
        previous_rate_bps: float,
        link_speed_mbps: int = 1000,
        oper_status: str = "UP",
        prev_oper_status: str = "UP"
    ) -> IntervalDecision:
        if device_id not in self.devices:
            self.register_device(device_id)
        
        dev_state = self.devices[device_id]
        score = ActivityScorer.calculate_score(
            current_rate_bps=current_rate_bps,
            previous_rate_bps=previous_rate_bps,
            link_speed_mbps=link_speed_mbps,
            oper_status=oper_status,
            prev_oper_status=prev_oper_status
        )
        dev_state.activity_score = score

        # Target interval based on score
        if score >= 70.0:
            target_interval = INTERVAL_HIGH
            priority = 1
        elif score >= 30.0:
            target_interval = INTERVAL_MEDIUM
            priority = 2
        else:
            target_interval = INTERVAL_STABLE
            priority = 3

        prev_interval = dev_state.current_interval
        new_interval = prev_interval
        reason = ""

        if self.mode == "fixed":
            new_interval = self.fixed_interval
            priority = 1
            reason = f"Fixed Polling Mode ({self.fixed_interval}s interval)"
            dev_state.consecutive_stable_count = 0
        else:
            # ADAPTIVE LOGIC WITH HYSTERESIS & PRIORITY
            if target_interval < prev_interval:
                # Fast Escalation: Anomaly/burst detected -> immediately increase polling frequency
                new_interval = target_interval
                dev_state.consecutive_stable_count = 0
                reason = f"Activity surge (score {score}); expedited polling to {target_interval}s"
            elif target_interval > prev_interval:
                # Relaxation with Hysteresis: Require consecutive stable cycles before slowing down
                dev_state.consecutive_stable_count += 1
                if dev_state.consecutive_stable_count >= self.hysteresis_threshold:
                    new_interval = target_interval
                    reason = f"Stability verified ({dev_state.consecutive_stable_count}/{self.hysteresis_threshold} cycles); relaxed to {target_interval}s"
                    dev_state.consecutive_stable_count = 0
                else:
                    new_interval = prev_interval
                    reason = f"Hysteresis hold ({dev_state.consecutive_stable_count}/{self.hysteresis_threshold} stable cycles); maintaining {prev_interval}s"
            else:
                # Steady state
                new_interval = prev_interval
                reason = f"Steady activity (score {score}); maintained {prev_interval}s"

        # Apply bounds
        new_interval = max(INTERVAL_MIN, min(INTERVAL_MAX, new_interval))

        dev_state.current_interval = new_interval
        dev_state.priority_level = priority
        dev_state.last_decision_reason = reason

        decision = IntervalDecision(
            device_id=device_id,
            activity_score=score,
            previous_interval=prev_interval,
            new_interval=new_interval,
            priority_level=priority,
            reason=reason,
            hysteresis_count=dev_state.consecutive_stable_count
        )

        self.decisions_log.append(decision)
        if len(self.decisions_log) > 100:
            self.decisions_log.pop(0)

        return decision

    def record_poll_executed(self, device_id: str):
        now_m = time.monotonic()
        now_utc = datetime.now(timezone.utc)
        if device_id in self.devices:
            st = self.devices[device_id]
            st.last_polled_monotonic = now_m
            st.last_polled_at = now_utc
            st.next_poll_due_monotonic = now_m + st.current_interval
            st.total_polls += 1

        self.total_adaptive_requests += 1

        # Sample comparison metrics for charts at most once per 2 seconds
        now_m = time.monotonic()
        if now_m - self._last_history_sample_time >= 2.0:
            self._last_history_sample_time = now_m
            metrics = self.get_comparison_metrics()
            self.comparison_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "time_str": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "elapsed_seconds": metrics["elapsed_seconds"],
                "fixed_requests": metrics["total_fixed_requests"],
                "adaptive_requests": metrics["total_adaptive_requests"],
                "requests_saved": metrics["requests_saved"],
                "percent_reduction": metrics["percent_reduction"]
            })
            if len(self.comparison_history) > 60:
                self.comparison_history.pop(0)

    def get_devices_due_for_poll(self) -> List[str]:
        """
        Returns device IDs due for polling, sorted by priority and urgency.
        Includes Starvation Prevention: devices exceeding MAX_STARVATION_DELAY are forced first.
        """
        now_m = time.monotonic()
        candidates: List[Tuple[float, int, str]] = []

        for dev_id, st in self.devices.items():
            time_since_last = now_m - st.last_polled_monotonic if st.last_polled_monotonic > 0 else 9999.0
            
            # Check if due or starved
            is_due = now_m >= st.next_poll_due_monotonic
            is_starved = time_since_last >= MAX_STARVATION_DELAY

            if is_due or is_starved:
                # Priority ranking tuple: (priority_rank, urgency_rank, device_id)
                # Lower numbers = higher priority in sorting
                # Starved devices get top priority (rank 0)
                prio_rank = 0 if is_starved else st.priority_level
                urgency = -time_since_last # largest elapsed time polled first
                candidates.append((prio_rank, urgency, dev_id))

        # Sort by priority rank then urgency
        candidates.sort(key=lambda x: (x[0], x[1]))
        return [c[2] for c in candidates]

    def get_comparison_metrics(self) -> dict:
        """
        Calculates mathematical comparison between Fixed and Adaptive modes.
        Fixed Baseline: 5-second polling for every device over the same elapsed duration.
        """
        now_m = time.monotonic()
        elapsed_sec = max(1.0, now_m - self.start_time_monotonic)
        num_devices = len(self.devices) or 5

        # Equivalent requests in Fixed mode (every 5 seconds)
        expected_fixed_per_dev = elapsed_sec / self.fixed_interval
        total_fixed_calculated = int(expected_fixed_per_dev * num_devices)

        # Actual adaptive requests sent
        actual_adaptive = self.total_adaptive_requests

        # Requests saved
        requests_saved = max(0, total_fixed_calculated - actual_adaptive)
        percent_reduction = (requests_saved / total_fixed_calculated * 100.0) if total_fixed_calculated > 0 else 0.0

        # Average polling interval across active devices
        intervals = [st.current_interval for st in self.devices.values()]
        avg_interval = sum(intervals) / len(intervals) if intervals else INTERVAL_STABLE

        return {
            "mode": self.mode,
            "elapsed_seconds": round(elapsed_sec, 1),
            "total_fixed_requests": total_fixed_calculated,
            "total_adaptive_requests": actual_adaptive,
            "requests_saved": requests_saved,
            "percent_reduction": round(percent_reduction, 1),
            "average_interval_seconds": round(avg_interval, 1),
            "fixed_interval_seconds": self.fixed_interval,
            "device_count": num_devices
        }
