# Adaptive SNMP Polling Optimization for Low-Overhead Network Monitoring

**Academic Prototype for Network Design and Management (FT-III)**  
*Designed for demonstration, verifiable telemetry, and faculty evaluation.*

---

## 1. Project Objective & Novelty

Traditional Simple Network Management Protocol (SNMP) monitoring software queries all managed routers, switches, and hosts using a static, fixed polling interval (typically 5 to 60 seconds). In large campus and enterprise networks, fixed polling leads to:
1. **Excessive Management Overhead:** Hundreds of quiescent, idle devices are repeatedly queried for identical counter values, wasting monitoring bandwidth and polling processing cycles.
2. **Delayed Detection during Spikes:** Fixed intervals cannot dynamically adapt when a link suddenly experiences congestion, anomalous traffic spikes, or interface state flaps.

### The Novel Contribution: Activity-Aware Adaptive Polling Engine
Our prototype introduces a lightweight, explainable adaptive engine that dynamically modulates polling intervals according to measured traffic dynamics:
- **Feature A (Derived Activity Scoring):** Evaluates real counter differences and relative volatility to assign a continuous score ($0.0 - 100.0$), rather than arbitrary random weights.
- **Feature B (3-Tier Dynamic Intervals):**
  - **High Activity (Score $\ge 70.0$):** $5.0\text{s}$ interval (Priority 1).
  - **Medium Activity ($30.0 \le \text{Score} < 70.0$):** $15.0\text{s}$ interval (Priority 2).
  - **Stable / Quiescent (Score $< 30.0$):** $30.0\text{s}$ interval (Priority 3).
- **Feature C (Hysteresis Stability Guard):**
  - *Fast Escalation:* Instantaneous jump to $5.0\text{s}$ upon anomaly detection.
  - *Anti-Flapping:* Requires $K = 3$ consecutive stable observations before relaxing intervals.
- **Feature D (Priority Scheduling & Starvation Prevention):** Highest urgency devices are polled first, but any device reaching `MAX_STARVATION_DELAY` ($30.0\text{s}$) is guaranteed an immediate poll.
- **Feature E (Mathematical Fixed vs. Adaptive Comparison):** Computes exact packet savings:
  $$\text{Requests Saved} = \text{Requests}_{\text{Fixed}} - \text{Requests}_{\text{Adaptive}}$$
  $$\text{Percentage Reduction} = \frac{\text{Requests Saved}}{\text{Requests}_{\text{Fixed}}} \times 100$$

---

## 2. Technology Stack & System Architecture

### Architecture Diagram
```text
               +-------------------------------------------------------+
               |                  REACT 19 + VITE UI                   |
               | (Tailwind CSS, Recharts Area/Line, Lucide Dashboard)  |
               +---------------------------+---------------------------+
                                           | HTTP REST / JSON
                                           v
               +-------------------------------------------------------+
               |                 FASTAPI BACKEND (8000)                |
               |                                                       |
               |  +------------------------+  +---------------------+  |
               |  | Adaptive Engine        |  | SNMP Poller         |  |
               |  | - Activity Scorer      |  | - UDP Query Client  |  |
               |  | - Hysteresis Control   |  | - 64-bit HC Deltas  |  |
               |  | - Priority Dispatcher  |  | - Discontinuity Det.|  |
               |  +------------------------+  +----------+----------+  |
               +-----------------------------------------|-------------+
                                                         | Real UDP Datagrams
                                                         v (RFC 1901/1905)
               +-------------------------------------------------------+
               |              5x UDP SNMP v2c AGENTS                   |
               |   dev-01: Port 10161 (High Traffic Profile)           |
               |   dev-02: Port 10162 (Medium Traffic Profile)         |
               |   dev-03: Port 10163 (Stable Quiescent Profile)       |
               |   dev-04: Port 10164 (Intermittent Traffic Burst)     |
               |   dev-05: Port 10165 (Low Activity Profile)           |
               +-------------------------------------------------------+
```

### Components:
- **Frontend:** React 19, Vite, TypeScript, Tailwind CSS, Recharts.
- **Backend:** Python 3.13, FastAPI, Uvicorn, Pydantic v2.
- **SNMP Engine:** PySNMP 7.1 with asynchronous BER/DER decoding over UDP sockets (`127.0.0.1:10161–10165`).
- **Standard MIB Objects:**
  - `sysUpTime.0` (`1.3.6.1.2.1.1.3.0`)
  - `ifOperStatus.1` (`1.3.6.1.2.1.2.2.1.8.1`)
  - `ifHCInOctets.1` (`1.3.6.1.2.1.31.1.1.1.6.1`) [64-bit High-Capacity]
  - `ifHCOutOctets.1` (`1.3.6.1.2.1.31.1.1.1.10.1`) [64-bit High-Capacity]
  - `ifHighSpeed.1` (`1.3.6.1.2.1.31.1.1.1.15.1`)

---

## 3. Windows 11 Step-by-Step Execution

### Prerequisites
- Python 3.11+ installed and on system PATH.
- Node.js 18+ and npm.

