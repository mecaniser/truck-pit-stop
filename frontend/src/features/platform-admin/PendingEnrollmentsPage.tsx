import { useState } from 'react'
import { Spinner } from '@/components/ui'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  Building2, CheckCircle, XCircle, User, Phone, Mail, MapPin, 
  Calendar, FileText, Globe, Clock, AlertTriangle, UserCheck 
} from 'lucide-react'
import api from '../../lib/api'
import toast from 'react-hot-toast'
import { GlassNoirCard, GlassNoirHeader, GlassNoirBadge } from '../../components/ui/GlassNoirCard'
import { SegmentedControl } from '../../components/ui/MobileStats'

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
        <Spinner size="xl" />
      </div>
    )
  }

  if (error) {
    return (
      <GlassNoirCard className="border-red-500/30">
        <p className="text-red-400">Failed to load enrollments</p>
      </GlassNoirCard>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <GlassNoirHeader
        title="Shop Enrollments"
        subtitle="Review and approve new shop applications"
        icon={<UserCheck className="w-6 h-6 text-gold-400" />}
      />

      {/* Filter - Segmented Control */}
      <SegmentedControl
        value={statusFilter}
        onChange={setStatusFilter}
        options={[
          { id: 'pending', label: 'Pending', shortLabel: 'Pending', count: stats?.pending || 0, icon: <Clock className="w-4 h-4" />, color: 'gold' },
          { id: 'approved', label: 'Approved', shortLabel: 'OK', count: stats?.approved || 0, icon: <CheckCircle className="w-4 h-4" />, color: 'green' },
          { id: 'rejected', label: 'Rejected', shortLabel: 'No', count: stats?.rejected || 0, icon: <XCircle className="w-4 h-4" />, color: 'red' },
          { id: '', label: 'All', shortLabel: 'All', count: stats?.total || 0, color: 'default' },
        ]}
      />

      {/* Enrollments List */}
      <div className="space-y-4">
        {enrollments.length === 0 ? (
          <GlassNoirCard className="text-center py-12">
            <Building2 className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">
              {statusFilter === 'pending' 
                ? 'No pending enrollments' 
                : `No ${statusFilter || ''} enrollments found`}
            </p>
          </GlassNoirCard>
        ) : (
          enrollments.map((enrollment) => (
            <GlassNoirCard key={enrollment.id} hover>
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`p-3 rounded-lg border ${
                    enrollment.enrollment_status === 'pending' 
                      ? 'bg-gold-500/10 border-gold-500/20' 
                      : enrollment.enrollment_status === 'approved'
                      ? 'bg-green-500/10 border-green-500/20'
                      : 'bg-red-500/10 border-red-500/20'
                  }`}>
                    <Building2 className={`w-6 h-6 ${
                      enrollment.enrollment_status === 'pending' 
                        ? 'text-gold-400' 
                        : enrollment.enrollment_status === 'approved'
                        ? 'text-green-400'
                        : 'text-red-400'
                    }`} />
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold text-white">{enrollment.garage_name}</h3>
                    <p className="text-sm text-gray-400">dieselbridge.com/{enrollment.slug}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {enrollment.enrollment_status === 'pending' && (
                    <GlassNoirBadge variant="gold">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        Pending Review
                      </span>
                    </GlassNoirBadge>
                  )}
                  {enrollment.enrollment_status === 'approved' && (
                    <GlassNoirBadge variant="success">
                      <span className="flex items-center gap-1">
                        <CheckCircle className="w-3 h-3" />
                        Approved
                      </span>
                    </GlassNoirBadge>
                  )}
                  {enrollment.enrollment_status === 'rejected' && (
                    <GlassNoirBadge variant="error">
                      <span className="flex items-center gap-1">
                        <XCircle className="w-3 h-3" />
                        Rejected
                      </span>
                    </GlassNoirBadge>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Shop Info */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-gold-400/80 uppercase tracking-wide">Shop Info</h4>
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
                      <a href={`mailto:${enrollment.email}`} className="text-gold-400 hover:text-gold-300">
                        {enrollment.email}
                      </a>
                    </div>
                  )}
                  {enrollment.website && (
                    <div className="flex items-center gap-2 text-sm">
                      <Globe className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <a href={enrollment.website} target="_blank" rel="noopener noreferrer" className="text-gold-400 hover:text-gold-300">
                        {enrollment.website}
                      </a>
                    </div>
                  )}
                </div>

                {/* Business Details */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-gold-400/80 uppercase tracking-wide">Business Details</h4>
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
                  <h4 className="text-sm font-semibold text-gold-400/80 uppercase tracking-wide">Owner</h4>
                  {enrollment.owner_name && (
                    <div className="flex items-center gap-2 text-sm">
                      <User className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">{enrollment.owner_name}</span>
                    </div>
                  )}
                  {enrollment.owner_email && (
                    <div className="flex items-center gap-2 text-sm">
                      <Mail className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <a href={`mailto:${enrollment.owner_email}`} className="text-gold-400 hover:text-gold-300">
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
                <div className="mt-4 p-4 bg-noir-800/50 border border-gold-500/20 rounded-lg">
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Reason for rejection <span className="text-red-400">*</span>
                  </label>
                  <textarea
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Please provide a reason for rejecting this application..."
                    className="w-full px-3 py-2 bg-black/40 border border-gold-500/20 rounded-lg text-white placeholder-gray-500 focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                    rows={3}
                  />
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={() => {
                        setRejectingId(null)
                        setRejectReason('')
                      }}
                      className="px-4 py-2 bg-gold-500/10 hover:bg-gold-500/20 text-gold-400 border border-gold-500/30 rounded-lg text-sm transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => handleReject(enrollment.id)}
                      disabled={rejectMutation.isPending}
                      className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50 flex items-center gap-2"
                    >
                      {rejectMutation.isPending && <Spinner size="xs" />}
                      Confirm Rejection
                    </button>
                  </div>
                </div>
              )}

              {/* Actions */}
              {enrollment.enrollment_status === 'pending' && rejectingId !== enrollment.id && (
                <div className="mt-6 pt-4 border-t border-gold-500/10 flex gap-2">
                  <button
                    onClick={() => approveMutation.mutate(enrollment.id)}
                    disabled={approveMutation.isPending}
                    className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50 flex items-center gap-2"
                  >
                    {approveMutation.isPending && <Spinner size="xs" />}
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
                <div className="mt-4 pt-4 border-t border-gold-500/10">
                  <p className="text-sm text-gray-400">
                    Approved on {formatDate(enrollment.approved_at)}
                  </p>
                </div>
              )}
            </GlassNoirCard>
          ))
        )}
      </div>
    </div>
  )
}
