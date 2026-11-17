export interface HealthStatus {
  status: string;
  version: string;
  service: string;
  timestamp: string;
}

export interface MetricSnapshot {
  timestamp: string;
  sys_uptime_ticks: number;
  if_oper_status: string;
  if_in_octets: number;
  if_out_octets: number;
  in_rate_bps: number;
  out_rate_bps: number;
  poll_latency_ms: number;
}

export interface DeviceDetail {
  id: string;
  name: string;
  ip: string;
  port: number;
  community: string;
  device_type: 'router' | 'switch' | 'server';
  activity_profile: 'stable' | 'low' | 'medium' | 'high' | 'intermittent';
  is_active: boolean;
  current_interval: number;
  last_polled_at?: string;
  activity_score: number;
  priority_level: number;
  oper_status: string;
  in_octets_rate: number;
  out_octets_rate: number;
  total_polls_count: number;
  interval_reason: string;
  consecutive_stable_count: number;
  latest_metrics?: MetricSnapshot;
}

export interface DeviceMetricsHistory {
  device_id: string;
  device_name: string;
  snapshots: MetricSnapshot[];
}

export interface IntervalDecisionOut {
  device_id: string;
  activity_score: number;
  previous_interval: number;
  new_interval: number;
  priority_level: number;
  reason: string;
  hysteresis_count: number;
  timestamp: string;
}

export interface ComparisonMetrics {
  mode: string;
  elapsed_seconds: number;
  total_fixed_requests: number;
  total_adaptive_requests: number;
  requests_saved: number;
  percent_reduction: number;
  average_interval_seconds: number;
  fixed_interval_seconds: number;
  device_count: number;
}

export interface ComparisonHistoryPoint {
  timestamp: string;
  time_str: string;
  elapsed_seconds: number;
  fixed_requests: number;
  adaptive_requests: number;
  requests_saved: number;
  percent_reduction: number;
}

export interface SimulatorStatus {
  is_running: boolean;
  polling_mode: string;
  devices_count: number;
  total_polls_performed: number;
  active_udp_ports: number[];
  comparison?: ComparisonMetrics;
  timestamp: string;
}
