from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone

class HealthStatus(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    service: str = "Adaptive SNMP Polling Backend"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class DeviceBase(BaseModel):
    id: str
    name: str
    ip: str = "127.0.0.1"
    port: int
    community: str = "public"
    device_type: str = "router" # router, switch
    activity_profile: str = "stable" # stable, low, medium, high, intermittent
    is_active: bool = True

class MetricSnapshot(BaseModel):
    timestamp: datetime
    sys_uptime_ticks: int
    if_oper_status: str # UP, DOWN
    if_in_octets: int # 64-bit counter
    if_out_octets: int # 64-bit counter
    in_rate_bps: float
    out_rate_bps: float
    poll_latency_ms: float

class DeviceDetail(DeviceBase):
    current_interval: float = 30.0 # seconds
    last_polled_at: Optional[datetime] = None
    activity_score: float = 0.0 # 0.0 to 100.0
    priority_level: int = 3 # 1 = High, 2 = Medium, 3 = Low
    oper_status: str = "UP"
    in_octets_rate: float = 0.0 # bps
    out_octets_rate: float = 0.0 # bps
    total_polls_count: int = 0
    interval_reason: str = "Steady state"
    consecutive_stable_count: int = 0
    latest_metrics: Optional[MetricSnapshot] = None

class DeviceMetricsHistory(BaseModel):
    device_id: str
    device_name: str
    snapshots: List[MetricSnapshot]

class ActivityUpdateReq(BaseModel):
    activity_profile: str # stable, low, medium, high, intermittent
    burst_duration_sec: Optional[int] = None

class ModeSwitchReq(BaseModel):
    mode: str # "adaptive" or "fixed"

class IntervalDecisionOut(BaseModel):
    device_id: str
    activity_score: float
    previous_interval: float
    new_interval: float
    priority_level: int
    reason: str
    hysteresis_count: int
    timestamp: datetime

class ComparisonMetrics(BaseModel):
    mode: str
    elapsed_seconds: float
    total_fixed_requests: int
    total_adaptive_requests: int
    requests_saved: int
    percent_reduction: float
    average_interval_seconds: float
    fixed_interval_seconds: float
    device_count: int

class SimulatorStatus(BaseModel):
    is_running: bool = True
    polling_mode: str = "adaptive"
    devices_count: int
    total_polls_performed: int
    active_udp_ports: List[int]
    comparison: Optional[ComparisonMetrics] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
