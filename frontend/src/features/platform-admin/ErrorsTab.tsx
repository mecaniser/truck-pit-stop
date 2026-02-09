import { useEffect, useState, useCallback } from 'react'
import {
  AlertTriangle, AlertCircle, AlertOctagon, Search,
  RefreshCw, Filter, X, CheckCircle, Clock,
  ChevronLeft, ChevronRight, ExternalLink
} from 'lucide-react'
import api from '../../lib/api'
import { GlassNoirCard } from '../../components/ui/GlassNoirCard'
import { StatScrollRow } from '../../components/ui/MobileStats'

interface ErrorLog {
  id: string
  correlation_id: string | null
  created_at: string
  error_type: string
  error_category: string
  severity: string
  endpoint: string | null
  method: string | null
  status_code: number | null
  user_id: string | null
  tenant_id: string | null
  message: string
  resolved: boolean
  resolved_at: string | null
  resolved_by_id: string | null
  notes: string | null
}

interface ErrorDetail extends ErrorLog {
  stack_trace: string | null
  request_context: Record<string, unknown> | null
}

interface ErrorStats {
  total: number
  unresolved: number
  critical: number
  by_category: Record<string, number>
  by_severity: Record<string, number>
  top_error_types: Array<{ type: string; count: number }>
  top_endpoints: Array<{ endpoint: string; count: number }>
  period: { start: string; end: string }
}

interface ErrorListResponse {
  errors: ErrorLog[]
  total: number
  skip: number
  limit: number
}

const CATEGORIES = ['payment', 'auth', 'validation', 'database', 'external_api', 'unhandled']
const SEVERITIES = ['warning', 'error', 'critical']

