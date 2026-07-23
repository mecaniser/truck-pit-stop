import { useEffect, useState, useCallback } from 'react'
import { Spinner } from '@/components/ui'
import { 
  Activity, Server, Database,
  Clock, AlertTriangle, RefreshCw,
  CheckCircle, XCircle, Gauge
} from 'lucide-react'
import api from '../../lib/api'
import StatusIndicator from './components/StatusIndicator'
import MetricCard from './components/MetricCard'
import { GlassNoirCard } from '../../components/ui/GlassNoirCard'
import { StatScrollRow, CollapsibleStats, InlineStats } from '../../components/ui/MobileStats'

interface HealthData {
  status: string
  checks: {
    database: { status: string; latency_ms: number }
    redis: { status: string; latency_ms: number }
  }
  version: string
  environment: string
  uptime_seconds: number
}

interface PerformanceStats {
  http: {
    requests_total: number
    requests_by_status: { '2xx': number; '4xx': number; '5xx': number }
    requests_by_endpoint: Array<{ path: string; count: number }>
    slowest_endpoints: Array<{
      path: string
      requests: number
      avg_latency_ms: number
      p95_latency_ms: number
    }>
    avg_latency_ms: number
    p50_latency_ms: number
    p95_latency_ms: number
    p99_latency_ms: number
    requests_in_progress: number
  }
  activity_window: {
    window_seconds: number
    observed_seconds: number
    request_count: number
    requests_per_minute: number
    p95_latency_ms: number
    error_rate_percent: number
    error_count: number
  }
  business: {
    logins: { success: number; failure: number }
    logouts: number
    orders_created: number
    quotes: { created: number; approved: number; declined: number }
    payments: { success: number; failure: number }
  }
  system: {
    python_version: string
    gc_collections: number
    process_cpu_seconds: number
    process_memory_bytes: number
    active_users: number
  }
  alerts: Array<{
    severity: 'warning' | 'critical'
    title: string
    detail: string
  }>
}

function getHealthReadyUrl() {
  const apiUrl = (import.meta.env.VITE_API_URL || '/api/v1').replace(/\/+$/, '')
  const backendBase = apiUrl.replace(/\/api\/v1$/, '')
  return backendBase ? `${backendBase}/health/ready` : '/health/ready'
}

function getInfrastructureAlerts(health: HealthData | null): PerformanceStats['alerts'] {
  if (!health) return []

  const checks = [
    { label: 'Database health check', latency: health.checks.database?.latency_ms, target: 200 },
    { label: 'Redis health check', latency: health.checks.redis?.latency_ms, target: 100 },
  ]

  return checks.flatMap(({ label, latency, target }) => {
    if (latency == null || latency < target) return []
    const severity: 'warning' | 'critical' = latency >= target * 2.5 ? 'critical' : 'warning'
    return [{
      severity,
      title: `${label} is slow`,
      detail: `${latency.toFixed(1)}ms; target is below ${target}ms.`,
    }]
  })
}

async function fetchHealthReady(): Promise<HealthData> {
  const response = await fetch(getHealthReadyUrl(), { credentials: 'include' })
  if (!response.ok) {
    throw new Error(`Health check failed (${response.status})`)
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.toLowerCase().includes('application/json')) {
    throw new Error('Health endpoint returned non-JSON response')
  }

  return response.json()
}

