import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  Building2, CheckCircle, XCircle, User, Phone, Mail, MapPin, 
  Calendar, FileText, Globe, Clock, AlertTriangle, Loader2 
} from 'lucide-react'
import api from '../../lib/api'
import toast from 'react-hot-toast'

interface Enrollment {
  id: string
  garage_name: string
  slug: string
  address: string | null
  phone: string | null
  email: string | null
  website: string | null
  business_license: string | null
  ein: string | null
  enrollment_status: string
  applied_at: string | null
  approved_at: string | null
  rejection_reason: string | null
  owner_id: string | null
  owner_email: string | null
  owner_name: string | null
  owner_phone: string | null
}

interface EnrollmentStats {
  pending: number
  approved: number
  rejected: number
  total: number
}

export default function PendingEnrollmentsPage() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>('pending')
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  // Fetch enrollments
  const { data: enrollments = [], isLoading, error } = useQuery<Enrollment[]>({
    queryKey: ['enrollments', statusFilter],
    queryFn: async () => {
      const params = statusFilter ? { status_filter: statusFilter } : {}
      const response = await api.get('/admin/pending-enrollments', { params })
      return response.data
    },
  })

  // Fetch stats
  const { data: stats } = useQuery<EnrollmentStats>({
    queryKey: ['enrollment-stats'],
    queryFn: async () => {
      const response = await api.get('/admin/enrollment-stats')
      return response.data
    },
  })

  // Approve mutation
  const approveMutation = useMutation({
    mutationFn: async (tenantId: string) => {
      const response = await api.post(`/admin/approve-enrollment/${tenantId}`)
      return response.data
    },
    onSuccess: () => {
      toast.success('Enrollment approved successfully')
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      queryClient.invalidateQueries({ queryKey: ['enrollment-stats'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to approve enrollment')
    },
  })

  // Reject mutation
  const rejectMutation = useMutation({
    mutationFn: async ({ tenantId, reason }: { tenantId: string; reason: string }) => {
      const response = await api.post(`/admin/reject-enrollment/${tenantId}`, { reason })
      return response.data
    },
    onSuccess: () => {
      toast.success('Enrollment rejected')
      setRejectingId(null)
      setRejectReason('')
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      queryClient.invalidateQueries({ queryKey: ['enrollment-stats'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to reject enrollment')
    },
  })

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A'
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const handleReject = (tenantId: string) => {
    if (!rejectReason.trim()) {
      toast.error('Please provide a reason for rejection')
      return
    }
    rejectMutation.mutate({ tenantId, reason: rejectReason })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-6">
        <p className="text-red-400">Failed to load enrollments</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Garage Enrollments</h1>
          <p className="text-gray-400">Review and approve new garage applications</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <button
          onClick={() => setStatusFilter('pending')}
          className={`bg-gray-800/50 border rounded-lg p-4 text-left transition-colors ${
            statusFilter === 'pending' ? 'border-amber-500' : 'border-gray-700/50 hover:border-gray-600'
          }`}
        >
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <Clock className="w-4 h-4" />
            Pending
          </div>
          <div className="text-2xl font-bold text-amber-400 mt-1">{stats?.pending || 0}</div>
        </button>
        <button
          onClick={() => setStatusFilter('approved')}
          className={`bg-gray-800/50 border rounded-lg p-4 text-left transition-colors ${
            statusFilter === 'approved' ? 'border-green-500' : 'border-gray-700/50 hover:border-gray-600'
          }`}
        >
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <CheckCircle className="w-4 h-4" />
            Approved
          </div>
          <div className="text-2xl font-bold text-green-400 mt-1">{stats?.approved || 0}</div>
        </button>
        <button
          onClick={() => setStatusFilter('rejected')}
          className={`bg-gray-800/50 border rounded-lg p-4 text-left transition-colors ${
            statusFilter === 'rejected' ? 'border-red-500' : 'border-gray-700/50 hover:border-gray-600'
          }`}
        >
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <XCircle className="w-4 h-4" />
            Rejected
          </div>
          <div className="text-2xl font-bold text-red-400 mt-1">{stats?.rejected || 0}</div>
        </button>
        <button
          onClick={() => setStatusFilter('')}
          className={`bg-gray-800/50 border rounded-lg p-4 text-left transition-colors ${
            statusFilter === '' ? 'border-blue-500' : 'border-gray-700/50 hover:border-gray-600'
          }`}
        >
          <div className="text-gray-400 text-sm">Total</div>
          <div className="text-2xl font-bold text-white mt-1">{stats?.total || 0}</div>
        </button>
      </div>

      {/* Enrollments List */}
      <div className="space-y-4">
        {enrollments.length === 0 ? (
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-12 text-center">
            <Building2 className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">
              {statusFilter === 'pending' 
                ? 'No pending enrollments' 
                : `No ${statusFilter || ''} enrollments found`}
            </p>
          </div>
        ) : (
          enrollments.map((enrollment) => (
            <div
              key={enrollment.id}
              className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6 hover:border-gray-600/50 transition-colors"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`p-3 rounded-lg ${
                    enrollment.enrollment_status === 'pending' 
                      ? 'bg-amber-500/10' 
                      : enrollment.enrollment_status === 'approved'
                      ? 'bg-green-500/10'
                      : 'bg-red-500/10'
                  }`}>
                    <Building2 className={`w-6 h-6 ${
                      enrollment.enrollment_status === 'pending' 
                        ? 'text-amber-400' 
                        : enrollment.enrollment_status === 'approved'
                        ? 'text-green-400'
                        : 'text-red-400'
                    }`} />
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold text-white">{enrollment.garage_name}</h3>
                    <p className="text-sm text-gray-400">truckpitstop.com/{enrollment.slug}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {enrollment.enrollment_status === 'pending' && (
                    <span className="flex items-center gap-1 px-3 py-1 bg-amber-500/10 text-amber-400 rounded-full text-sm">
                      <Clock className="w-4 h-4" />
                      Pending Review
                    </span>
                  )}
                  {enrollment.enrollment_status === 'approved' && (
                    <span className="flex items-center gap-1 px-3 py-1 bg-green-500/10 text-green-400 rounded-full text-sm">
                      <CheckCircle className="w-4 h-4" />
                      Approved
                    </span>
                  )}
                  {enrollment.enrollment_status === 'rejected' && (
                    <span className="flex items-center gap-1 px-3 py-1 bg-red-500/10 text-red-400 rounded-full text-sm">
                      <XCircle className="w-4 h-4" />
                      Rejected
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Garage Info */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Garage Info</h4>
                  {enrollment.address && (
                    <div className="flex items-start gap-2 text-sm">
                      <MapPin className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-300">{enrollment.address}</span>
                    </div>
                  )}
                  {enrollment.phone && (
                    <div className="flex items-center gap-2 text-sm">
                      <Phone className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">{enrollment.phone}</span>
                    </div>
                  )}
                  {enrollment.email && (
                    <div className="flex items-center gap-2 text-sm">
                      <Mail className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <a href={`mailto:${enrollment.email}`} className="text-blue-400 hover:text-blue-300">
                        {enrollment.email}
                      </a>
                    </div>
                  )}
                  {enrollment.website && (
                    <div className="flex items-center gap-2 text-sm">
                      <Globe className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <a href={enrollment.website} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300">
                        {enrollment.website}
                      </a>
                    </div>
                  )}
                </div>

                {/* Business Details */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Business Details</h4>
                  {enrollment.business_license ? (
                    <div className="flex items-center gap-2 text-sm">
                      <FileText className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">License: {enrollment.business_license}</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <FileText className="w-4 h-4 flex-shrink-0" />
                      <span>No license provided</span>
                    </div>
                  )}
                  {enrollment.ein ? (
                    <div className="flex items-center gap-2 text-sm">
                      <FileText className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">EIN: {enrollment.ein}</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <FileText className="w-4 h-4 flex-shrink-0" />
                      <span>No EIN provided</span>
                    </div>
                  )}
                  <div className="flex items-center gap-2 text-sm">
                    <Calendar className="w-4 h-4 text-gray-500 flex-shrink-0" />
                    <span className="text-gray-400">Applied: {formatDate(enrollment.applied_at)}</span>
                  </div>
                </div>

                {/* Owner Info */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Owner</h4>
                  {enrollment.owner_name && (
                    <div className="flex items-center gap-2 text-sm">
                      <User className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">{enrollment.owner_name}</span>
                    </div>
                  )}
                  {enrollment.owner_email && (
                    <div className="flex items-center gap-2 text-sm">
                      <Mail className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <a href={`mailto:${enrollment.owner_email}`} className="text-blue-400 hover:text-blue-300">
                        {enrollment.owner_email}
                      </a>
                    </div>
                  )}
                  {enrollment.owner_phone && (
                    <div className="flex items-center gap-2 text-sm">
                      <Phone className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">{enrollment.owner_phone}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Rejection Reason (if rejected) */}
              {enrollment.enrollment_status === 'rejected' && enrollment.rejection_reason && (
                <div className="mt-4 p-3 bg-red-900/20 border border-red-500/30 rounded-lg">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-red-400">Rejection Reason:</p>
                      <p className="text-sm text-gray-300 mt-1">{enrollment.rejection_reason}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Rejection Form */}
              {rejectingId === enrollment.id && (
                <div className="mt-4 p-4 bg-gray-900/50 border border-gray-700 rounded-lg">
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Reason for rejection <span className="text-red-400">*</span>
                  </label>
                  <textarea
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Please provide a reason for rejecting this application..."
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:ring-2 focus:ring-red-500 focus:border-red-500"
                    rows={3}
                  />
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={() => {
                        setRejectingId(null)
                        setRejectReason('')
                      }}
                      className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => handleReject(enrollment.id)}
                      disabled={rejectMutation.isPending}
                      className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50 flex items-center gap-2"
                    >
                      {rejectMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                      Confirm Rejection
                    </button>
                  </div>
                </div>
              )}

              {/* Actions */}
              {enrollment.enrollment_status === 'pending' && rejectingId !== enrollment.id && (
                <div className="mt-6 pt-4 border-t border-gray-700/50 flex gap-2">
                  <button
                    onClick={() => approveMutation.mutate(enrollment.id)}
                    disabled={approveMutation.isPending}
                    className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50 flex items-center gap-2"
                  >
                    {approveMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                    <CheckCircle className="w-4 h-4" />
                    Approve
                  </button>
                  <button
                    onClick={() => setRejectingId(enrollment.id)}
                    className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm transition-colors flex items-center gap-2"
                  >
                    <XCircle className="w-4 h-4" />
                    Reject
                  </button>
                </div>
              )}

              {/* Approved info */}
              {enrollment.enrollment_status === 'approved' && enrollment.approved_at && (
                <div className="mt-4 pt-4 border-t border-gray-700/50">
                  <p className="text-sm text-gray-400">
                    Approved on {formatDate(enrollment.approved_at)}
                  </p>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
