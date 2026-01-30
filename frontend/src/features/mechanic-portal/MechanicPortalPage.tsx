import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import { 
  Wrench, 
  Truck, 
  Clock, 
  CheckCircle, 
  PlayCircle, 
  AlertCircle,
  ChevronRight,
  ArrowLeft,
  Loader2,
  History,
  ClipboardList
} from 'lucide-react'

interface MechanicJob {
  id: string
  order_number: string
  status: string
  vehicle_info: string
  description: string | null
  services_count: number
  updated_at: string
}

interface ServiceItem {
  name: string
  description: string | null
  base_price: string | null
}

interface MechanicJobDetail {
  id: string
  order_number: string
  status: string
  description: string | null
  vehicle_year: number | null
  vehicle_make: string
  vehicle_model: string
  vehicle_vin: string | null
  vehicle_license_plate: string | null
  vehicle_mileage: number | null
  services: ServiceItem[]
  created_at: string
  updated_at: string
}

interface WorkHistoryItem {
  id: string
  order_number: string
  status: string
  vehicle_info: string
  completed_at: string
  services_count: number
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  assigned: { label: 'Assigned', color: 'text-amber-600', bg: 'bg-amber-100', icon: AlertCircle },
  acknowledged: { label: 'Acknowledged', color: 'text-blue-600', bg: 'bg-blue-100', icon: CheckCircle },
  in_progress: { label: 'In Progress', color: 'text-purple-600', bg: 'bg-purple-100', icon: PlayCircle },
  pending_review: { label: 'Pending Review', color: 'text-orange-600', bg: 'bg-orange-100', icon: Clock },
  completed: { label: 'Completed', color: 'text-green-600', bg: 'bg-green-100', icon: CheckCircle },
  invoiced: { label: 'Invoiced', color: 'text-indigo-600', bg: 'bg-indigo-100', icon: CheckCircle },
  paid: { label: 'Paid', color: 'text-emerald-600', bg: 'bg-emerald-100', icon: CheckCircle },
}

type TabType = 'active' | 'history'

