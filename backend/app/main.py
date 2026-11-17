import asyncio
import time
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import (
    HealthStatus,
    DeviceDetail,
    DeviceMetricsHistory,
    ActivityUpdateReq,
    ModeSwitchReq,
    IntervalDecisionOut,
    ComparisonMetrics,
    SimulatorStatus
)
from app.snmp_simulator import SNMPSimulatorCluster
from app.snmp_poller import SNMPPoller
from app.adaptive_engine import AdaptiveScheduler

cluster = SNMPSimulatorCluster()
poller = SNMPPoller()
scheduler = AdaptiveScheduler()
bg_task: Optional[asyncio.Task] = None

async def adaptive_polling_loop():
    """
    Intelligent dispatch loop:
    Evaluates devices due for polling according to their dynamic intervals,
    priority levels, and starvation prevention limits.
    """
    while True:
        try:
            due_device_ids = scheduler.get_devices_due_for_poll()
            for dev_id in due_device_ids:
                dev = cluster.get_device(dev_id)
                if not dev:
                    continue

                prev_snapshot = poller.get_latest_snapshot(dev_id)
                prev_in_rate = prev_snapshot.in_rate_bps if prev_snapshot else 0.0
                prev_oper = prev_snapshot.if_oper_status if prev_snapshot else "UP"

                # Execute genuine UDP SNMP Poll
                snap = await poller.poll_device(
                    ip=dev.ip,
                    port=dev.port,
                    community=dev.community,
                    device_id=dev.device_id
                )

                curr_in_rate = snap.in_rate_bps if snap else 0.0
                curr_oper = snap.if_oper_status if snap else "UP"

                # Evaluate adaptive intelligence & update interval
                scheduler.evaluate_device(
                    device_id=dev.device_id,
                    current_rate_bps=curr_in_rate,
                    previous_rate_bps=prev_in_rate,
                    link_speed_mbps=dev.if_speed_mbps,
                    oper_status=curr_oper,
                    prev_oper_status=prev_oper
                )
                scheduler.record_poll_executed(dev.device_id)

            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            await asyncio.sleep(1.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bg_task
    # Startup: Start UDP Agents and register devices
    await cluster.start()
    for dev in cluster.list_devices():
        scheduler.register_device(dev.device_id, initial_interval=30.0)
        # 1. Baseline poll to establish initial counter offsets
        await poller.poll_device(dev.ip, dev.port, dev.community, dev.device_id)

    # Brief delay for counter progression to evaluate initial rates
    await asyncio.sleep(0.4)
    for dev in cluster.list_devices():
        snap = await poller.poll_device(dev.ip, dev.port, dev.community, dev.device_id)
        rate = snap.in_rate_bps if snap else 0.0
        oper = snap.if_oper_status if snap else "UP"
        scheduler.evaluate_device(dev.device_id, rate, 0.0, dev.if_speed_mbps, oper, "UP")
        scheduler.record_poll_executed(dev.device_id)

    bg_task = asyncio.create_task(adaptive_polling_loop())
    yield
    # Shutdown
    if bg_task:
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
    await cluster.stop()

app = FastAPI(
    title="Adaptive SNMP Polling API",
    version="1.0.0",
    description="Backend API for Adaptive SNMP Polling Optimization",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _build_device_detail(dev_id: str) -> DeviceDetail:
    dev = cluster.get_device(dev_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")

    snapshot = poller.get_latest_snapshot(dev_id)
    total_polls = poller.get_total_polls(dev_id)
    current_profile = dev.get_current_profile()
    sched_state = scheduler.devices.get(dev_id)

    in_rate = snapshot.in_rate_bps if snapshot else 0.0
    out_rate = snapshot.out_rate_bps if snapshot else 0.0
    oper_status = snapshot.if_oper_status if snapshot else "UP"
    last_polled = snapshot.timestamp if snapshot else None

    current_interval = sched_state.current_interval if sched_state else 30.0
    activity_score = sched_state.activity_score if sched_state else 0.0
    priority_level = sched_state.priority_level if sched_state else 3
    reason = sched_state.last_decision_reason if sched_state else "Steady state"
    hysteresis_count = sched_state.consecutive_stable_count if sched_state else 0

    return DeviceDetail(
        id=dev.device_id,
        name=dev.name,
        ip=dev.ip,
        port=dev.port,
        community=dev.community,
        device_type=dev.device_type,
        activity_profile=current_profile,
        is_active=True,
        current_interval=current_interval,
        last_polled_at=last_polled,
        activity_score=activity_score,
        priority_level=priority_level,
        oper_status=oper_status,
        in_octets_rate=in_rate,
        out_octets_rate=out_rate,
        total_polls_count=total_polls,
        interval_reason=reason,
        consecutive_stable_count=hysteresis_count,
        latest_metrics=snapshot
    )

@app.get("/api/health", response_model=HealthStatus)
def get_health():
    return HealthStatus(
        status="ok",
        version="1.0.0",
        service="Adaptive SNMP Polling Backend",
        timestamp=datetime.now(timezone.utc)
    )

@app.get("/api/devices", response_model=List[DeviceDetail])
def get_devices():
    return [_build_device_detail(dev.device_id) for dev in cluster.list_devices()]

@app.get("/api/devices/{device_id}", response_model=DeviceDetail)
def get_device(device_id: str):
    return _build_device_detail(device_id)

@app.get("/api/devices/{device_id}/metrics", response_model=DeviceMetricsHistory)
def get_device_metrics(device_id: str):
    dev = cluster.get_device(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    history = poller.get_history(device_id)
    return DeviceMetricsHistory(
        device_id=dev.device_id,
        device_name=dev.name,
        snapshots=history
    )

@app.post("/api/devices/{device_id}/activity", response_model=DeviceDetail)
def set_device_activity(device_id: str, req: ActivityUpdateReq):
    dev = cluster.get_device(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    dev.set_activity(req.activity_profile, req.burst_duration_sec)
    
    # Expedite scheduling dispatch so activity surge is evaluated immediately
    if device_id in scheduler.devices:
        scheduler.devices[device_id].next_poll_due_monotonic = time.monotonic()
        
    return _build_device_detail(device_id)

@app.get("/api/adaptive/decisions", response_model=List[IntervalDecisionOut])
def get_adaptive_decisions():
    return [
        IntervalDecisionOut(
            device_id=d.device_id,
            activity_score=d.activity_score,
            previous_interval=d.previous_interval,
            new_interval=d.new_interval,
            priority_level=d.priority_level,
            reason=d.reason,
            hysteresis_count=d.hysteresis_count,
            timestamp=d.timestamp
        )
        for d in reversed(scheduler.decisions_log)
    ]

@app.get("/api/adaptive/comparison", response_model=ComparisonMetrics)
def get_comparison():
    return ComparisonMetrics(**scheduler.get_comparison_metrics())

@app.get("/api/adaptive/comparison-history")
def get_comparison_history():
    return scheduler.comparison_history

@app.post("/api/adaptive/mode")
def set_polling_mode(req: ModeSwitchReq):
    scheduler.set_mode(req.mode)
    return {"status": "mode_updated", "current_mode": scheduler.mode}

@app.post("/api/adaptive/reset")
def reset_comparison():
    scheduler.reset_statistics()
    return {"status": "reset_completed"}

@app.post("/api/simulator/poll-now")
async def poll_now():
    results = {}
    for dev in cluster.list_devices():
        prev_snap = poller.get_latest_snapshot(dev.device_id)
        prev_rate = prev_snap.in_rate_bps if prev_snap else 0.0
        prev_oper = prev_snap.if_oper_status if prev_snap else "UP"

        snap = await poller.poll_device(
            ip=dev.ip,
            port=dev.port,
            community=dev.community,
            device_id=dev.device_id
        )
        if snap:
            scheduler.evaluate_device(
                device_id=dev.device_id,
                current_rate_bps=snap.in_rate_bps,
                previous_rate_bps=prev_rate,
                link_speed_mbps=dev.if_speed_mbps,
                oper_status=snap.if_oper_status,
                prev_oper_status=prev_oper
            )
            scheduler.record_poll_executed(dev.device_id)
            results[dev.device_id] = snap.model_dump()
        else:
            results[dev.device_id] = None
    return {"status": "polled", "results": results}

@app.get("/api/simulator/status", response_model=SimulatorStatus)
def get_simulator_status():
    comp = ComparisonMetrics(**scheduler.get_comparison_metrics())
    return SimulatorStatus(
        is_running=cluster.is_running(),
        polling_mode=scheduler.mode,
        devices_count=len(cluster.devices),
        total_polls_performed=poller.total_requests_sent,
        active_udp_ports=[d.port for d in cluster.list_devices()],
        comparison=comp,
        timestamp=datetime.now(timezone.utc)
    )
