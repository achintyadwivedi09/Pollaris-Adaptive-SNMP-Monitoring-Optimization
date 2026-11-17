import asyncio
import time
import math
import random
from typing import Dict, List, Optional, Tuple
from pysnmp.proto import api
from pyasn1.codec.ber import decoder, encoder

# Standard MIB-II & RFC 2863 (IF-MIB) OIDs
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_IF_INDEX = "1.3.6.1.2.1.2.2.1.1.1"
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2.1"
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5.1"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8.1"
OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10.1"
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16.1"
OID_IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6.1"
OID_IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10.1"
OID_IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15.1"

UINT64_MAX = (1 << 64)
UINT32_MAX = (1 << 32)

class SimulatedDevice:
    def __init__(
        self,
        device_id: str,
        name: str,
        port: int,
        device_type: str,
        activity_profile: str,
        community: str = "public",
        if_descr: str = "GigabitEthernet0/1",
        if_speed_mbps: int = 1000
    ):
        self.device_id = device_id
        self.name = name
        self.ip = "127.0.0.1"
        self.port = port
        self.community = community
        self.device_type = device_type
        self.activity_profile = activity_profile
        self.if_descr = if_descr
        self.if_speed_mbps = if_speed_mbps

        self.start_monotonic = time.monotonic()
        self.last_update_monotonic = self.start_monotonic

        # Starting counters
        self.in_octets: int = random.randint(1_000_000, 50_000_000)
        self.out_octets: int = random.randint(1_000_000, 50_000_000)
        self.oper_status: int = 1 # 1 = up, 2 = down

        # Burst override mechanics
        self.burst_until_monotonic: Optional[float] = None
        self.burst_profile: Optional[str] = None

    def set_activity(self, profile: str, burst_duration_sec: Optional[int] = None):
        if burst_duration_sec and burst_duration_sec > 0:
            self.burst_until_monotonic = time.monotonic() + burst_duration_sec
            self.burst_profile = profile
        else:
            self.activity_profile = profile
            self.burst_until_monotonic = None
            self.burst_profile = None

    def get_current_profile(self) -> str:
        if self.burst_until_monotonic is not None:
            if time.monotonic() < self.burst_until_monotonic:
                return self.burst_profile or "high"
            else:
                self.burst_until_monotonic = None
                self.burst_profile = None
        return self.activity_profile

    def get_sys_uptime_ticks(self) -> int:
        # TimeTicks in 1/100 of a second
        elapsed = time.monotonic() - self.start_monotonic
        return int(elapsed * 100) % UINT32_MAX

    def update_counters(self):
        now = time.monotonic()
        dt = now - self.last_update_monotonic
        if dt <= 0:
            return
        self.last_update_monotonic = now

        profile = self.get_current_profile()

        # Target bps for profile:
        # stable: ~20-50 kbps
        # low: ~100-300 kbps
        # medium: ~2-6 Mbps
        # high: ~30-70 Mbps
        # intermittent: alternating 12s idle (~20 kbps) and 12s burst (~45 Mbps)
        base_rate_bps = 25_000.0
        if profile == "stable":
            base_rate_bps = 25_000.0 + random.uniform(-3000, 3000)
        elif profile == "low":
            base_rate_bps = 180_000.0 + 50_000.0 * math.sin(now / 5.0) + random.uniform(-10000, 10000)
        elif profile == "medium":
            base_rate_bps = 3_500_000.0 + 1_200_000.0 * math.sin(now / 4.0) + random.uniform(-100_000, 100_000)
        elif profile == "high":
            base_rate_bps = 52_000_000.0 + 15_000_000.0 * math.sin(now / 3.0) + random.uniform(-2_000_000, 2_000_000)
        elif profile == "intermittent":
            cycle = int(now) % 24
            if cycle < 12:
                # Idle phase
                base_rate_bps = 20_000.0 + random.uniform(-2000, 2000)
            else:
                # Active burst phase
                base_rate_bps = 48_000_000.0 + random.uniform(-4_000_000, 4_000_000)

        # Ensure rate is non-negative
        base_rate_bps = max(5_000.0, base_rate_bps)

        # In bytes per second: rate / 8
        in_bytes_sec = (base_rate_bps / 8.0) * random.uniform(0.9, 1.1)
        out_bytes_sec = (base_rate_bps / 8.0) * random.uniform(0.85, 1.15)

        added_in = int(in_bytes_sec * dt)
        added_out = int(out_bytes_sec * dt)

        self.in_octets = (self.in_octets + added_in) % UINT64_MAX
        self.out_octets = (self.out_octets + added_out) % UINT64_MAX

    def get_oid_value(self, oid_str: str) -> Optional[Tuple[str, any]]:
        self.update_counters()
        uptime_ticks = self.get_sys_uptime_ticks()

        # Mapping OIDs to PySNMP ASN.1 value builders
        if oid_str == OID_SYS_UPTIME:
            return ("TimeTicks", api.v2c.TimeTicks(uptime_ticks))
        elif oid_str == OID_IF_INDEX:
            return ("Integer32", api.v2c.Integer32(1))
        elif oid_str == OID_IF_DESCR:
            return ("OctetString", api.v2c.OctetString(self.if_descr))
        elif oid_str == OID_IF_SPEED:
            return ("Gauge32", api.v2c.Gauge32(min(self.if_speed_mbps * 1_000_000, UINT32_MAX - 1)))
        elif oid_str == OID_IF_OPER_STATUS:
            return ("Integer32", api.v2c.Integer32(self.oper_status))
        elif oid_str == OID_IF_IN_OCTETS:
            return ("Counter32", api.v2c.Counter32(self.in_octets % UINT32_MAX))
        elif oid_str == OID_IF_OUT_OCTETS:
            return ("Counter32", api.v2c.Counter32(self.out_octets % UINT32_MAX))
        elif oid_str == OID_IF_HC_IN_OCTETS:
            return ("Counter64", api.v2c.Counter64(self.in_octets))
        elif oid_str == OID_IF_HC_OUT_OCTETS:
            return ("Counter64", api.v2c.Counter64(self.out_octets))
        elif oid_str == OID_IF_HIGH_SPEED:
            return ("Gauge32", api.v2c.Gauge32(self.if_speed_mbps))
        return None