export default function MechanicPortalPage() {
  const { user, logout } = useAuthStore()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<TabType>('active')
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null)

  // Active jobs query
  const { data: jobs, isLoading } = useQuery<MechanicJob[]>({
    queryKey: ['mechanic-jobs'],
    queryFn: async () => {
      const response = await api.get('/mechanics/my-jobs')
      return response.data
    },
  })

  // Work history query
  const { data: history, isLoading: historyLoading } = useQuery<WorkHistoryItem[]>({
    queryKey: ['mechanic-history'],
    queryFn: async () => {
      const response = await api.get('/mechanics/my-history')
      return response.data
    },
    enabled: activeTab === 'history',
  })

  // Job detail query (for both active and history)
  const detailId = selectedJobId || selectedHistoryId
  const { data: jobDetail } = useQuery<MechanicJobDetail>({
    queryKey: ['mechanic-job-detail', detailId],
    queryFn: async () => {
      const response = await api.get(`/mechanics/my-jobs/${detailId}`)
      return response.data
    },
    enabled: !!detailId,
  })

  const acknowledgeMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.post(`/repair-orders/${orderId}/acknowledge`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-job-detail', selectedJobId] })
      toast.success('Job acknowledged')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to acknowledge job')
    },
  })

  const startWorkMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.post(`/repair-orders/${orderId}/start-work`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-job-detail', selectedJobId] })
      toast.success('Work started - Customer notified')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to start work')
    },
  })

  const completeWorkMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.post(`/repair-orders/${orderId}/complete-work`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-history'] })
      setSelectedJobId(null)
      toast.success('Work completed - Manager notified for review')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to complete work')
    },
  })

  const handleLogout = async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      // ignore
    }
    logout()
  }

  const handleBack = () => {
    setSelectedJobId(null)
    setSelectedHistoryId(null)
  }

  // Job Detail View (shared for active and history)
  if (detailId && jobDetail) {
    const config = STATUS_CONFIG[jobDetail.status] || STATUS_CONFIG.assigned
    const StatusIcon = config.icon
    const isHistoryView = !!selectedHistoryId

    return (
      <div className="min-h-screen bg-gray-900">
        {/* Header */}
        <header className="bg-gray-800 border-b border-gray-700 px-4 py-4">
          <div className="max-w-2xl mx-auto flex items-center gap-4">
            <button
              onClick={handleBack}
              className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-gray-400" />
            </button>
            <div className="flex-1">
              <h1 className="text-lg font-semibold text-white">{jobDetail.order_number}</h1>
              <div className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${config.bg} ${config.color}`}>
                <StatusIcon className="w-3 h-3" />
                {config.label}
              </div>
            </div>
          </div>
        </header>

        <main className="max-w-2xl mx-auto p-4 space-y-4">
          {/* Vehicle Info */}
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-cyan-500/20 rounded-lg flex items-center justify-center">
                <Truck className="w-5 h-5 text-cyan-400" />
              </div>
              <div>
                <h2 className="text-white font-semibold">
                  {jobDetail.vehicle_year} {jobDetail.vehicle_make} {jobDetail.vehicle_model}
                </h2>
                <p className="text-sm text-gray-400">Vehicle Information</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {jobDetail.vehicle_vin && (
                <div>
                  <span className="text-gray-500">VIN</span>
                  <p className="text-white font-mono text-xs">{jobDetail.vehicle_vin}</p>
                </div>
              )}
              {jobDetail.vehicle_license_plate && (
                <div>
                  <span className="text-gray-500">License Plate</span>
                  <p className="text-white">{jobDetail.vehicle_license_plate}</p>
                </div>
              )}
              {jobDetail.vehicle_mileage && (
                <div>
                  <span className="text-gray-500">Mileage</span>
                  <p className="text-white">{jobDetail.vehicle_mileage.toLocaleString()} mi</p>
                </div>
              )}
            </div>
          </div>

          {/* Description */}
          {jobDetail.description && (
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <h3 className="text-sm font-medium text-gray-400 mb-2">Description</h3>
              <p className="text-white">{jobDetail.description}</p>
            </div>
          )}

          {/* Services */}
          {jobDetail.services.length > 0 && (
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <h3 className="text-sm font-medium text-gray-400 mb-3">
                {isHistoryView ? 'Services Performed' : 'Services to Perform'}
              </h3>
              <div className="space-y-2">
                {jobDetail.services.map((svc, idx) => (
                  <div key={idx} className="flex items-center gap-3 p-3 bg-gray-700/50 rounded-lg">
                    <Wrench className="w-4 h-4 text-amber-400 shrink-0" />
                    <div className="flex-1">
                      <p className="text-white font-medium">{svc.name}</p>
                      {svc.description && (
                        <p className="text-sm text-gray-400">{svc.description}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions - only for active jobs */}
          {!isHistoryView && (
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <h3 className="text-sm font-medium text-gray-400 mb-3">Actions</h3>
              
              {jobDetail.status === 'assigned' && (
                <button
                  onClick={() => acknowledgeMutation.mutate(jobDetail.id)}
                  disabled={acknowledgeMutation.isPending}
                  className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  {acknowledgeMutation.isPending ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <CheckCircle className="w-5 h-5" />
                  )}
                  Acknowledge Job
                </button>
              )}

              {jobDetail.status === 'acknowledged' && (
                <button
                  onClick={() => startWorkMutation.mutate(jobDetail.id)}
                  disabled={startWorkMutation.isPending}
                  className="w-full py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  {startWorkMutation.isPending ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <PlayCircle className="w-5 h-5" />
                  )}
                  Start Work
                </button>
              )}

              {jobDetail.status === 'in_progress' && (
                <button
                  onClick={() => completeWorkMutation.mutate(jobDetail.id)}
                  disabled={completeWorkMutation.isPending}
                  className="w-full py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  {completeWorkMutation.isPending ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <CheckCircle className="w-5 h-5" />
                  )}
                  Mark as Complete
                </button>
              )}

              {jobDetail.status === 'pending_review' && (
                <div className="text-center py-4">
                  <Clock className="w-8 h-8 text-orange-400 mx-auto mb-2" />
                  <p className="text-gray-400">Waiting for manager review</p>
                </div>
              )}
            </div>
          )}

          {/* Timestamps for history */}
          {isHistoryView && (
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <h3 className="text-sm font-medium text-gray-400 mb-3">Timeline</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Created</span>
                  <span className="text-white">{format(new Date(jobDetail.created_at), 'MMM d, yyyy h:mm a')}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Last Updated</span>
                  <span className="text-white">{format(new Date(jobDetail.updated_at), 'MMM d, yyyy h:mm a')}</span>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    )
  }

  // Main List View with Tabs
  return (
    <div className="min-h-screen bg-gray-900">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-4 py-4">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-amber-500">🔧 Mechanic Portal</h1>
            <p className="text-sm text-gray-400">Hi, {user?.first_name}</p>
          </div>
          <button
            onClick={handleLogout}
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
          >
            Logout
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-2xl mx-auto flex">
          <button
            onClick={() => setActiveTab('active')}
            className={`flex-1 py-3 px-4 text-sm font-medium flex items-center justify-center gap-2 border-b-2 transition-colors ${
              activeTab === 'active'
                ? 'border-amber-500 text-amber-500'
                : 'border-transparent text-gray-400 hover:text-white'
            }`}
          >
            <ClipboardList className="w-4 h-4" />
            Active Jobs
            {jobs && jobs.length > 0 && (
              <span className="ml-1 px-1.5 py-0.5 bg-amber-500/20 text-amber-400 text-xs rounded-full">
                {jobs.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`flex-1 py-3 px-4 text-sm font-medium flex items-center justify-center gap-2 border-b-2 transition-colors ${
              activeTab === 'history'
                ? 'border-amber-500 text-amber-500'
                : 'border-transparent text-gray-400 hover:text-white'
            }`}
          >
            <History className="w-4 h-4" />
            Work History
          </button>
        </div>
      </div>

      <main className="max-w-2xl mx-auto p-4">
        {/* Active Jobs Tab */}
        {activeTab === 'active' && (
          <>
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
              </div>
            ) : jobs && jobs.length > 0 ? (
              <div className="space-y-3">
                {jobs.map((job) => {
                  const config = STATUS_CONFIG[job.status] || STATUS_CONFIG.assigned
                  const StatusIcon = config.icon
                  
                  return (
                    <button
                      key={job.id}
                      onClick={() => setSelectedJobId(job.id)}
                      className="w-full bg-gray-800 rounded-xl p-4 border border-gray-700 hover:border-amber-500/50 transition-colors text-left"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-mono text-sm text-gray-400">{job.order_number}</span>
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.bg} ${config.color}`}>
                              <StatusIcon className="w-3 h-3" />
                              {config.label}
                            </span>
                          </div>
                          <p className="text-white font-medium">{job.vehicle_info}</p>
                          {job.description && (
                            <p className="text-sm text-gray-400 truncate mt-1">{job.description}</p>
                          )}
                          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                            <span>{job.services_count} service{job.services_count !== 1 ? 's' : ''}</span>
                            <span>Updated {format(new Date(job.updated_at), 'MMM d, h:mm a')}</span>
                          </div>
                        </div>
                        <ChevronRight className="w-5 h-5 text-gray-500 shrink-0" />
                      </div>
                    </button>
                  )
                })}
              </div>
            ) : (
              <div className="text-center py-12">
                <Wrench className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                <p className="text-gray-400">No active jobs</p>
                <p className="text-sm text-gray-500 mt-1">Check back later for new assignments</p>
              </div>
            )}
          </>
        )}

        {/* Work History Tab */}
        {activeTab === 'history' && (
          <>
            {historyLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
              </div>
            ) : history && history.length > 0 ? (
              <div className="space-y-3">
                {history.map((item) => {
                  const config = STATUS_CONFIG[item.status] || STATUS_CONFIG.completed
                  const StatusIcon = config.icon
                  
                  return (
                    <button
                      key={item.id}
                      onClick={() => setSelectedHistoryId(item.id)}
                      className="w-full bg-gray-800 rounded-xl p-4 border border-gray-700 hover:border-gray-600 transition-colors text-left"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-mono text-sm text-gray-400">{item.order_number}</span>
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.bg} ${config.color}`}>
                              <StatusIcon className="w-3 h-3" />
                              {config.label}
                            </span>
                          </div>
                          <p className="text-white font-medium">{item.vehicle_info}</p>
                          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                            <span>{item.services_count} service{item.services_count !== 1 ? 's' : ''}</span>
                            <span>Completed {format(new Date(item.completed_at), 'MMM d, yyyy')}</span>
                          </div>
                        </div>
                        <ChevronRight className="w-5 h-5 text-gray-500 shrink-0" />
                      </div>
                    </button>
                  )
                })}
              </div>
            ) : (
              <div className="text-center py-12">
                <History className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                <p className="text-gray-400">No work history yet</p>
                <p className="text-sm text-gray-500 mt-1">Completed jobs will appear here</p>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
