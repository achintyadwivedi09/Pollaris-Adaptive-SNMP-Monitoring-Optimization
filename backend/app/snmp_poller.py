import asyncio
import time
import socket
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pysnmp.proto import api
from pyasn1.codec.ber import decoder, encoder

from app.models import MetricSnapshot, DeviceDetail
from app.snmp_simulator import (
    OID_SYS_UPTIME,
    OID_IF_OPER_STATUS,
    OID_IF_HC_IN_OCTETS,
    OID_IF_HC_OUT_OCTETS,
    OID_IF_HIGH_SPEED,
    UINT64_MAX
)

MAX_HISTORY_POINTS = 60

class DevicePollState:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.prev_timestamp: Optional[datetime] = None
        self.prev_uptime_ticks: Optional[int] = None
        self.prev_in_octets: Optional[int] = None
        self.prev_out_octets: Optional[int] = None

        self.last_snapshot: Optional[MetricSnapshot] = None
        self.history: List[MetricSnapshot] = []
        self.total_polls: int = 0
        self.failed_polls: int = 0

class SNMPPoller:
    def __init__(self):
        self.states: Dict[str, DevicePollState] = {}
        self.total_requests_sent: int = 0
        self._req_id_counter: int = 1000

    def _get_next_req_id(self) -> int:
        self._req_id_counter = (self._req_id_counter + 1) % 2147483647
        return self._req_id_counter

    def get_or_create_state(self, device_id: str) -> DevicePollState:
        if device_id not in self.states:
            self.states[device_id] = DevicePollState(device_id)
        return self.states[device_id]

    async def poll_device(self, ip: str, port: int, community: str, device_id: str, timeout: float = 1.5) -> Optional[MetricSnapshot]:
        req_id = self._get_next_req_id()
        self.total_requests_sent += 1
        state = self.get_or_create_state(device_id)

        # 1. Build SNMP v2c GetRequest PDU
        req_msg = api.v2c.Message()
        api.v2c.apiMessage.set_version(req_msg, 1) # v2c
        api.v2c.apiMessage.set_community(req_msg, community)

        pdu = api.v2c.GetRequestPDU()
        api.v2c.apiPDU.set_request_id(pdu, req_id)
        api.v2c.apiPDU.set_error_status(pdu, 0)
        api.v2c.apiPDU.set_error_index(pdu, 0)

        oids_to_query = [
            OID_SYS_UPTIME,
            OID_IF_OPER_STATUS,
            OID_IF_HC_IN_OCTETS,
            OID_IF_HC_OUT_OCTETS,
            OID_IF_HIGH_SPEED
        ]
        api.v2c.apiPDU.set_varbinds(pdu, [(oid, api.v2c.Null()) for oid in oids_to_query])
        api.v2c.apiMessage.set_pdu(req_msg, pdu)

        req_bytes = encoder.encode(req_msg)

        # 2. Async UDP query
        t0 = time.monotonic()
        loop = asyncio.get_running_loop()

        raw_response = None
        try:
            # Using loop.run_in_executor with UDP socket for robust timeout handling
            def _udp_exchange():
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(timeout)
                try:
                    sock.sendto(req_bytes, (ip, port))
                    resp_data, _ = sock.recvfrom(4096)
                    return resp_data
                finally:
                    sock.close()

            raw_response = await loop.run_in_executor(None, _udp_exchange)
        except Exception:
            state.failed_polls += 1
            return None

        latency_ms = (time.monotonic() - t0) * 1000.0

        # 3. Decode response
        try:
            resp_msg, _ = decoder.decode(raw_response, asn1Spec=api.v2c.Message())
            resp_pdu = api.v2c.apiMessage.get_pdu(resp_msg)
            varbinds = api.v2c.apiPDU.get_varbinds(resp_pdu)
        except Exception:
            state.failed_polls += 1
            return None

        val_dict = {}
        for oid, val in varbinds:
            oid_str = str(oid)
            try:
                # Convert pyasn1 value to int
                val_dict[oid_str] = int(val)
            except Exception:
                val_dict[oid_str] = str(val)

        sys_uptime = int(val_dict.get(OID_SYS_UPTIME, 0))
        oper_status_val = int(val_dict.get(OID_IF_OPER_STATUS, 1))
        oper_status_str = "UP" if oper_status_val == 1 else "DOWN"
        curr_in = int(val_dict.get(OID_IF_HC_IN_OCTETS, 0))
        curr_out = int(val_dict.get(OID_IF_HC_OUT_OCTETS, 0))

        now_utc = datetime.now(timezone.utc)

        # 4. Correct Counter Differences and Rate Calculations
        in_rate_bps = 0.0
        out_rate_bps = 0.0

        if (
            state.prev_timestamp is not None
            and state.prev_in_octets is not None
            and state.prev_out_octets is not None
            and state.prev_uptime_ticks is not None
        ):
            elapsed_sec = (now_utc - state.prev_timestamp).total_seconds()

            # Check for interface discontinuity / system reboot
            if sys_uptime < state.prev_uptime_ticks:
                # Reboot occurred: reset baseline, rate is not computed for this discontinuity point
                in_rate_bps = 0.0
                out_rate_bps = 0.0
            elif elapsed_sec > 0:
                # In Octets delta with 64-bit wraparound handling
                delta_in = curr_in - state.prev_in_octets
                if delta_in < 0:
                    delta_in += UINT64_MAX

                # Out Octets delta with 64-bit wraparound handling
                delta_out = curr_out - state.prev_out_octets
                if delta_out < 0:
                    delta_out += UINT64_MAX

                # Rate in bps = (Delta Octets * 8) / elapsed_seconds
                in_rate_bps = (delta_in * 8.0) / elapsed_sec
                out_rate_bps = (delta_out * 8.0) / elapsed_sec

        # Update previous state
        state.prev_timestamp = now_utc
        state.prev_uptime_ticks = sys_uptime
        state.prev_in_octets = curr_in
        state.prev_out_octets = curr_out
        state.total_polls += 1

        snapshot = MetricSnapshot(
            timestamp=now_utc,
            sys_uptime_ticks=sys_uptime,
            if_oper_status=oper_status_str,
            if_in_octets=curr_in,
            if_out_octets=curr_out,
            in_rate_bps=round(in_rate_bps, 2),
            out_rate_bps=round(out_rate_bps, 2),
            poll_latency_ms=round(latency_ms, 2)
        )

        state.last_snapshot = snapshot
        state.history.append(snapshot)
        if len(state.history) > MAX_HISTORY_POINTS:
            state.history.pop(0)

        return snapshot

    def get_history(self, device_id: str) -> List[MetricSnapshot]:
        state = self.states.get(device_id)
        return state.history if state else []

    def get_latest_snapshot(self, device_id: str) -> Optional[MetricSnapshot]:
        state = self.states.get(device_id)
        return state.last_snapshot if state else None

    def get_total_polls(self, device_id: str) -> int:
        state = self.states.get(device_id)
        return state.total_polls if state else 0
