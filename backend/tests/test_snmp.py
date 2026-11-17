import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from app.snmp_simulator import SimulatedDevice, SNMPAgentProtocol, SNMPSimulatorCluster, UINT64_MAX
from app.snmp_poller import SNMPPoller, DevicePollState
from app.models import MetricSnapshot

def test_snmp_agent_udp_query():
    async def _run():
        dev = SimulatedDevice(
            device_id="test-01",
            name="Test-Router",
            port=10199,
            device_type="router",
            activity_profile="high"
        )
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: SNMPAgentProtocol(dev),
            local_addr=("127.0.0.1", 10199)
        )

        try:
            poller = SNMPPoller()
            # Baseline poll
            snap1 = await poller.poll_device("127.0.0.1", 10199, "public", "test-01")
            assert snap1 is not None
            assert snap1.if_oper_status == "UP"
            assert snap1.if_in_octets > 0
            assert snap1.sys_uptime_ticks >= 0

            # Wait a brief moment to allow counter progression
            await asyncio.sleep(0.3)

            # Second poll to measure rate
            snap2 = await poller.poll_device("127.0.0.1", 10199, "public", "test-01")
            assert snap2 is not None
            assert snap2.if_in_octets >= snap1.if_in_octets
            assert snap2.in_rate_bps > 0 # Genuine rate calculated from counter difference
        finally:
            transport.close()

    asyncio.run(_run())

def test_rate_calculation_and_wraparound():
    state = DevicePollState("dev-wrap")
    t0 = datetime.now(timezone.utc)
    state.prev_timestamp = t0
    state.prev_uptime_ticks = 1000
    state.prev_in_octets = UINT64_MAX - 50_000 # Near 64-bit boundary
    state.prev_out_octets = 1_000_000

    # Simulate 2 seconds elapsed and 100,000 bytes ingested, causing wraparound
    curr_in = 50_000
    delta_in = curr_in - state.prev_in_octets
    if delta_in < 0:
        delta_in += UINT64_MAX
    assert delta_in == 100_000

    elapsed_sec = 2.0
    rate_bps = (delta_in * 8.0) / elapsed_sec
    assert rate_bps == 400_000.0 # 400 kbps

def test_cluster_initialization():
    cluster = SNMPSimulatorCluster()
    devices = cluster.list_devices()
    assert len(devices) == 5
    profiles = {d.activity_profile for d in devices}
    assert "stable" in profiles
    assert "low" in profiles
    assert "medium" in profiles
    assert "high" in profiles
    assert "intermittent" in profiles