class SNMPAgentProtocol(asyncio.DatagramProtocol):
    def __init__(self, device: SimulatedDevice):
        self.device = device
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        try:
            req_msg, _ = decoder.decode(data, asn1Spec=api.v2c.Message())
            community = str(api.v2c.apiMessage.get_community(req_msg))
            if community != self.device.community:
                return # unauthorized community string ignored

            req_pdu = api.v2c.apiMessage.get_pdu(req_msg)
            request_id = int(api.v2c.apiPDU.get_request_id(req_pdu))
            varbinds = api.v2c.apiPDU.get_varbinds(req_pdu)

            # Build response PDU
            resp_msg = api.v2c.Message()
            api.v2c.apiMessage.set_version(resp_msg, 1) # SNMP v2c
            api.v2c.apiMessage.set_community(resp_msg, community)

            resp_pdu = api.v2c.GetResponsePDU()
            api.v2c.apiPDU.set_request_id(resp_pdu, request_id)
            api.v2c.apiPDU.set_error_status(resp_pdu, 0)
            api.v2c.apiPDU.set_error_index(resp_pdu, 0)

            resp_varbinds = []
            for oid, _ in varbinds:
                oid_str = str(oid)
                val_tuple = self.device.get_oid_value(oid_str)
                if val_tuple:
                    resp_varbinds.append((oid_str, val_tuple[1]))
                else:
                    # NoSuchObject / NoSuchInstance
                    resp_varbinds.append((oid_str, api.v2c.NoSuchInstance()))

            api.v2c.apiPDU.set_varbinds(resp_pdu, resp_varbinds)
            api.v2c.apiMessage.set_pdu(resp_msg, resp_pdu)

            resp_bytes = encoder.encode(resp_msg)
            self.transport.sendto(resp_bytes, addr)
        except Exception:
            # Drop malformed packets silently
            pass


class SNMPSimulatorCluster:
    def __init__(self):
        self.devices: Dict[str, SimulatedDevice] = {}
        self.transports: List[asyncio.DatagramTransport] = []
        self._is_running = False

        self._init_default_devices()

    def _init_default_devices(self):
        defs = [
            ("dev-01", "Core-Router-Alpha", 10161, "router", "high", "GigabitEthernet0/1", 1000),
            ("dev-02", "Dist-Switch-East", 10162, "switch", "medium", "GigabitEthernet0/24", 1000),
            ("dev-03", "Access-Switch-West", 10163, "switch", "stable", "FastEthernet0/1", 100),
            ("dev-04", "Border-Gateway-01", 10164, "router", "intermittent", "TenGigabitEthernet0/1", 10000),
            ("dev-05", "DC-Mgmt-Switch-01", 10165, "switch", "low", "GigabitEthernet0/48", 1000),
        ]
        for dev_id, name, port, dev_type, profile, if_descr, speed in defs:
            self.devices[dev_id] = SimulatedDevice(
                device_id=dev_id,
                name=name,
                port=port,
                device_type=dev_type,
                activity_profile=profile,
                if_descr=if_descr,
                if_speed_mbps=speed
            )

    async def start(self):
        if self._is_running:
            return
        loop = asyncio.get_running_loop()
        for device in self.devices.values():
            try:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda d=device: SNMPAgentProtocol(d),
                    local_addr=("127.0.0.1", device.port)
                )
                self.transports.append(transport)
            except Exception as e:
                print(f"Error binding SNMP agent for {device.name} on port {device.port}: {e}")
        self._is_running = True

    async def stop(self):
        for transport in self.transports:
            transport.close()
        self.transports.clear()
        self._is_running = False

    def is_running(self) -> bool:
        return self._is_running

    def get_device(self, device_id: str) -> Optional[SimulatedDevice]:
        return self.devices.get(device_id)

    def list_devices(self) -> List[SimulatedDevice]:
        return list(self.devices.values())