export default function PerformanceTab() {
  const refreshIntervalMs = 15_000
  const [health, setHealth] = useState<HealthData | null>(null)
  const [stats, setStats] = useState<PerformanceStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())
  const [autoRefresh, setAutoRefresh] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const [healthRes, statsRes] = await Promise.all([
        fetchHealthReady(),
        api.get('/admin/performance/stats'),
      ])
      setHealth(healthRes)
      setStats(statsRes.data)
      setError(null)
      setLastRefresh(new Date())
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load performance data')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Refresh frequently enough to observe the rolling server window without
  // turning this dashboard into its own workload.
  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(fetchData, refreshIntervalMs)
    return () => clearInterval(interval)
  }, [autoRefresh, fetchData])

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    if (days > 0) return `${days}d ${hours}h ${mins}m`
    if (hours > 0) return `${hours}h ${mins}m`
    return `${mins}m`
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
  }

  const formatLatency = (ms: number) => {
    if (ms < 1) return `${(ms * 1000).toFixed(0)}µs`
    if (ms < 1000) return `${ms.toFixed(1)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  const getHealthStatus = (check: { status: string }): 'healthy' | 'error' => {
    return check.status === 'healthy' || check.status === 'ok' ? 'healthy' : 'error'
  }

  const getLatencyStatus = (ms: number): 'healthy' | 'warning' | 'error' => {
    if (ms < 50) return 'healthy'
    if (ms < 200) return 'warning'
    return 'error'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="xl" />
      </div>
    )
  }

  if (error) {
    return (
      <GlassNoirCard className="border-red-500/30">
        <p className="text-red-400">{error}</p>
        <button 
          onClick={fetchData}
          className="mt-4 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-colors"
        >
          Retry
        </button>
      </GlassNoirCard>
    )
  }

  const totalRequests = stats?.http.requests_total || 0
  const activityWindow = stats?.activity_window
  const performanceAlerts = [
    ...(stats?.alerts || []),
    ...getInfrastructureAlerts(health),
  ]

  const loginSuccessRate = (stats?.business.logins.success || 0) + (stats?.business.logins.failure || 0) > 0
    ? (stats?.business.logins.success || 0) / ((stats?.business.logins.success || 0) + (stats?.business.logins.failure || 0)) * 100
    : 100

  return (
    <div className="space-y-6">
      {/* Refresh Controls */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-400 space-y-0.5">
          <div>Last updated: {lastRefresh.toLocaleTimeString()}</div>
          <div className="text-xs text-gray-500">
            Current process window: {formatUptime(health?.uptime_seconds || 0)}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-gold-500/30 bg-black/40 text-gold-500 focus:ring-gold-500"
            />
            Auto-refresh (15s)
          </label>
          <button
            onClick={fetchData}
            className="flex items-center gap-2 px-3 py-1.5 bg-gold-500/10 hover:bg-gold-500/20 text-gold-400 border border-gold-500/30 rounded-lg transition-colors text-sm"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* System Health Panel */}
      <GlassNoirCard padding="none" className="p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 sm:mb-4">
          <h2 className="text-base font-semibold text-white sm:text-lg">System Health</h2>
          <Server className="w-5 h-5 text-gold-400" />
        </div>
        
        <div className="grid grid-cols-2 gap-x-4 gap-y-4 md:grid-cols-2 md:gap-6 lg:grid-cols-4">
          {/* API Status */}
          <div className="min-w-0 space-y-2 sm:space-y-3">
            <StatusIndicator
              status={health?.status === 'healthy' || health?.status === 'ready' ? 'healthy' : 'error'}
              label="API Status"
              sublabel={health?.environment || 'unknown'}
              compactOnMobile
            />
            <div className="text-xs text-gray-500">
              Version: {health?.version || 'unknown'}
            </div>
          </div>

          {/* Database */}
          <div className="min-w-0 space-y-2 sm:space-y-3">
            <StatusIndicator
              status={health?.checks.database ? getHealthStatus(health.checks.database) : 'unknown'}
              label="Database"
              sublabel={health?.checks.database ? `${health.checks.database.latency_ms.toFixed(1)}ms` : 'N/A'}
              compactOnMobile
            />
            <div className="w-full bg-gray-700 rounded-full h-1.5">
              <div 
                className={`h-1.5 rounded-full transition-all ${
                  getLatencyStatus(health?.checks.database?.latency_ms || 0) === 'healthy' 
                    ? 'bg-green-500' 
                    : getLatencyStatus(health?.checks.database?.latency_ms || 0) === 'warning'
                    ? 'bg-yellow-500'
                    : 'bg-red-500'
                }`}
                style={{ width: `${Math.min((health?.checks.database?.latency_ms || 0) / 2, 100)}%` }}
              />
            </div>
          </div>

          {/* Redis */}
          <div className="min-w-0 space-y-2 sm:space-y-3">
            <StatusIndicator
              status={health?.checks.redis ? getHealthStatus(health.checks.redis) : 'unknown'}
              label="Redis Cache"
              sublabel={health?.checks.redis ? `${health.checks.redis.latency_ms.toFixed(1)}ms` : 'N/A'}
              compactOnMobile
            />
            <div className="w-full bg-gray-700 rounded-full h-1.5">
              <div 
                className={`h-1.5 rounded-full transition-all ${
                  getLatencyStatus(health?.checks.redis?.latency_ms || 0) === 'healthy' 
                    ? 'bg-green-500' 
                    : getLatencyStatus(health?.checks.redis?.latency_ms || 0) === 'warning'
                    ? 'bg-yellow-500'
                    : 'bg-red-500'
                }`}
                style={{ width: `${Math.min((health?.checks.redis?.latency_ms || 0) / 2, 100)}%` }}
              />
            </div>
          </div>

          {/* Uptime */}
          <div className="min-w-0">
            <div className="flex items-center gap-2 sm:gap-3">
              <div className="shrink-0 p-1.5 bg-gold-500/10 rounded-lg border border-gold-500/20 sm:p-2">
                <Clock className="w-4 h-4 text-gold-400 sm:w-5 sm:h-5" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-gold-400 sm:text-base">Uptime</div>
                <div className="truncate text-base font-bold text-white sm:text-lg">
                  {formatUptime(health?.uptime_seconds || 0)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </GlassNoirCard>

      {/* Performance alerts */}
      <GlassNoirCard className={performanceAlerts.length > 0 ? 'border-amber-500/30' : ''}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Performance Alerts</h2>
            <p className="text-xs text-gray-500 mt-1">Five-minute request window; request rules activate after 10 samples.</p>
          </div>
          <AlertTriangle className={`w-5 h-5 ${performanceAlerts.some((alert) => alert.severity === 'critical') ? 'text-red-400' : performanceAlerts.length ? 'text-amber-400' : 'text-green-400'}`} />
        </div>

        {performanceAlerts.length === 0 ? (
          <div className="text-sm text-green-400">No active performance rule breaches.</div>
        ) : (
          <div className="space-y-3">
            {performanceAlerts.map((alert, index) => (
              <div key={`${alert.title}-${index}`} className={`border-l-2 pl-3 ${alert.severity === 'critical' ? 'border-red-500' : 'border-amber-500'}`}>
                <div className={`text-sm font-medium ${alert.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}`}>{alert.title}</div>
                <div className="text-sm text-gray-400 mt-0.5">{alert.detail}</div>
              </div>
            ))}
          </div>
        )}
      </GlassNoirCard>

      {/* Process Metrics */}
      <GlassNoirCard padding="none" className="p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 sm:mb-4">
          <div>
            <h2 className="text-base font-semibold text-white sm:text-lg">Process Metrics</h2>
            <p className="text-[11px] leading-4 text-gray-500 mt-0.5 sm:mt-1 sm:text-xs">
              Rolling activity window, up to {Math.round((activityWindow?.window_seconds || 300) / 60)} minutes.
            </p>
          </div>
          <Activity className="w-5 h-5 text-gold-400" />
        </div>

        <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
          <MetricCard
            icon={Activity}
            iconColor="text-green-400"
            iconBg="bg-green-500/10"
            label="Requests"
            value={activityWindow?.request_count || 0}
            sublabel={`Last ${Math.max(1, Math.ceil((activityWindow?.observed_seconds || 0) / 60))} minute(s)`}
            compactOnMobile
          />
          <MetricCard
            icon={RefreshCw}
            iconColor="text-blue-400"
            iconBg="bg-blue-500/10"
            label="Request Rate"
            value={`${(activityWindow?.requests_per_minute || 0).toFixed(1)}/min`}
            sublabel="Rolling window"
            compactOnMobile
          />
          <MetricCard
            icon={Gauge}
            iconColor={activityWindow?.p95_latency_ms && activityWindow.p95_latency_ms >= 750 ? 'text-red-400' : 'text-amber-400'}
            iconBg={activityWindow?.p95_latency_ms && activityWindow.p95_latency_ms >= 750 ? 'bg-red-500/10' : 'bg-amber-500/10'}
            label="Recent P95"
            value={formatLatency(activityWindow?.p95_latency_ms || 0)}
            sublabel="Rolling window"
            compactOnMobile
          />
          <MetricCard
            icon={AlertTriangle}
            iconColor={(activityWindow?.error_rate_percent || 0) > 5 ? 'text-red-400' : 'text-gold-400'}
            iconBg={(activityWindow?.error_rate_percent || 0) > 5 ? 'bg-red-500/10' : 'bg-gold-500/10'}
            label="Request Failures"
            value={`${(activityWindow?.error_rate_percent || 0).toFixed(2)}%`}
            sublabel={`${activityWindow?.error_count || 0} in window`}
            compactOnMobile
          />
        </div>
      </GlassNoirCard>

      {/* Latency & Performance */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Latency Percentiles */}
        <GlassNoirCard>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Response Latency</h2>
            <Gauge className="w-5 h-5 text-gold-400" />
          </div>

          <div className="space-y-4">
            {[
              { label: 'Average', value: stats?.http.avg_latency_ms || 0 },
              { label: 'P50 (Median)', value: stats?.http.p50_latency_ms || 0 },
              { label: 'P95', value: stats?.http.p95_latency_ms || 0 },
              { label: 'P99', value: stats?.http.p99_latency_ms || 0 },
            ].map(({ label, value }) => (
              <div key={label}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-400">{label}</span>
                  <span className={`font-medium ${
                    value < 50 ? 'text-green-400' : value < 200 ? 'text-yellow-400' : 'text-red-400'
                  }`}>
                    {formatLatency(value)}
                  </span>
                </div>
                <div className="w-full bg-noir-700 rounded-full h-2">
                  <div 
                    className={`h-2 rounded-full transition-all ${
                      value < 50 ? 'bg-green-500' : value < 200 ? 'bg-yellow-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${Math.min(value / 5, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </GlassNoirCard>

        {/* Request Status Distribution */}
        <GlassNoirCard>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Request Status</h2>
            <Database className="w-5 h-5 text-gold-400" />
          </div>

          <div className="space-y-4">
            {[
              { label: '2xx Success', value: stats?.http.requests_by_status['2xx'] || 0, color: 'bg-green-500', textColor: 'text-green-400' },
              { label: '4xx Client Error', value: stats?.http.requests_by_status['4xx'] || 0, color: 'bg-yellow-500', textColor: 'text-yellow-400' },
              { label: '5xx Server Error', value: stats?.http.requests_by_status['5xx'] || 0, color: 'bg-red-500', textColor: 'text-red-400' },
            ].map(({ label, value, color, textColor }) => {
              const percentage = totalRequests > 0 ? (value / totalRequests) * 100 : 0
              return (
                <div key={label}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-400">{label}</span>
                    <span className={`font-medium ${textColor}`}>
                      {value.toLocaleString()} ({percentage.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="w-full bg-noir-700 rounded-full h-2">
                    <div 
                      className={`h-2 rounded-full transition-all ${color}`}
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </GlassNoirCard>
      </div>

      {/* Business Metrics - Collapsible */}
      <CollapsibleStats
        title="Business"
        summary={
          <InlineStats items={[
            { label: 'Logins', value: stats?.business.logins.success || 0, color: 'text-green-400' },
            { label: 'Failed', value: stats?.business.logins.failure || 0, color: 'text-red-400' },
            { label: 'Orders', value: stats?.business.orders_created || 0 },
          ]} />
        }
      >
        <StatScrollRow
          stats={[
            { label: 'Logins', value: stats?.business.logins.success || 0, icon: <CheckCircle className="w-4 h-4" />, color: 'green' },
            { label: 'Failed', value: stats?.business.logins.failure || 0, icon: <XCircle className="w-4 h-4" />, color: 'red' },
            { label: 'Success', value: `${loginSuccessRate.toFixed(1)}%` },
            { label: 'Orders', value: stats?.business.orders_created || 0 },
            { label: 'Quotes', value: stats?.business.quotes.approved || 0 },
            { label: 'Payments', value: stats?.business.payments.success || 0 },
          ]}
          size="sm"
        />
      </CollapsibleStats>

      {/* Endpoint demand and latency */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      {stats?.http.slowest_endpoints && stats.http.slowest_endpoints.length > 0 && (
        <GlassNoirCard>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-white">Slowest Endpoints</h2>
              <p className="text-xs text-gray-500 mt-1">Prioritize high-volume rows with elevated p95 latency.</p>
            </div>
            <Gauge className="w-5 h-5 text-gold-400" />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-gold-500/20">
                  <th className="pb-2">Endpoint</th>
                  <th className="pb-2 text-right">P95</th>
                  <th className="pb-2 text-right">Average</th>
                  <th className="pb-2 text-right">Requests</th>
                </tr>
              </thead>
              <tbody>
                {stats.http.slowest_endpoints.map((endpoint) => (
                  <tr key={endpoint.path} className="border-b border-gold-500/10">
                    <td className="py-2 font-mono text-gray-300 max-w-[250px] truncate" title={endpoint.path}>{endpoint.path}</td>
                    <td className={`py-2 text-right font-medium ${endpoint.p95_latency_ms < 250 ? 'text-green-400' : endpoint.p95_latency_ms < 750 ? 'text-yellow-400' : 'text-red-400'}`}>
                      {formatLatency(endpoint.p95_latency_ms)}
                    </td>
                    <td className="py-2 text-right text-gray-300">{formatLatency(endpoint.avg_latency_ms)}</td>
                    <td className="py-2 text-right text-white">{endpoint.requests.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassNoirCard>
      )}

      {stats?.http.requests_by_endpoint && stats.http.requests_by_endpoint.length > 0 && (
        <GlassNoirCard>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-white">Highest Request Volume</h2>
              <p className="text-xs text-gray-500 mt-1">Request count since this process started.</p>
            </div>
            <Server className="w-5 h-5 text-gold-400" />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-gold-500/20">
                  <th className="pb-2">Endpoint</th>
                  <th className="pb-2 text-right">Requests</th>
                  <th className="pb-2 text-right">% of Total</th>
                </tr>
              </thead>
              <tbody>
                {stats.http.requests_by_endpoint.slice(0, 10).map((endpoint, i) => {
                  const percentage = totalRequests > 0 ? (endpoint.count / totalRequests) * 100 : 0
                  return (
                    <tr key={i} className="border-b border-gold-500/10">
                      <td className="py-2 font-mono text-gray-300">{endpoint.path}</td>
                      <td className="py-2 text-right text-white">{endpoint.count.toLocaleString()}</td>
                      <td className="py-2 text-right text-gray-400">{percentage.toFixed(1)}%</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </GlassNoirCard>
      )}
      </div>

      {/* System Info - Collapsible */}
      <CollapsibleStats
        title="System"
        summary={
          <InlineStats items={[
            { label: 'Memory', value: formatBytes(stats?.system.process_memory_bytes || 0) },
            { label: 'CPU', value: `${(stats?.system.process_cpu_seconds || 0).toFixed(1)}s` },
            { label: 'Python', value: stats?.system.python_version || 'N/A' },
          ]} />
        }
      >
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div className="bg-white/5 rounded-lg p-3">
            <div className="text-gray-400 text-xs mb-1">Python</div>
            <div className="font-medium text-white">{stats?.system.python_version || 'N/A'}</div>
          </div>
          <div className="bg-white/5 rounded-lg p-3">
            <div className="text-gray-400 text-xs mb-1">Memory</div>
            <div className="font-medium text-white">{formatBytes(stats?.system.process_memory_bytes || 0)}</div>
          </div>
          <div className="bg-white/5 rounded-lg p-3">
            <div className="text-gray-400 text-xs mb-1">CPU Time</div>
            <div className="font-medium text-white">{(stats?.system.process_cpu_seconds || 0).toFixed(2)}s</div>
          </div>
          <div className="bg-white/5 rounded-lg p-3">
            <div className="text-gray-400 text-xs mb-1">GC Collections</div>
            <div className="font-medium text-white">{stats?.system.gc_collections || 0}</div>
          </div>
        </div>
      </CollapsibleStats>
    </div>
  )
}
