import { useEffect, useState, useCallback } from 'react'
import { Spinner } from '@/components/ui'
import { 
  Activity, Server, Database, Zap, 
  Clock, AlertTriangle, RefreshCw, Users,
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
    avg_latency_ms: number
    p50_latency_ms: number
    p95_latency_ms: number
    p99_latency_ms: number
    requests_in_progress: number
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
}

function getHealthReadyUrl() {
  const apiUrl = (import.meta.env.VITE_API_URL || '/api/v1').replace(/\/+$/, '')
  const backendBase = apiUrl.replace(/\/api\/v1$/, '')
  return backendBase ? `${backendBase}/health/ready` : '/health/ready'
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

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(fetchData, 30000)
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
  const errorRate = totalRequests > 0 
    ? ((stats?.http.requests_by_status['4xx'] || 0) + (stats?.http.requests_by_status['5xx'] || 0)) / totalRequests * 100
    : 0

  const loginSuccessRate = (stats?.business.logins.success || 0) + (stats?.business.logins.failure || 0) > 0
    ? (stats?.business.logins.success || 0) / ((stats?.business.logins.success || 0) + (stats?.business.logins.failure || 0)) * 100
    : 100

  return (
    <div className="space-y-6">
      {/* Refresh Controls */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-400">
          Last updated: {lastRefresh.toLocaleTimeString()}
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-gold-500/30 bg-black/40 text-gold-500 focus:ring-gold-500"
            />
            Auto-refresh (30s)
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
      <GlassNoirCard>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">System Health</h2>
          <Server className="w-5 h-5 text-gold-400" />
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* API Status */}
          <div className="space-y-3">
            <StatusIndicator
              status={health?.status === 'healthy' || health?.status === 'ready' ? 'healthy' : 'error'}
              label="API Status"
              sublabel={health?.environment || 'unknown'}
            />
            <div className="text-xs text-gray-500">
              Version: {health?.version || 'unknown'}
            </div>
          </div>

          {/* Database */}
          <div className="space-y-3">
            <StatusIndicator
              status={health?.checks.database ? getHealthStatus(health.checks.database) : 'unknown'}
              label="Database"
              sublabel={health?.checks.database ? `${health.checks.database.latency_ms.toFixed(1)}ms` : 'N/A'}
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
          <div className="space-y-3">
            <StatusIndicator
              status={health?.checks.redis ? getHealthStatus(health.checks.redis) : 'unknown'}
              label="Redis Cache"
              sublabel={health?.checks.redis ? `${health.checks.redis.latency_ms.toFixed(1)}ms` : 'N/A'}
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
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-gold-500/10 rounded-lg border border-gold-500/20">
                <Clock className="w-5 h-5 text-gold-400" />
              </div>
              <div>
                <div className="font-medium text-gold-400">Uptime</div>
                <div className="text-lg font-bold text-white">
                  {formatUptime(health?.uptime_seconds || 0)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </GlassNoirCard>

      {/* Real-time Metrics Panel */}
      <GlassNoirCard>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Real-time Metrics</h2>
          <Activity className="w-5 h-5 text-gold-400" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard
            icon={Zap}
            iconColor="text-yellow-400"
            iconBg="bg-yellow-500/10"
            label="In Progress"
            value={stats?.http.requests_in_progress || 0}
            sublabel="Active requests"
          />
          <MetricCard
            icon={Activity}
            iconColor="text-green-400"
            iconBg="bg-green-500/10"
            label="Total Requests"
            value={totalRequests.toLocaleString()}
            sublabel="Since startup"
          />
          <MetricCard
            icon={AlertTriangle}
            iconColor={errorRate > 5 ? 'text-red-400' : 'text-amber-400'}
            iconBg={errorRate > 5 ? 'bg-red-500/10' : 'bg-amber-500/10'}
            label="Error Rate"
            value={`${errorRate.toFixed(2)}%`}
            sublabel={`${(stats?.http.requests_by_status['4xx'] || 0) + (stats?.http.requests_by_status['5xx'] || 0)} errors`}
          />
          <MetricCard
            icon={Users}
            iconColor="text-gold-400"
            iconBg="bg-gold-500/10"
            label="Active Users"
            value={stats?.system.active_users || 0}
            sublabel="Approximation"
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

      {/* Top Endpoints */}
      {stats?.http.requests_by_endpoint && stats.http.requests_by_endpoint.length > 0 && (
        <GlassNoirCard>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Top Endpoints</h2>
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
