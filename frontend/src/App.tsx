import React, { useEffect, useState } from 'react';
import type {
  HealthStatus,
  DeviceDetail,
  DeviceMetricsHistory,
  IntervalDecisionOut,
  ComparisonMetrics,
  ComparisonHistoryPoint,
  SimulatorStatus
} from './types';
import {
  Activity,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Cpu,
  Radio,
  Zap,
  TrendingDown,
  Layers,
  BarChart3,
  RotateCcw,
  Sliders,
  Sparkles,
  Info
} from 'lucide-react';
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';

export const App: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [devices, setDevices] = useState<DeviceDetail[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('dev-01');
  const [deviceHistory, setDeviceHistory] = useState<DeviceMetricsHistory | null>(null);
  const [decisions, setDecisions] = useState<IntervalDecisionOut[]>([]);
  const [comparison, setComparison] = useState<ComparisonMetrics | null>(null);
  const [compHistory, setCompHistory] = useState<ComparisonHistoryPoint[]>([]);
  const [simStatus, setSimStatus] = useState<SimulatorStatus | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [autoPoll, setAutoPoll] = useState<boolean>(true);
  const [lastUpdated, setLastUpdated] = useState<string>('');

  const fetchAllData = async () => {
    try {
      const [healthRes, devRes, compRes, decsRes, compHistRes, simRes] = await Promise.all([
        fetch('/api/health'),
        fetch('/api/devices'),
        fetch('/api/adaptive/comparison'),
        fetch('/api/adaptive/decisions'),
        fetch('/api/adaptive/comparison-history'),
        fetch('/api/simulator/status')
      ]);

      if (healthRes.ok) setHealth(await healthRes.json());
      if (devRes.ok) setDevices(await devRes.json());
      if (compRes.ok) setComparison(await compRes.json());
      if (decsRes.ok) setDecisions(await decsRes.json());
      if (compHistRes.ok) setCompHistory(await compHistRes.json());
      if (simRes.ok) setSimStatus(await simRes.json());

      setLastUpdated(new Date().toLocaleTimeString());
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Communication error';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const fetchSelectedHistory = async (devId: string) => {
    try {
      const res = await fetch(`/api/devices/${devId}/metrics`);
      if (res.ok) {
        const hist: DeviceMetricsHistory = await res.json();
        setDeviceHistory(hist);
      }
    } catch (e) {
      console.error('Failed to fetch history', e);
    }
  };

  useEffect(() => {
    fetchAllData();
  }, []);

  useEffect(() => {
    if (selectedDeviceId) {
      fetchSelectedHistory(selectedDeviceId);
    }
  }, [selectedDeviceId]);

  // Periodic polling interval
  useEffect(() => {
    if (!autoPoll) return;
    const interval = setInterval(() => {
      fetchAllData();
      if (selectedDeviceId) {
        fetchSelectedHistory(selectedDeviceId);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [autoPoll, selectedDeviceId]);

  const handlePollNow = async () => {
    setActionLoading(true);
    try {
      await fetch('/api/simulator/poll-now', { method: 'POST' });
      await fetchAllData();
      if (selectedDeviceId) await fetchSelectedHistory(selectedDeviceId);
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSwitchMode = async (mode: 'adaptive' | 'fixed') => {
    setActionLoading(true);
    try {
      await fetch('/api/adaptive/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });
      await fetchAllData();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResetBenchmark = async () => {
    setActionLoading(true);
    try {
      await fetch('/api/adaptive/reset', { method: 'POST' });
      await fetchAllData();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(false);
    }
  };

  const handleTriggerBurst = async (deviceId: string) => {
    setActionLoading(true);
    try {
      await fetch(`/api/devices/${deviceId}/activity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ activity_profile: 'high', burst_duration_sec: 25 })
      });
      await fetchAllData();
      if (selectedDeviceId === deviceId) await fetchSelectedHistory(deviceId);
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSetProfile = async (deviceId: string, profile: string) => {
    setActionLoading(true);
    try {
      await fetch(`/api/devices/${deviceId}/activity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ activity_profile: profile })
      });
      await fetchAllData();
      if (selectedDeviceId === deviceId) await fetchSelectedHistory(deviceId);
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(false);
    }
  };

  // Preset Demonstration Scenarios
  const applyScenario = async (scenario: 'stable' | 'surge' | 'mixed') => {
    setActionLoading(true);
    try {
      if (scenario === 'stable') {
        for (const dev of devices) {
          await fetch(`/api/devices/${dev.id}/activity`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ activity_profile: 'stable' })
          });
        }
      } else if (scenario === 'surge') {
        // Trigger high burst on dev-03
        await fetch('/api/devices/dev-03/activity', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ activity_profile: 'high', burst_duration_sec: 30 })
        });
        setSelectedDeviceId('dev-03');
      } else if (scenario === 'mixed') {
        const defaults: Record<string, string> = {
          'dev-01': 'high',
          'dev-02': 'medium',
          'dev-03': 'stable',
          'dev-04': 'intermittent',
          'dev-05': 'low'
        };
        for (const [id, prof] of Object.entries(defaults)) {
          await fetch(`/api/devices/${id}/activity`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ activity_profile: prof })
          });
        }
      }
      await fetchAllData();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(false);
    }
  };

  const formatBps = (bps: number) => {
    if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(2)} Mbps`;
    if (bps >= 1_000) return `${(bps / 1_000).toFixed(1)} Kbps`;
    return `${bps.toFixed(0)} bps`;
  };

  const formatUptime = (ticks?: number) => {
    if (ticks === undefined) return '0s';
    const totalSec = Math.floor(ticks / 100);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}m ${s}s`;
  };

  const selectedDevice = devices.find((d) => d.id === selectedDeviceId);

  // Device bandwidth chart data
  const chartData = (deviceHistory?.snapshots || []).map((s) => ({
    time: new Date(s.timestamp).toLocaleTimeString(),
    inRateMbps: Number((s.in_rate_bps / 1_000_000).toFixed(3)),
    outRateMbps: Number((s.out_rate_bps / 1_000_000).toFixed(3)),
  }));

  // Overview Counts
  const activeCount = devices.filter((d) => d.activity_score >= 70 || d.activity_profile === 'high').length;
  const stableCount = devices.filter((d) => d.activity_score < 30 || d.activity_profile === 'stable').length;
  const currentMode = comparison?.mode || 'adaptive';

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col font-sans">
      {/* Top Navigation */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-20 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-blue-600 rounded-lg text-white shadow-xs">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight leading-tight">
                  Adaptive SNMP Polling Optimization
                </h1>
                {health && (
                  <span className="hidden md:inline-flex items-center px-2 py-0.5 rounded text-2xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-600" />
                    v{health.version} {simStatus ? `• ${simStatus.devices_count} Agents UDP` : ''}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 font-medium">
                Activity-Aware Intelligence for Low-Overhead Network Monitoring
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {/* Mode Switcher */}
            <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs font-semibold">
              <button
                onClick={() => handleSwitchMode('adaptive')}
                disabled={actionLoading}
                className={`px-3 py-1 rounded-md transition-all ${
                  currentMode === 'adaptive'
                    ? 'bg-blue-600 text-white shadow-xs font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Adaptive Mode
              </button>
              <button
                onClick={() => handleSwitchMode('fixed')}
                disabled={actionLoading}
                className={`px-3 py-1 rounded-md transition-all ${
                  currentMode === 'fixed'
                    ? 'bg-blue-600 text-white shadow-xs font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Fixed Mode (5s)
              </button>
            </div>

            {/* Live Polling Toggle */}
            <div className="hidden sm:flex items-center space-x-2 bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200">
              <span className="text-xs font-semibold text-slate-600">Auto-Update:</span>
              <button
                onClick={() => setAutoPoll(!autoPoll)}
                className={`text-xs font-bold px-2 py-0.5 rounded transition-colors ${
                  autoPoll ? 'bg-emerald-600 text-white' : 'bg-slate-300 text-slate-700'
                }`}
              >
                {autoPoll ? 'LIVE' : 'PAUSED'}
              </button>
            </div>

            <button
              onClick={handlePollNow}
              disabled={actionLoading}
              title="Poll all devices immediately via UDP"
              className="inline-flex items-center px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors disabled:opacity-50 shadow-xs"
            >
              <Zap className={`w-3.5 h-3.5 mr-1.5 ${actionLoading ? 'animate-spin' : ''}`} />
              Poll Now
            </button>

            <button
              onClick={fetchAllData}
              disabled={loading}
              className="p-2 text-slate-600 hover:bg-slate-100 rounded-lg border border-slate-300 transition-colors"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full space-y-6">
        {/* Error Alert */}
        {error && (
          <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-center space-x-3 text-rose-800 text-sm">
            <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* SECTION A: Overview Metric Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
              <span>Monitored Devices</span>
              <Cpu className="w-4 h-4 text-blue-600" />
            </div>
            <p className="text-2xl font-bold text-slate-900 mt-2">{devices.length}</p>
            <p className="text-xs text-slate-500 mt-1 font-mono">127.0.0.1:10161–10165</p>
          </div>

          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
              <span>Active Devices</span>
              <Activity className="w-4 h-4 text-rose-600" />
            </div>
            <p className="text-2xl font-bold text-rose-700 mt-2">{activeCount}</p>
            <p className="text-xs text-slate-500 mt-1">High / Medium traffic</p>
          </div>

          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
              <span>Stable Devices</span>
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            </div>
            <p className="text-2xl font-bold text-emerald-700 mt-2">{stableCount}</p>
            <p className="text-xs text-slate-500 mt-1">Quiescent (Score &lt; 30)</p>
          </div>

          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
            <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
              <span>Requests Saved</span>
              <TrendingDown className="w-4 h-4 text-emerald-600" />
            </div>
            <p className="text-2xl font-bold text-emerald-600 mt-2">
              {comparison ? comparison.requests_saved : 0}
            </p>
            <p className="text-xs font-semibold text-emerald-700 mt-1">
              {comparison ? `${comparison.percent_reduction}% reduction` : '0%'}
            </p>
          </div>

          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs col-span-2 sm:col-span-1">
            <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
              <span>Current Mode</span>
              <Radio className="w-4 h-4 text-indigo-600" />
            </div>
            <p className="text-2xl font-bold text-slate-900 mt-2 capitalize font-mono text-blue-700">
              {currentMode}
            </p>
            <p className="text-xs text-slate-500 mt-1">
              Avg Interval: {comparison?.average_interval_seconds || 0}s
            </p>
          </div>
        </div>

        {/* SECTION E (Interactive Demo Scenarios & Quick Controls) */}
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center space-x-2">
            <Sliders className="w-5 h-5 text-blue-600 shrink-0" />
            <div>
              <h2 className="text-sm font-bold text-slate-900">Faculty Demonstration Scenarios</h2>
              <p className="text-xs text-slate-500">
                Trigger automated network conditions to demonstrate adaptive interval shifts in real-time.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => applyScenario('stable')}
              disabled={actionLoading}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-300 hover:bg-emerald-100 transition-colors shadow-2xs"
            >
              Scenario 1: Stable Network
            </button>
            <button
              onClick={() => applyScenario('surge')}
              disabled={actionLoading}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-300 hover:bg-amber-100 transition-colors shadow-2xs flex items-center"
            >
              <Zap className="w-3.5 h-3.5 mr-1 text-amber-600" />
              Scenario 2: Traffic Spike
            </button>
            <button
              onClick={() => applyScenario('mixed')}
              disabled={actionLoading}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-blue-800 border border-blue-300 hover:bg-blue-100 transition-colors shadow-2xs"
            >
              Scenario 3: Mixed Activity
            </button>
            <button
              onClick={handleResetBenchmark}
              disabled={actionLoading}
              title="Reset comparison counters to 0 for a clean benchmark"
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors flex items-center border border-slate-300"
            >
              <RotateCcw className="w-3.5 h-3.5 mr-1" />
              Reset Benchmark
            </button>
          </div>
        </div>

        {/* SECTION D: Performance Comparison (Side-by-Side Fixed vs Adaptive) */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-6 space-y-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-slate-100 pb-4 gap-2">
            <div>
              <div className="flex items-center space-x-2">
                <BarChart3 className="w-5 h-5 text-blue-600" />
                <h2 className="text-base font-bold text-slate-900">
                  Performance Comparison: Traditional Fixed vs Adaptive Polling
                </h2>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Exact request accounting evaluated over {comparison?.elapsed_seconds || 0} seconds of continuous runtime.
              </p>
            </div>

            <div className="flex items-center space-x-2 text-xs">
              <span className="inline-flex items-center px-2.5 py-1 rounded-full font-semibold bg-emerald-100 text-emerald-800">
                <Sparkles className="w-3.5 h-3.5 mr-1 text-emerald-600" />
                {comparison?.percent_reduction || 0}% Overhead Reduction
              </span>
            </div>
          </div>

          {/* Comparative Metrics Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Mode 1: Traditional Fixed */}
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
              <div className="flex justify-between items-center text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <span>Traditional Fixed Polling</span>
                <span className="px-2 py-0.5 rounded bg-slate-200 text-slate-700 font-mono">5.0s fixed</span>
              </div>
              <div className="mt-3">
                <span className="text-3xl font-extrabold text-slate-800">
                  {comparison?.total_fixed_requests || 0}
                </span>
                <span className="text-xs text-slate-500 ml-1.5 font-medium">requests</span>
              </div>
              <p className="text-xs text-slate-500 mt-2">
                Every device queried indiscriminately every 5.0 seconds regardless of quiescence.
              </p>
            </div>

            {/* Mode 2: Adaptive Polling */}
            <div className="bg-blue-50/60 p-4 rounded-xl border border-blue-200">
              <div className="flex justify-between items-center text-xs font-semibold text-blue-800 uppercase tracking-wider">
                <span>Our Adaptive Polling</span>
                <span className="px-2 py-0.5 rounded bg-blue-200 text-blue-800 font-mono">5s / 15s / 30s</span>
              </div>
              <div className="mt-3">
                <span className="text-3xl font-extrabold text-blue-900">
                  {comparison?.total_adaptive_requests || 0}
                </span>
                <span className="text-xs text-blue-700 ml-1.5 font-medium">requests</span>
              </div>
              <p className="text-xs text-blue-700 mt-2">
                Active devices polled at 5s; stable devices relaxed to 30s with hysteresis.
              </p>
            </div>

            {/* Savings & Efficiency */}
            <div className="bg-emerald-50/60 p-4 rounded-xl border border-emerald-200">
              <div className="flex justify-between items-center text-xs font-semibold text-emerald-800 uppercase tracking-wider">
                <span>Management Traffic Saved</span>
                <span className="px-2 py-0.5 rounded bg-emerald-200 text-emerald-800 font-bold">
                  {comparison?.percent_reduction || 0}%
                </span>
              </div>
              <div className="mt-3">
                <span className="text-3xl font-extrabold text-emerald-700">
                  {comparison?.requests_saved || 0}
                </span>
                <span className="text-xs text-emerald-600 ml-1.5 font-medium">packets avoided</span>
              </div>
              <p className="text-xs text-emerald-700 mt-2">
                Formula: (Fixed − Adaptive) ÷ Fixed × 100 calculated from real packet counts.
              </p>
            </div>
          </div>

          {/* Comparative Cumulative Trend Chart */}
          {compHistory.length > 1 && (
            <div className="mt-4 pt-4 border-t border-slate-100">
              <div className="flex justify-between items-center mb-3">
                <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Cumulative Polling Requests Over Time
                </span>
                <span className="text-2xs text-slate-400">Sampled every 2 seconds</span>
              </div>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={compHistory} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="time_str" tick={{ fontSize: 10, fill: '#64748b' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '12px' }}
                    />
                    <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '4px' }} />
                    <Line
                      type="monotone"
                      dataKey="fixed_requests"
                      name="Fixed (5s baseline)"
                      stroke="#94a3b8"
                      strokeWidth={2}
                      strokeDasharray="4 4"
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="adaptive_requests"
                      name="Our Adaptive Poller"
                      stroke="#2563eb"
                      strokeWidth={2.5}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="requests_saved"
                      name="Packets Saved"
                      stroke="#10b981"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>

        {/* SECTION B: Monitored Devices & Live Telemetry Table */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
            <div>
              <h2 className="text-base font-bold text-slate-900">Monitored Device Telemetry</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Activity scores, dynamic intervals, priorities, and calculated bitrates. Click a row to inspect.
              </p>
            </div>
            <span className="text-xs text-slate-400">Updated: {lastUpdated}</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 text-xs font-semibold uppercase tracking-wider">
                <tr>
                  <th className="py-3 px-5">Device</th>
                  <th className="py-3 px-4">Profile</th>
                  <th className="py-3 px-4">Activity Score</th>
                  <th className="py-3 px-4">Polling Interval</th>
                  <th className="py-3 px-4">Priority</th>
                  <th className="py-3 px-4">Bitrates (bps)</th>
                  <th className="py-3 px-4">Polls</th>
                  <th className="py-3 px-5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {devices.map((dev) => {
                  const isSelected = dev.id === selectedDeviceId;
                  return (
                    <tr
                      key={dev.id}
                      onClick={() => setSelectedDeviceId(dev.id)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-blue-50/70' : 'hover:bg-slate-50/70'
                      }`}
                    >
                      <td className="py-3.5 px-5">
                        <div className="flex items-center space-x-2">
                          <span
                            className={`w-2.5 h-2.5 rounded-full ${
                              isSelected ? 'bg-blue-600 ring-4 ring-blue-100' : 'bg-slate-300'
                            }`}
                          />
                          <div>
                            <div className="font-semibold text-slate-900 flex items-center space-x-1.5">
                              <span>{dev.name}</span>
                              <span className="text-2xs font-mono uppercase bg-slate-100 text-slate-600 px-1 rounded">
                                {dev.device_type}
                              </span>
                            </div>
                            <div className="text-xs text-slate-500 font-mono">
                              127.0.0.1:{dev.port} • Uptime: {formatUptime(dev.latest_metrics?.sys_uptime_ticks)}
                            </div>
                          </div>
                        </div>
                      </td>

                      <td className="py-3.5 px-4">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold uppercase ${
                            dev.activity_profile === 'high'
                              ? 'bg-rose-100 text-rose-800'
                              : dev.activity_profile === 'medium'
                              ? 'bg-amber-100 text-amber-800'
                              : dev.activity_profile === 'intermittent'
                              ? 'bg-purple-100 text-purple-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {dev.activity_profile}
                        </span>
                      </td>

                      <td className="py-3.5 px-4">
                        <div className="flex items-center space-x-2">
                          <div className="w-16 bg-slate-200 rounded-full h-2 overflow-hidden">
                            <div
                              className={`h-2 rounded-full ${
                                dev.activity_score >= 70
                                  ? 'bg-rose-500'
                                  : dev.activity_score >= 30
                                  ? 'bg-amber-500'
                                  : 'bg-emerald-500'
                              }`}
                              style={{ width: `${Math.min(100, dev.activity_score)}%` }}
                            />
                          </div>
                          <span className="font-mono text-xs font-bold text-slate-700">
                            {dev.activity_score}
                          </span>
                        </div>
                      </td>

                      <td className="py-3.5 px-4">
                        <span
                          className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-bold font-mono ${
                            dev.current_interval <= 5.0
                              ? 'bg-rose-50 text-rose-700 border border-rose-200'
                              : dev.current_interval <= 15.0
                              ? 'bg-amber-50 text-amber-700 border border-amber-200'
                              : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          }`}
                        >
                          {dev.current_interval}s
                        </span>
                      </td>

                      <td className="py-3.5 px-4">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-2xs font-bold uppercase ${
                            dev.priority_level === 1
                              ? 'bg-rose-600 text-white'
                              : dev.priority_level === 2
                              ? 'bg-amber-500 text-white'
                              : 'bg-slate-400 text-white'
                          }`}
                        >
                          P{dev.priority_level}
                        </span>
                      </td>

                      <td className="py-3.5 px-4 font-mono text-xs">
                        <div className="text-emerald-700 font-semibold">↓ {formatBps(dev.in_octets_rate)}</div>
                        <div className="text-blue-700">↑ {formatBps(dev.out_octets_rate)}</div>
                      </td>

                      <td className="py-3.5 px-4 font-mono text-xs text-slate-600">
                        {dev.total_polls_count}
                      </td>

                      <td className="py-3.5 px-5 text-right space-x-2" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => handleTriggerBurst(dev.id)}
                          title="Inject high activity traffic for 25s"
                          className="inline-flex items-center px-2.5 py-1 text-xs font-semibold rounded bg-amber-500 hover:bg-amber-600 text-white transition-colors shadow-2xs"
                        >
                          <Zap className="w-3 h-3 mr-1" />
                          Burst
                        </button>
                        <select
                          value={dev.activity_profile}
                          onChange={(e) => handleSetProfile(dev.id, e.target.value)}
                          className="text-xs bg-white border border-slate-300 rounded px-2 py-1 text-slate-700 font-medium"
                        >
                          <option value="stable">Stable</option>
                          <option value="low">Low</option>
                          <option value="medium">Medium</option>
                          <option value="high">High</option>
                          <option value="intermittent">Intermittent</option>
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* SECTION C: Adaptive Polling Monitor & Deep Dive */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Selected Device Telemetry & Bandwidth Chart */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-xs p-6 space-y-4">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-slate-100 pb-3 gap-2">
              <div>
                <div className="flex items-center space-x-2">
                  <Activity className="w-4 h-4 text-blue-600" />
                  <h3 className="text-sm font-bold text-slate-900">
                    Live Interface Bandwidth: {selectedDevice?.name || 'Select Device'}
                  </h3>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Calculated from <code>ifHCInOctets</code> / <code>ifHCOutOctets</code> deltas over UDP
                </p>
              </div>

              {selectedDevice && (
                <div className="flex items-center space-x-3 text-xs">
                  <span className="font-semibold text-emerald-700">
                    In: {formatBps(selectedDevice.in_octets_rate)}
                  </span>
                  <span className="font-semibold text-blue-700">
                    Out: {formatBps(selectedDevice.out_octets_rate)}
                  </span>
                </div>
              )}
            </div>

            {chartData.length > 1 ? (
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="inBwColor" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                      </linearGradient>
                      <linearGradient id="outBwColor" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#64748b' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#64748b' }} unit=" Mbps" />
                    <Tooltip
                      formatter={(val: any) => [`${val} Mbps`, '']}
                      contentStyle={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '12px' }}
                    />
                    <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '4px' }} />
                    <Area
                      type="monotone"
                      dataKey="inRateMbps"
                      name="Inbound (Mbps)"
                      stroke="#10b981"
                      fill="url(#inBwColor)"
                      strokeWidth={2}
                    />
                    <Area
                      type="monotone"
                      dataKey="outRateMbps"
                      name="Outbound (Mbps)"
                      stroke="#3b82f6"
                      fill="url(#outBwColor)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-44 flex items-center justify-center text-slate-400 text-xs">
                Awaiting SNMP counter cycles...
              </div>
            )}
          </div>

          {/* Adaptive Decision Insight Card */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-6 flex flex-col justify-between space-y-4">
            <div>
              <div className="flex items-center space-x-2 border-b border-slate-100 pb-3">
                <Info className="w-4 h-4 text-blue-600" />
                <h3 className="text-sm font-bold text-slate-900">Adaptive Decision Insight</h3>
              </div>

              {selectedDevice ? (
                <div className="mt-4 space-y-3 text-xs">
                  <div>
                    <span className="text-slate-500">Device Target:</span>
                    <p className="font-semibold text-slate-800">{selectedDevice.name} ({selectedDevice.ip}:{selectedDevice.port})</p>
                  </div>
                  <div>
                    <span className="text-slate-500">Current Polling Interval:</span>
                    <p className="font-bold text-sm text-blue-700">{selectedDevice.current_interval} seconds</p>
                  </div>
                  <div>
                    <span className="text-slate-500">Priority Tier:</span>
                    <p className="font-semibold text-slate-800">
                      Tier {selectedDevice.priority_level} ({selectedDevice.priority_level === 1 ? 'High/Anomaly' : selectedDevice.priority_level === 2 ? 'Moderate' : 'Stable'})
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-500">Hysteresis Stability Count:</span>
                    <p className="font-semibold text-slate-800">
                      {selectedDevice.consecutive_stable_count} / 3 cycles to relaxation
                    </p>
                  </div>
                  <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                    <span className="font-semibold text-slate-700">Engine Rationale:</span>
                    <p className="text-slate-600 mt-1 italic leading-relaxed">
                      "{selectedDevice.interval_reason}"
                    </p>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-slate-400 mt-4">Select a device from the table above.</p>
              )}
            </div>

            <div className="pt-3 border-t border-slate-100 text-2xs text-slate-400 flex items-center justify-between">
              <span>Hysteresis Guard: 3 Cycles</span>
              <span>Starvation Limit: 30s</span>
            </div>
          </div>
        </div>

        {/* Live Engine Decision Trail Table */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="px-6 py-3 border-b border-slate-200 flex justify-between items-center bg-slate-50/50">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center">
              <Layers className="w-3.5 h-3.5 mr-1.5 text-blue-600" />
              Recent Interval Scheduling Decisions (Hysteresis Log)
            </h3>
            <span className="text-2xs text-slate-400">Last 15 decisions</span>
          </div>

          <div className="overflow-x-auto max-h-56">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 uppercase font-semibold text-2xs">
                <tr>
                  <th className="py-2.5 px-5">Time</th>
                  <th className="py-2.5 px-4">Device ID</th>
                  <th className="py-2.5 px-4">Activity Score</th>
                  <th className="py-2.5 px-4">Interval Transition</th>
                  <th className="py-2.5 px-4">Priority</th>
                  <th className="py-2.5 px-5">Decision Reason & Hysteresis State</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {decisions.slice(0, 15).map((dec, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/60">
                    <td className="py-2 px-5 font-mono text-slate-500">
                      {new Date(dec.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="py-2 px-4 font-mono font-semibold text-slate-800">
                      {dec.device_id}
                    </td>
                    <td className="py-2 px-4 font-mono font-bold text-slate-700">
                      {dec.activity_score}
                    </td>
                    <td className="py-2 px-4 font-mono font-semibold">
                      <span className="text-slate-500">{dec.previous_interval}s</span>
                      <span className="mx-1 text-slate-400">→</span>
                      <span className="text-blue-700 font-bold">{dec.new_interval}s</span>
                    </td>
                    <td className="py-2 px-4">
                      <span className="px-1.5 py-0.5 rounded text-2xs font-bold bg-slate-100 text-slate-700">
                        P{dec.priority_level}
                      </span>
                    </td>
                    <td className="py-2 px-5 text-slate-600 font-medium">
                      {dec.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 py-4 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row justify-between items-center text-xs text-slate-500">
          <p>Academic Project — Network Design and Management (FT-III)</p>
          <p className="mt-2 sm:mt-0 font-medium">Phase 4: Interactive Dashboard & Performance Comparison</p>
        </div>
      </footer>
    </div>
  );
};

export default App;