export default function ErrorsTab() {
  const [errors, setErrors] = useState<ErrorLog[]>([])
  const [stats, setStats] = useState<ErrorStats | null>(null)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [statsLoading, setStatsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Pagination
  const [page, setPage] = useState(0)
  const [limit] = useState(20)

  // Filters
  const [showFilters, setShowFilters] = useState(false)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string>('')
  const [severity, setSeverity] = useState<string>('')
  const [resolved, setResolved] = useState<string>('')
  const [errorTypes, setErrorTypes] = useState<string[]>([])
  const [selectedType, setSelectedType] = useState<string>('')

  // Detail modal
  const [selectedError, setSelectedError] = useState<ErrorDetail | null>(null)
  const [_detailLoading, setDetailLoading] = useState(false)
  const [resolveNotes, setResolveNotes] = useState('')

  // Fetch error types for filter dropdown
  useEffect(() => {
    api.get('/admin/errors/types')
      .then(res => setErrorTypes(res.data.types || []))
      .catch(() => {})
  }, [])

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      setStatsLoading(true)
      const res = await api.get('/admin/errors/stats')
      setStats(res.data)
    } catch (err) {
      console.error('Failed to load error stats', err)
    } finally {
      setStatsLoading(false)
    }
  }, [])

  // Fetch errors
  const fetchErrors = useCallback(async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams()
      params.append('skip', String(page * limit))
      params.append('limit', String(limit))
      if (search) params.append('search', search)
      if (category) params.append('category', category)
      if (severity) params.append('severity', severity)
      if (resolved) params.append('resolved', resolved)
      if (selectedType) params.append('error_type', selectedType)

      const res = await api.get<ErrorListResponse>(`/admin/errors?${params.toString()}`)
      setErrors(res.data.errors)
      setTotal(res.data.total)
      setError(null)
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      setError(axiosErr.response?.data?.detail || 'Failed to load errors')
    } finally {
      setLoading(false)
    }
  }, [page, limit, search, category, severity, resolved, selectedType])

  useEffect(() => {
    fetchStats()
  }, [fetchStats])

  useEffect(() => {
    fetchErrors()
  }, [fetchErrors])

  // Fetch error detail
  const openErrorDetail = async (errorId: string) => {
    try {
      setDetailLoading(true)
      const res = await api.get<ErrorDetail>(`/admin/errors/${errorId}`)
      setSelectedError(res.data)
      setResolveNotes('')
    } catch (err) {
      console.error('Failed to load error detail', err)
    } finally {
      setDetailLoading(false)
    }
  }

  // Resolve/unresolve error
  const handleResolve = async () => {
    if (!selectedError) return
    try {
      await api.patch(`/admin/errors/${selectedError.id}/resolve`, { notes: resolveNotes || null })
      setSelectedError({ ...selectedError, resolved: true })
      fetchErrors()
      fetchStats()
    } catch (err) {
      console.error('Failed to resolve error', err)
    }
  }

  const handleUnresolve = async () => {
    if (!selectedError) return
    try {
      await api.patch(`/admin/errors/${selectedError.id}/unresolve`)
      setSelectedError({ ...selectedError, resolved: false })
      fetchErrors()
      fetchStats()
    } catch (err) {
      console.error('Failed to unresolve error', err)
    }
  }

  const clearFilters = () => {
    setSearch('')
    setCategory('')
    setSeverity('')
    setResolved('')
    setSelectedType('')
    setPage(0)
  }

  const getSeverityIcon = (sev: string) => {
    switch (sev) {
      case 'critical':
        return <AlertOctagon className="w-4 h-4 text-red-500" />
      case 'error':
        return <AlertCircle className="w-4 h-4 text-orange-500" />
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-yellow-500" />
      default:
        return <AlertCircle className="w-4 h-4 text-gray-500" />
    }
  }

  const getSeverityBadge = (sev: string) => {
    const colors: Record<string, string> = {
      critical: 'bg-red-500/20 text-red-400 border-red-500/30',
      error: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
      warning: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    }
    return colors[sev] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
  }

  const getCategoryBadge = (cat: string) => {
    const colors: Record<string, string> = {
      payment: 'bg-purple-500/20 text-purple-400',
      auth: 'bg-blue-500/20 text-blue-400',
      validation: 'bg-cyan-500/20 text-cyan-400',
      database: 'bg-red-500/20 text-red-400',
      external_api: 'bg-amber-500/20 text-amber-400',
      unhandled: 'bg-gray-500/20 text-gray-400',
    }
    return colors[cat] || 'bg-gray-500/20 text-gray-400'
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleString()
  }

  const totalPages = Math.ceil(total / limit)

  return (
    <div className="space-y-6">
      {/* Stats - Horizontal Scroll */}
      {!statsLoading && stats && (
        <StatScrollRow
          stats={[
            { label: '24h Total', value: stats.total, icon: <AlertCircle className="w-4 h-4" /> },
            { label: 'Unresolved', value: stats.unresolved, icon: <Clock className="w-4 h-4" />, color: 'gold' },
            { label: 'Critical', value: stats.critical, icon: <AlertOctagon className="w-4 h-4" />, color: 'red' },
            { label: 'Resolved', value: `${stats.total > 0 ? Math.round(((stats.total - stats.unresolved) / stats.total) * 100) : 0}%`, icon: <CheckCircle className="w-4 h-4" />, color: 'green' },
          ]}
          size="sm"
        />
      )}

      {/* Category breakdown */}
      {!statsLoading && stats && Object.keys(stats.by_category).length > 0 && (
        <GlassNoirCard padding="sm">
          <h3 className="text-sm font-medium text-gold-400/80 mb-3">Errors by Category (24h)</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.by_category).map(([cat, count]) => (
              <button
                key={cat}
                onClick={() => { setCategory(cat); setPage(0); }}
                className={`px-3 py-1 rounded-full text-sm ${getCategoryBadge(cat)} hover:opacity-80 transition-opacity`}
              >
                {cat}: {count}
              </button>
            ))}
          </div>
        </GlassNoirCard>
      )}

      {/* Filters and Search */}
      <GlassNoirCard padding="sm">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Search */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search by message, type, or correlation ID..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(0); }}
              className="w-full pl-10 pr-4 py-2 bg-black/40 border border-gold-500/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-gold-500"
            />
          </div>

          {/* Filter toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors ${
              showFilters ? 'bg-gold-500/20 border-gold-500 text-gold-400' : 'bg-black/40 border-gold-500/20 text-gray-300 hover:border-gold-500/40'
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
          </button>

          {/* Refresh */}
          <button
            onClick={() => { fetchErrors(); fetchStats(); }}
            className="flex items-center gap-2 px-4 py-2 bg-gold-500/10 border border-gold-500/30 rounded-lg text-gold-400 hover:bg-gold-500/20 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* Expanded filters */}
        {showFilters && (
          <div className="mt-4 pt-4 border-t border-gold-500/20 grid grid-cols-2 md:grid-cols-5 gap-4">
            <select
              value={category}
              onChange={(e) => { setCategory(e.target.value); setPage(0); }}
              className="bg-black/40 border border-gold-500/20 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-gold-500"
            >
              <option value="">All Categories</option>
              {CATEGORIES.map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>

            <select
              value={severity}
              onChange={(e) => { setSeverity(e.target.value); setPage(0); }}
              className="bg-black/40 border border-gold-500/20 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-gold-500"
            >
              <option value="">All Severities</option>
              {SEVERITIES.map(sev => (
                <option key={sev} value={sev}>{sev}</option>
              ))}
            </select>

            <select
              value={resolved}
              onChange={(e) => { setResolved(e.target.value); setPage(0); }}
              className="bg-black/40 border border-gold-500/20 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-gold-500"
            >
              <option value="">All Status</option>
              <option value="false">Unresolved</option>
              <option value="true">Resolved</option>
            </select>

            <select
              value={selectedType}
              onChange={(e) => { setSelectedType(e.target.value); setPage(0); }}
              className="bg-black/40 border border-gold-500/20 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-gold-500"
            >
              <option value="">All Types</option>
              {errorTypes.map(type => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>

            <button
              onClick={clearFilters}
              className="flex items-center justify-center gap-2 px-4 py-2 bg-black/40 border border-gold-500/20 rounded-lg text-gray-300 hover:border-gold-500/40 transition-colors"
            >
              <X className="w-4 h-4" />
              Clear
            </button>
          </div>
        )}
      </GlassNoirCard>

      {/* Error list */}
      {error && (
        <GlassNoirCard className="border-red-500/30">
          <p className="text-red-400">{error}</p>
        </GlassNoirCard>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-8 h-8 text-gold-500 animate-spin" />
        </div>
      ) : errors.length === 0 ? (
        <GlassNoirCard className="text-center py-8">
          <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-4" />
          <p className="text-gray-400">No errors found matching your filters</p>
        </GlassNoirCard>
      ) : (
        <GlassNoirCard padding="sm" className="overflow-hidden">
          <table className="w-full">
            <thead className="bg-gold-500/5">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gold-400/80 uppercase">Severity</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gold-400/80 uppercase">Type</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gold-400/80 uppercase">Category</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gold-400/80 uppercase">Endpoint</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gold-400/80 uppercase">Message</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gold-400/80 uppercase">Time</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gold-400/80 uppercase">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gold-500/10">
              {errors.map((err) => (
                <tr
                  key={err.id}
                  onClick={() => openErrorDetail(err.id)}
                  className="hover:bg-gold-500/5 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {getSeverityIcon(err.severity)}
                      <span className={`text-xs px-2 py-0.5 rounded border ${getSeverityBadge(err.severity)}`}>
                        {err.severity}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-white font-mono">{err.error_type}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${getCategoryBadge(err.error_category)}`}>
                      {err.error_category}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400 font-mono">
                    {err.method && <span className="text-gold-400 mr-1">{err.method}</span>}
                    {err.endpoint ? (err.endpoint.length > 30 ? err.endpoint.slice(0, 30) + '...' : err.endpoint) : '-'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-300 max-w-xs truncate">
                    {err.message.length > 50 ? err.message.slice(0, 50) + '...' : err.message}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400">{formatDate(err.created_at)}</td>
                  <td className="px-4 py-3">
                    {err.resolved ? (
                      <span className="flex items-center gap-1 text-xs text-green-400">
                        <CheckCircle className="w-3 h-3" /> Resolved
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-gold-400">
                        <Clock className="w-3 h-3" /> Open
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          <div className="flex items-center justify-between px-4 py-3 border-t border-gold-500/20">
            <div className="text-sm text-gray-400">
              Showing {page * limit + 1} - {Math.min((page + 1) * limit, total)} of {total}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="p-2 rounded-lg bg-gold-500/10 border border-gold-500/20 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gold-500/20 transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm text-gray-400">
                Page {page + 1} of {totalPages || 1}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="p-2 rounded-lg bg-gold-500/10 border border-gold-500/20 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gold-500/20 transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </GlassNoirCard>
      )}

      {/* Error Detail Modal */}
      {selectedError && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-noir-800 rounded-xl border border-gold-500/20 max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl shadow-gold-500/10">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gold-500/20">
              <div className="flex items-center gap-3">
                {getSeverityIcon(selectedError.severity)}
                <div>
                  <h2 className="text-lg font-semibold text-white">{selectedError.error_type}</h2>
                  <p className="text-sm text-gray-400">{formatDate(selectedError.created_at)}</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedError(null)}
                className="p-2 rounded-lg hover:bg-gold-500/10 text-gray-400 hover:text-gold-400 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Metadata */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <div className="text-xs text-gold-400/80 mb-1">Category</div>
                  <span className={`text-sm px-2 py-0.5 rounded ${getCategoryBadge(selectedError.error_category)}`}>
                    {selectedError.error_category}
                  </span>
                </div>
                <div>
                  <div className="text-xs text-gold-400/80 mb-1">Severity</div>
                  <span className={`text-sm px-2 py-0.5 rounded border ${getSeverityBadge(selectedError.severity)}`}>
                    {selectedError.severity}
                  </span>
                </div>
                <div>
                  <div className="text-xs text-gold-400/80 mb-1">Status Code</div>
                  <span className="text-sm text-white">{selectedError.status_code || 'N/A'}</span>
                </div>
                <div>
                  <div className="text-xs text-gold-400/80 mb-1">Status</div>
                  {selectedError.resolved ? (
                    <span className="flex items-center gap-1 text-sm text-green-400">
                      <CheckCircle className="w-4 h-4" /> Resolved
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-sm text-gold-400">
                      <Clock className="w-4 h-4" /> Open
                    </span>
                  )}
                </div>
              </div>

              {/* Endpoint */}
              {selectedError.endpoint && (
                <div>
                  <div className="text-xs text-gold-400/80 mb-1">Endpoint</div>
                  <code className="text-sm text-gold-400 bg-black/40 px-2 py-1 rounded border border-gold-500/20">
                    {selectedError.method} {selectedError.endpoint}
                  </code>
                </div>
              )}

              {/* Correlation ID */}
              {selectedError.correlation_id && (
                <div>
                  <div className="text-xs text-gold-400/80 mb-1">Correlation ID</div>
                  <div className="flex items-center gap-2">
                    <code className="text-sm text-white bg-black/40 px-2 py-1 rounded border border-gold-500/20">
                      {selectedError.correlation_id}
                    </code>
                    <button
                      onClick={() => {
                        setSearch(selectedError.correlation_id || '')
                        setSelectedError(null)
                      }}
                      className="text-xs text-gold-400 hover:text-gold-300 flex items-center gap-1"
                    >
                      <ExternalLink className="w-3 h-3" /> Find related
                    </button>
                  </div>
                </div>
              )}

              {/* Message */}
              <div>
                <div className="text-xs text-gold-400/80 mb-1">Message</div>
                <div className="text-sm text-white bg-black/40 p-3 rounded-lg border border-gold-500/10 whitespace-pre-wrap">
                  {selectedError.message}
                </div>
              </div>

              {/* Stack Trace */}
              {selectedError.stack_trace && (
                <div>
                  <div className="text-xs text-gold-400/80 mb-1">Stack Trace</div>
                  <pre className="text-xs text-gray-300 bg-noir-900 p-3 rounded-lg border border-gold-500/10 overflow-x-auto max-h-64">
                    {selectedError.stack_trace}
                  </pre>
                </div>
              )}

              {/* Request Context */}
              {selectedError.request_context && Object.keys(selectedError.request_context).length > 0 && (
                <div>
                  <div className="text-xs text-gold-400/80 mb-1">Request Context</div>
                  <pre className="text-xs text-gray-300 bg-noir-900 p-3 rounded-lg border border-gold-500/10 overflow-x-auto max-h-48">
                    {JSON.stringify(selectedError.request_context, null, 2)}
                  </pre>
                </div>
              )}

              {/* Resolution notes */}
              {selectedError.notes && (
                <div>
                  <div className="text-xs text-gold-400/80 mb-1">Resolution Notes</div>
                  <div className="text-sm text-gray-300 bg-black/40 p-3 rounded-lg border border-gold-500/10">
                    {selectedError.notes}
                  </div>
                </div>
              )}

              {/* Resolve form */}
              {!selectedError.resolved && (
                <div className="border-t border-gold-500/20 pt-4">
                  <div className="text-xs text-gold-400/80 mb-2">Mark as Resolved</div>
                  <textarea
                    value={resolveNotes}
                    onChange={(e) => setResolveNotes(e.target.value)}
                    placeholder="Add resolution notes (optional)..."
                    className="w-full px-3 py-2 bg-black/40 border border-gold-500/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-gold-500 resize-none"
                    rows={2}
                  />
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gold-500/20">
              <button
                onClick={() => setSelectedError(null)}
                className="px-4 py-2 bg-gold-500/10 border border-gold-500/30 text-gold-400 rounded-lg hover:bg-gold-500/20 transition-colors"
              >
                Close
              </button>
              {selectedError.resolved ? (
                <button
                  onClick={handleUnresolve}
                  className="px-4 py-2 bg-gold-500 text-black font-semibold rounded-lg hover:bg-gold-400 transition-colors"
                >
                  Reopen
                </button>
              ) : (
                <button
                  onClick={handleResolve}
                  className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
                >
                  Mark Resolved
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