### Step 1: Start Backend
Open a PowerShell terminal in `NDM PROJECT/backend`:
```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# (Optional) Run automated tests
pytest tests

# Launch FastAPI backend with live reload
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
API Docs available at: `http://127.0.0.1:8000/docs`

### Step 2: Start Frontend
Open a second PowerShell terminal in `NDM PROJECT/frontend`:
```powershell
# Start Vite development server
npm run dev
```
Open your browser at: `http://localhost:5173`

---

## 4. Faculty Demonstration Script (Step-by-Step)

When presenting to your professor, follow these 3 demonstration steps:

### Scenario 1: Stable Network (Low Overhead Mode)
1. In the top control bar, click **"Scenario 1: Stable Network"**.
2. Click **"Reset Benchmark"**.
3. **Observe:** All devices settle into the $30.0\text{s}$ interval (Priority 3).
4. **Faculty Talking Point:** *"Professor, under stable conditions, traditional fixed polling would query devices every 5 seconds (generating 12-20 requests). Our adaptive engine relaxes intervals to 30 seconds, saving 70% to 75% of monitoring packets without losing connectivity."*

### Scenario 2: Sudden Traffic Surge & Fast Escalation
1. Click **"Scenario 2: Traffic Spike"** (or click the **"Burst"** button on `Access-Switch-West dev-03`).
2. **Observe:** Within 1 second, `dev-03` traffic jumps to ~60 Mbps. The activity score jumps to $100.0$, the interval immediately escalates from $30.0\text{s}$ to $5.0\text{s}$ (Priority 1), and the decision reason reports *"Activity surge; expedited polling"*.
3. **Faculty Talking Point:** *"Notice that escalation is instantaneous. The moment anomaly or burst traffic is detected on a stable device, our engine immediately escalates polling to 5 seconds to ensure real-time visibility."*

### Scenario 3: Hysteresis Hold & Anti-Flapping
1. Allow the 25-second burst to expire (or set `dev-03` profile back to **"Stable"**).
2. Look at the **"Adaptive Decision Insight"** card and the **"Hysteresis Stability Count"**.
3. **Observe:** Notice that the polling interval **does not** immediately switch back to 30s. It displays *"Hysteresis hold (1/3 cycles)"* and *"Hysteresis hold (2/3 cycles)"*. Only after 3 consecutive stable observations does it relax to 30s.
4. **Faculty Talking Point:** *"This proves our hysteresis innovation. In naive adaptive systems, temporary dips cause interval flapping. Our engine requires 3 consecutive cycles of verified stability before relaxing back to 30s."*

---

## 5. Likely Viva Questions & Explanations

### Q1: What formula did you use to calculate traffic rate from SNMP counters?
> **Answer:** *"We use the standard SNMP counter differential formula:  
> $\text{Rate (bps)} = \frac{(\text{Current Octets} - \text{Previous Octets}) \times 8}{\text{Elapsed Seconds}}$  
> Cumulative counters cannot be treated as instantaneous bandwidth. We also implement 64-bit wraparound arithmetic $(2^{64})$ and interface discontinuity checks when `sysUpTime` resets."*

### Q2: Why did you use 64-bit counters (`ifHCInOctets`) instead of 32-bit (`ifInOctets`)?
> **Answer:** *"At Gigabit speeds (1 Gbps+), standard 32-bit counters overflow and wrap around in approximately 34 seconds. High-Capacity 64-bit counters (RFC 2863) prevent false rollover calculations during longer polling intervals."*

### Q3: How is your Activity Score calculated? Is it just random?
> **Answer:** *"No, the score is strictly calculated by our `ActivityScorer` using three deterministic metrics:  
> 1. Bandwidth relative to link capacity (0–50 points).  
> 2. Relative traffic delta between consecutive polls (0–50 points) to detect volatility.  
> 3. Operational status transitions (link DOWN immediately assigns 100.0 points)."*

### Q4: What prevents a low-priority device from being ignored indefinitely (starvation)?
> **Answer:** *"Our scheduler implements a hard `MAX_STARVATION_DELAY` of 30 seconds. Even if a device is completely quiescent at Priority 3, once 30 seconds elapse since its last poll, the scheduler forces it to the front of the dispatch queue."*

### Q5: How do you prove your system actually saves management requests?
> **Answer:** *"Our dashboard runs a real-time side-by-side accounting model comparing actual adaptive UDP requests against the standard 5-second fixed polling baseline. The percentage reduction is calculated strictly from packet counts: $\frac{\text{Fixed} - \text{Adaptive}}{\text{Fixed}} \times 100$."*

---

## 6. Known Prototype Assumptions & Limitations
- **Router CPU Reduction:** In accordance with academic honesty standards, we do not claim direct router CPU reductions since tests are evaluated against simulated UDP SNMP agents rather than physical Cisco/Juniper hardware ASIC chips.
- **Transport:** Standard SNMP v2c over UDP; SNMP v3 cryptographic authentication is reserved for future enterprise work.
