import pytest
import asyncio
import time
from app.snmp_simulator import SNMPSimulatorCluster
from app.snmp_poller import SNMPPoller
from app.adaptive_engine import AdaptiveScheduler

def test_scenario_1_stable_network():
    async def _run():
        cluster = SNMPSimulatorCluster()
        poller = SNMPPoller()
        scheduler = AdaptiveScheduler(hysteresis_threshold=2)

        for d in cluster.list_devices():
            d.set_activity("stable")
            scheduler.register_device(d.device_id, initial_interval=30.0)

        for d in cluster.list_devices():
            await poller.poll_device(d.ip, d.port, d.community, d.device_id)

        for _ in range(3):
            await asyncio.sleep(0.1)
            for d in cluster.list_devices():
                snap = await poller.poll_device(d.ip, d.port, d.community, d.device_id)
                rate = snap.in_rate_bps if snap else 20_000.0
                dec = scheduler.evaluate_device(d.device_id, rate, rate, d.if_speed_mbps)
                assert dec.new_interval == 30.0
                scheduler.record_poll_executed(d.device_id)

        for st in scheduler.devices.values():
            assert st.current_interval == 30.0
            assert st.priority_level == 3

    asyncio.run(_run())

def test_scenario_2_sudden_surge():
    async def _run():
        cluster = SNMPSimulatorCluster()
        await cluster.start()
        try:
            poller = SNMPPoller()
            scheduler = AdaptiveScheduler(hysteresis_threshold=3)

            for d in cluster.list_devices():
                scheduler.register_device(d.device_id, initial_interval=30.0)
                await poller.poll_device(d.ip, d.port, d.community, d.device_id)

            dev3 = cluster.get_device("dev-03")
            dev3.set_activity("high", burst_duration_sec=30)

            await asyncio.sleep(0.3)
            snap3 = await poller.poll_device(dev3.ip, dev3.port, dev3.community, dev3.device_id)
            rate3 = snap3.in_rate_bps if snap3 else 55_000_000.0
            dec3 = scheduler.evaluate_device(dev3.device_id, rate3, 25_000.0, dev3.if_speed_mbps)

            assert dec3.new_interval == 5.0
            assert dec3.priority_level == 1
            assert "Activity surge" in dec3.reason

            dev5 = cluster.get_device("dev-05")
            snap5 = await poller.poll_device(dev5.ip, dev5.port, dev5.community, dev5.device_id)
            rate5 = snap5.in_rate_bps if snap5 else 200_000.0
            dec5 = scheduler.evaluate_device(dev5.device_id, rate5, rate5, dev5.if_speed_mbps)
            assert dec5.new_interval >= 15.0
        finally:
            await cluster.stop()

    asyncio.run(_run())

def test_scenario_3_mixed_activity_prioritization():
    async def _run():
        cluster = SNMPSimulatorCluster()
        await cluster.start()
        try:
            poller = SNMPPoller()
            scheduler = AdaptiveScheduler()

            for d in cluster.list_devices():
                scheduler.register_device(d.device_id, initial_interval=30.0)
                await poller.poll_device(d.ip, d.port, d.community, d.device_id)

            await asyncio.sleep(0.4)
            for d in cluster.list_devices():
                snap = await poller.poll_device(d.ip, d.port, d.community, d.device_id)
                rate = snap.in_rate_bps if snap else 0.0
                scheduler.evaluate_device(d.device_id, rate, 0.0, d.if_speed_mbps)
                scheduler.record_poll_executed(d.device_id)

            st_high = scheduler.devices["dev-01"]
            st_stable = scheduler.devices["dev-03"]

            assert st_high.priority_level == 1
            assert st_high.current_interval == 5.0
            assert st_stable.priority_level == 3
            assert st_stable.current_interval == 30.0
        finally:
            await cluster.stop()

    asyncio.run(_run())
