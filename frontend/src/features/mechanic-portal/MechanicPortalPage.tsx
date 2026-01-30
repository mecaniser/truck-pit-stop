import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import { 
  Wrench, 
  Truck, 
  CheckCircle, 
  PlayCircle, 
  Clock,
  ArrowLeft,
  Loader2,
  History,
  Trophy,
  Star,
  Zap,
  Calendar,
  DollarSign,
  X
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

interface MechanicStats {
  jobs_completed_today: number
  jobs_completed_week: number
  jobs_completed_month: number
  total_points: number
  available_points: number
  total_redeemed: number
  streak_days: number
  streak_multiplier: number
  pto_days_available: number
  cash_value: number
}

interface PTORequest {
  id: string
  request_type: string
  status: string
  pto_start_date: string | null
  pto_end_date: string | null
  pto_days: number | null
  points_requested: number
  cash_value: number | null
  mechanic_notes: string | null
  manager_notes: string | null
  created_at: string
  processed_at: string | null
}

const STATUS_LABELS: Record<string, string> = {
  assigned: 'New Job',
  acknowledged: 'Ready to Start',
  in_progress: 'Working',
  pending_review: 'Done - Awaiting Review',
}

type ViewType = 'list' | 'detail' | 'history' | 'stats' | 'request'

// Responsive container - max 480px on larger screens, centered
const Container = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <div className={`min-h-screen bg-gray-900 ${className}`}>
    <div className="max-w-lg mx-auto bg-gray-900 min-h-screen relative shadow-2xl shadow-black/50">
      {children}
    </div>
  </div>
)

export default function MechanicPortalPage() {
  const { user, logout } = useAuthStore()
  const queryClient = useQueryClient()
  const [view, setView] = useState<ViewType>('list')
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  
  // Request form state
  const [requestType, setRequestType] = useState<'pto' | 'cash'>('pto')
  const [ptoStartDate, setPtoStartDate] = useState('')
  const [ptoEndDate, setPtoEndDate] = useState('')
  const [requestNotes, setRequestNotes] = useState('')

  // Active jobs
  const { data: jobs, isLoading } = useQuery<MechanicJob[]>({
    queryKey: ['mechanic-jobs'],
    queryFn: async () => {
      const response = await api.get('/mechanics/my-jobs')
      return response.data
    },
    refetchInterval: 30000,
  })

  // Stats
  const { data: stats } = useQuery<MechanicStats>({
    queryKey: ['mechanic-stats'],
    queryFn: async () => {
      const response = await api.get('/mechanics/my-stats')
      return response.data
    },
  })

  // History
  const { data: history, isLoading: historyLoading } = useQuery<WorkHistoryItem[]>({
    queryKey: ['mechanic-history'],
    queryFn: async () => {
      const response = await api.get('/mechanics/my-history')
      return response.data
    },
    enabled: view === 'history',
  })
  
  // My PTO requests
  const { data: myRequests } = useQuery<PTORequest[]>({
    queryKey: ['my-pto-requests'],
    queryFn: async () => {
      const response = await api.get('/mechanics/pto-requests/my')
      return response.data
    },
    enabled: view === 'request',
  })

  // Job detail
  const { data: jobDetail } = useQuery<MechanicJobDetail>({
    queryKey: ['mechanic-job-detail', selectedJobId],
    queryFn: async () => {
      const response = await api.get(`/mechanics/my-jobs/${selectedJobId}`)
      return response.data
    },
    enabled: !!selectedJobId && view === 'detail',
  })

  // Mutations
  const acknowledgeMutation = useMutation({
    mutationFn: (orderId: string) => api.post(`/repair-orders/${orderId}/acknowledge`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-job-detail'] })
      toast.success('Job accepted!')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed'),
  })

  const startWorkMutation = useMutation({
    mutationFn: (orderId: string) => api.post(`/repair-orders/${orderId}/start-work`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-job-detail'] })
      toast.success('Work started!')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed'),
  })

  const completeWorkMutation = useMutation({
    mutationFn: (orderId: string) => api.post(`/repair-orders/${orderId}/complete-work`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-stats'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-history'] })
      setView('list')
      setSelectedJobId(null)
      toast.success('🎉 Job completed! +10 points')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed'),
  })

  const createRequestMutation = useMutation({
    mutationFn: async (data: { request_type: string; pto_start_date?: string; pto_end_date?: string; points_requested: number; notes?: string }) => {
      const response = await api.post('/mechanics/pto-requests', data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-pto-requests'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-stats'] })
      setPtoStartDate('')
      setPtoEndDate('')
      setRequestNotes('')
      toast.success('Request submitted!')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to submit request'),
  })

  const cancelRequestMutation = useMutation({
    mutationFn: (requestId: string) => api.delete(`/mechanics/pto-requests/${requestId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-pto-requests'] })
      toast.success('Request cancelled')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed'),
  })

  const handleLogout = async () => {
    try { await api.post('/auth/logout') } catch {}
    logout()
  }

  const openJob = (jobId: string) => {
    setSelectedJobId(jobId)
    setView('detail')
  }

  const goBack = () => {
    setSelectedJobId(null)
    setView('list')
  }

  const isPending = acknowledgeMutation.isPending || startWorkMutation.isPending || completeWorkMutation.isPending

  // ============ JOB DETAIL VIEW ============
  if (view === 'detail' && selectedJobId && jobDetail) {
    return (
      <Container className="flex flex-col">
        <div className="flex flex-col min-h-screen">
          {/* Header */}
          <header className="bg-gray-800 px-4 py-3 flex items-center gap-3">
            <button onClick={goBack} className="p-2 -ml-2 hover:bg-gray-700 rounded-lg">
              <ArrowLeft className="w-6 h-6 text-gray-400" />
            </button>
            <div className="flex-1">
              <p className="text-xs text-gray-500 uppercase tracking-wide">
                {STATUS_LABELS[jobDetail.status] || jobDetail.status}
              </p>
              <h1 className="text-lg font-bold text-white">{jobDetail.order_number}</h1>
            </div>
          </header>

          {/* Vehicle Card */}
          <div className="p-4">
            <div className="bg-gray-800 rounded-2xl p-4 border border-gray-700">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-cyan-500/20 rounded-xl flex items-center justify-center">
                  <Truck className="w-6 h-6 text-cyan-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <h2 className="text-white font-bold text-lg truncate">
                    {jobDetail.vehicle_year} {jobDetail.vehicle_make} {jobDetail.vehicle_model}
                  </h2>
                  {jobDetail.vehicle_license_plate && (
                    <p className="text-gray-400 text-sm">{jobDetail.vehicle_license_plate}</p>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Services */}
          {jobDetail.services.length > 0 && (
            <div className="px-4 flex-1">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Work to do</p>
              <div className="space-y-2">
                {jobDetail.services.map((svc, idx) => (
                  <div key={idx} className="flex items-center gap-3 bg-gray-800 rounded-xl p-3 border border-gray-700">
                    <Wrench className="w-5 h-5 text-amber-400 shrink-0" />
                    <span className="text-white font-medium">{svc.name}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* BIG ACTION BUTTON */}
          <div className="p-4 mt-auto">
            {jobDetail.status === 'assigned' && (
              <button
                onClick={() => acknowledgeMutation.mutate(jobDetail.id)}
                disabled={isPending}
                className="w-full py-5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:bg-gray-600 text-white text-xl font-bold rounded-2xl transition-all flex items-center justify-center gap-3 shadow-lg shadow-blue-500/25"
              >
                {isPending ? <Loader2 className="w-7 h-7 animate-spin" /> : <CheckCircle className="w-7 h-7" />}
                ACCEPT JOB
              </button>
            )}

            {jobDetail.status === 'acknowledged' && (
              <button
                onClick={() => startWorkMutation.mutate(jobDetail.id)}
                disabled={isPending}
                className="w-full py-5 bg-purple-600 hover:bg-purple-700 active:bg-purple-800 disabled:bg-gray-600 text-white text-xl font-bold rounded-2xl transition-all flex items-center justify-center gap-3 shadow-lg shadow-purple-500/25"
              >
                {isPending ? <Loader2 className="w-7 h-7 animate-spin" /> : <PlayCircle className="w-7 h-7" />}
                START WORK
              </button>
            )}

            {jobDetail.status === 'in_progress' && (
              <button
                onClick={() => completeWorkMutation.mutate(jobDetail.id)}
                disabled={isPending}
                className="w-full py-5 bg-green-600 hover:bg-green-700 active:bg-green-800 disabled:bg-gray-600 text-white text-xl font-bold rounded-2xl transition-all flex items-center justify-center gap-3 shadow-lg shadow-green-500/25"
              >
                {isPending ? <Loader2 className="w-7 h-7 animate-spin" /> : <CheckCircle className="w-7 h-7" />}
                JOB DONE ✓
              </button>
            )}

            {jobDetail.status === 'pending_review' && (
              <div className="bg-orange-500/20 border border-orange-500/50 rounded-2xl p-5 text-center">
                <Clock className="w-10 h-10 text-orange-400 mx-auto mb-2" />
                <p className="text-orange-300 font-medium text-lg">Waiting for manager approval</p>
              </div>
            )}
          </div>
        </div>
      </Container>
    )
  }

  // ============ HISTORY VIEW ============
  if (view === 'history') {
    return (
      <Container>
        <header className="bg-gray-800 px-4 py-3 flex items-center gap-3">
          <button onClick={() => setView('list')} className="p-2 -ml-2 hover:bg-gray-700 rounded-lg">
            <ArrowLeft className="w-6 h-6 text-gray-400" />
          </button>
          <h1 className="text-lg font-bold text-white">Work History</h1>
        </header>

        <div className="p-4">
          {historyLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
            </div>
          ) : history && history.length > 0 ? (
            <div className="space-y-3">
              {history.map((item) => (
                <div key={item.id} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-sm text-gray-500">{item.order_number}</span>
                    <span className="text-xs text-green-400 bg-green-500/20 px-2 py-0.5 rounded-full">
                      +10 pts
                    </span>
                  </div>
                  <p className="text-white font-medium">{item.vehicle_info}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {format(new Date(item.completed_at), 'MMM d, yyyy')}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <History className="w-12 h-12 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400">No completed jobs yet</p>
            </div>
          )}
        </div>
      </Container>
    )
  }

  // ============ STATS VIEW ============
  if (view === 'stats') {
    const availablePoints = stats?.available_points || 0
    const canRedeemPTO = availablePoints >= 8000
    const ptoDays = Math.floor(availablePoints / 8000)
    const cashValue = (availablePoints * 0.0375).toFixed(2)
    
    return (
      <Container>
        <header className="bg-gray-800 px-4 py-3 flex items-center gap-3">
          <button onClick={() => setView('list')} className="p-2 -ml-2 hover:bg-gray-700 rounded-lg">
            <ArrowLeft className="w-6 h-6 text-gray-400" />
          </button>
          <h1 className="text-lg font-bold text-white">My Stats & Rewards</h1>
        </header>

        <div className="p-4 space-y-4">
          {/* Available Points Card */}
          <div className="bg-gradient-to-br from-amber-500 to-orange-600 rounded-2xl p-6 text-center">
            <Trophy className="w-12 h-12 text-white mx-auto mb-2" />
            <p className="text-white/80 text-sm uppercase tracking-wide">Available Points</p>
            <p className="text-5xl font-black text-white">{availablePoints.toLocaleString()}</p>
            <p className="text-white/60 text-sm mt-1">
              Lifetime earned: {(stats?.total_points || 0).toLocaleString()}
            </p>
          </div>

          {/* Streak & Multiplier */}
          {(stats?.streak_days || 0) > 0 && (
            <div className="bg-gray-800 rounded-2xl p-4 border border-gray-700 flex items-center gap-4">
              <div className="w-12 h-12 bg-orange-500/20 rounded-xl flex items-center justify-center">
                <Zap className="w-6 h-6 text-orange-400" />
              </div>
              <div className="flex-1">
                <p className="text-gray-400 text-sm">Current Streak</p>
                <p className="text-2xl font-bold text-white">{stats?.streak_days} days</p>
              </div>
              {(stats?.streak_multiplier || 1) > 1 && (
                <div className="bg-green-500/20 px-3 py-1 rounded-full">
                  <span className="text-green-400 font-bold">{stats?.streak_multiplier}x</span>
                </div>
              )}
            </div>
          )}

          {/* Redemption Options */}
          <div className="bg-gray-800 rounded-2xl p-4 border border-gray-700">
            <p className="text-sm text-gray-400 mb-3">Redeem Your Points</p>
            
            {/* PTO Option */}
            <div className={`p-4 rounded-xl mb-3 ${canRedeemPTO ? 'bg-blue-500/20 border border-blue-500/50' : 'bg-gray-700/50'}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">🏖️</span>
                  <span className="text-white font-medium">PTO Day</span>
                </div>
                <span className="text-gray-400 text-sm">8,000 pts = 1 day</span>
              </div>
              {canRedeemPTO ? (
                <p className="text-blue-400 text-sm">
                  You can redeem <strong>{ptoDays} day{ptoDays > 1 ? 's' : ''}</strong> of PTO!
                </p>
              ) : (
                <p className="text-gray-500 text-sm">
                  Need {(8000 - availablePoints).toLocaleString()} more points
                </p>
              )}
            </div>

            {/* Cash Option */}
            <div className={`p-4 rounded-xl ${availablePoints > 0 ? 'bg-green-500/20 border border-green-500/50' : 'bg-gray-700/50'}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">💵</span>
                  <span className="text-white font-medium">Cash Out</span>
                </div>
                <span className="text-gray-400 text-sm">$0.0375/pt</span>
              </div>
              {availablePoints > 0 ? (
                <p className="text-green-400 text-sm">
                  Worth <strong>${cashValue}</strong> cash
                </p>
              ) : (
                <p className="text-gray-500 text-sm">Complete jobs to earn points</p>
              )}
            </div>

            {/* Request Button */}
            <button
              onClick={() => setView('request')}
              disabled={availablePoints <= 0}
              className="w-full py-4 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white font-bold rounded-xl transition-colors mt-3"
            >
              Request PTO or Cash
            </button>
          </div>

          {/* Job Counts */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <p className="text-3xl font-bold text-white">{stats?.jobs_completed_today || 0}</p>
              <p className="text-xs text-gray-500 uppercase">Today</p>
            </div>
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <p className="text-3xl font-bold text-white">{stats?.jobs_completed_week || 0}</p>
              <p className="text-xs text-gray-500 uppercase">This Week</p>
            </div>
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <p className="text-3xl font-bold text-white">{stats?.jobs_completed_month || 0}</p>
              <p className="text-xs text-gray-500 uppercase">This Month</p>
            </div>
          </div>

          {/* How Points Work */}
          <div className="bg-gray-800 rounded-2xl p-4 border border-gray-700">
            <p className="text-sm text-gray-400 mb-3">How Points Work</p>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2 text-gray-300">
                <span className="text-green-400">•</span>
                <span>1 point per $1 of labor value</span>
              </div>
              <div className="flex items-center gap-2 text-gray-300">
                <span className="text-green-400">•</span>
                <span>5+ day streak = 1.1x bonus</span>
              </div>
              <div className="flex items-center gap-2 text-gray-300">
                <span className="text-green-400">•</span>
                <span>10+ day streak = 1.25x bonus</span>
              </div>
              <div className="flex items-center gap-2 text-gray-300">
                <span className="text-green-400">•</span>
                <span>Bigger jobs = more points!</span>
              </div>
            </div>
          </div>

          {/* Milestones */}
          <div className="bg-gray-800 rounded-2xl p-4 border border-gray-700">
            <p className="text-sm text-gray-400 mb-3">Milestones</p>
            <div className="space-y-3">
              {[
                { pts: 1000, label: 'Rookie', icon: '🔧' },
                { pts: 5000, label: 'Pro', icon: '⭐' },
                { pts: 10000, label: 'Expert', icon: '🏆' },
                { pts: 50000, label: 'Master', icon: '👑' },
              ].map((m) => {
                const achieved = (stats?.total_points || 0) >= m.pts
                return (
                  <div key={m.pts} className={`flex items-center gap-3 ${achieved ? '' : 'opacity-40'}`}>
                    <span className="text-2xl">{m.icon}</span>
                    <div className="flex-1">
                      <p className={`font-medium ${achieved ? 'text-white' : 'text-gray-500'}`}>{m.label}</p>
                      <p className="text-xs text-gray-500">{m.pts.toLocaleString()} points</p>
                    </div>
                    {achieved && <CheckCircle className="w-5 h-5 text-green-400" />}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </Container>
    )
  }

  // ============ REQUEST VIEW ============
  if (view === 'request') {
    const availablePoints = stats?.available_points || 0
    const canRequestPTO = availablePoints >= 8000
    const ptoDays = ptoStartDate && ptoEndDate 
      ? Math.max(1, Math.ceil((new Date(ptoEndDate).getTime() - new Date(ptoStartDate).getTime()) / (1000 * 60 * 60 * 24)) + 1)
      : 0
    const ptoPointsNeeded = ptoDays * 8000
    const cashValue = (availablePoints * 0.0375).toFixed(2)
    
    return (
      <Container>
        <header className="bg-gray-800 px-4 py-3 flex items-center gap-3">
          <button onClick={() => setView('stats')} className="p-2 -ml-2 hover:bg-gray-700 rounded-lg">
            <ArrowLeft className="w-6 h-6 text-gray-400" />
          </button>
          <h1 className="text-lg font-bold text-white">Request Rewards</h1>
        </header>

        <div className="p-4 space-y-4">
          {/* Available Points */}
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex items-center justify-between">
            <span className="text-gray-400">Available Points</span>
            <span className="text-2xl font-bold text-amber-400">{availablePoints.toLocaleString()}</span>
          </div>

          {/* Request Type Toggle */}
          <div className="flex gap-2">
            <button
              onClick={() => setRequestType('pto')}
              className={`flex-1 py-3 rounded-xl font-medium flex items-center justify-center gap-2 transition-colors ${
                requestType === 'pto' 
                  ? 'bg-blue-600 text-white' 
                  : 'bg-gray-800 text-gray-400 border border-gray-700'
              }`}
            >
              <Calendar className="w-5 h-5" />
              PTO
            </button>
            <button
              onClick={() => setRequestType('cash')}
              className={`flex-1 py-3 rounded-xl font-medium flex items-center justify-center gap-2 transition-colors ${
                requestType === 'cash' 
                  ? 'bg-green-600 text-white' 
                  : 'bg-gray-800 text-gray-400 border border-gray-700'
              }`}
            >
              <DollarSign className="w-5 h-5" />
              Cash
            </button>
          </div>

          {/* PTO Form */}
          {requestType === 'pto' && (
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 space-y-4">
              <p className="text-sm text-gray-400">Select your PTO dates (8,000 pts/day)</p>
              
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Start Date</label>
                  <input
                    type="date"
                    value={ptoStartDate}
                    onChange={(e) => setPtoStartDate(e.target.value)}
                    min={format(new Date(), 'yyyy-MM-dd')}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">End Date</label>
                  <input
                    type="date"
                    value={ptoEndDate}
                    onChange={(e) => setPtoEndDate(e.target.value)}
                    min={ptoStartDate || format(new Date(), 'yyyy-MM-dd')}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                  />
                </div>
              </div>

              {ptoDays > 0 && (
                <div className="bg-gray-700/50 rounded-lg p-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Days requested</span>
                    <span className="text-white font-medium">{ptoDays}</span>
                  </div>
                  <div className="flex justify-between text-sm mt-1">
                    <span className="text-gray-400">Points needed</span>
                    <span className={ptoPointsNeeded <= availablePoints ? 'text-green-400' : 'text-red-400'}>
                      {ptoPointsNeeded.toLocaleString()}
                    </span>
                  </div>
                </div>
              )}

              <textarea
                value={requestNotes}
                onChange={(e) => setRequestNotes(e.target.value)}
                placeholder="Notes (optional)"
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white placeholder-gray-500 resize-none"
                rows={2}
              />

              <button
                onClick={() => {
                  if (!ptoStartDate || !ptoEndDate) {
                    toast.error('Please select dates')
                    return
                  }
                  if (ptoPointsNeeded > availablePoints) {
                    toast.error('Not enough points')
                    return
                  }
                  createRequestMutation.mutate({
                    request_type: 'pto',
                    pto_start_date: ptoStartDate,
                    pto_end_date: ptoEndDate,
                    points_requested: ptoPointsNeeded,
                    notes: requestNotes || undefined,
                  })
                }}
                disabled={!canRequestPTO || !ptoStartDate || !ptoEndDate || ptoPointsNeeded > availablePoints || createRequestMutation.isPending}
                className="w-full py-4 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white font-bold rounded-xl transition-colors flex items-center justify-center gap-2"
              >
                {createRequestMutation.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <Calendar className="w-5 h-5" />}
                Request PTO
              </button>
            </div>
          )}

          {/* Cash Form */}
          {requestType === 'cash' && (
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 space-y-4">
              <p className="text-sm text-gray-400">Cash out your points ($0.0375/pt)</p>
              
              <div className="bg-green-500/20 border border-green-500/50 rounded-xl p-4 text-center">
                <p className="text-green-400 text-sm">You can cash out</p>
                <p className="text-3xl font-bold text-white">${cashValue}</p>
                <p className="text-green-400/60 text-xs mt-1">({availablePoints.toLocaleString()} points)</p>
              </div>

              <textarea
                value={requestNotes}
                onChange={(e) => setRequestNotes(e.target.value)}
                placeholder="Notes (optional)"
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white placeholder-gray-500 resize-none"
                rows={2}
              />

              <button
                onClick={() => {
                  if (availablePoints <= 0) {
                    toast.error('No points to cash out')
                    return
                  }
                  createRequestMutation.mutate({
                    request_type: 'cash',
                    points_requested: availablePoints,
                    notes: requestNotes || undefined,
                  })
                }}
                disabled={availablePoints <= 0 || createRequestMutation.isPending}
                className="w-full py-4 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-bold rounded-xl transition-colors flex items-center justify-center gap-2"
              >
                {createRequestMutation.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <DollarSign className="w-5 h-5" />}
                Request Cash Out
              </button>
            </div>
          )}

          {/* My Requests */}
          {myRequests && myRequests.length > 0 && (
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <p className="text-sm text-gray-400 mb-3">My Requests</p>
              <div className="space-y-2">
                {myRequests.map((req) => (
                  <div key={req.id} className="bg-gray-700/50 rounded-lg p-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {req.request_type === 'pto' ? (
                          <Calendar className="w-4 h-4 text-blue-400" />
                        ) : (
                          <DollarSign className="w-4 h-4 text-green-400" />
                        )}
                        <span className="text-white font-medium">
                          {req.request_type === 'pto' 
                            ? `${req.pto_days} day${req.pto_days !== 1 ? 's' : ''} PTO`
                            : `$${req.cash_value?.toFixed(2)} cash`
                          }
                        </span>
                      </div>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        req.status === 'pending' ? 'bg-amber-500/20 text-amber-400' :
                        req.status === 'approved' ? 'bg-green-500/20 text-green-400' :
                        req.status === 'denied' ? 'bg-red-500/20 text-red-400' :
                        'bg-gray-500/20 text-gray-400'
                      }`}>
                        {req.status}
                      </span>
                    </div>
                    {req.request_type === 'pto' && req.pto_start_date && (
                      <p className="text-xs text-gray-500 mt-1">
                        {format(new Date(req.pto_start_date), 'MMM d')} - {format(new Date(req.pto_end_date!), 'MMM d, yyyy')}
                      </p>
                    )}
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-xs text-gray-500">
                        {format(new Date(req.created_at), 'MMM d, yyyy')}
                      </span>
                      {req.status === 'pending' && (
                        <button
                          onClick={() => cancelRequestMutation.mutate(req.id)}
                          className="text-xs text-red-400 hover:text-red-300"
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                    {req.manager_notes && (
                      <p className="text-xs text-gray-400 mt-2 italic">"{req.manager_notes}"</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </Container>
    )
  }

  // ============ MAIN JOB LIST VIEW ============
  const activeJobs = jobs?.filter(j => ['assigned', 'acknowledged', 'in_progress'].includes(j.status)) || []
  const pendingReview = jobs?.filter(j => j.status === 'pending_review') || []

  return (
    <Container>
      {/* Header */}
      <header className="bg-gray-800 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-400">Hey, {user?.first_name}!</p>
            <h1 className="text-xl font-bold text-white">My Jobs</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setView('stats')}
              className="flex items-center gap-1.5 bg-amber-500/20 hover:bg-amber-500/30 px-3 py-1.5 rounded-full transition-colors"
            >
              <Star className="w-4 h-4 text-amber-400" />
              <span className="text-amber-400 font-bold">{stats?.available_points || 0}</span>
            </button>
            <button
              onClick={handleLogout}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Quick Stats Bar */}
      <div className="bg-gray-800/50 px-4 py-2 flex items-center gap-4 border-b border-gray-700/50">
        <div className="flex items-center gap-1.5 text-sm">
          <span className="text-gray-500">Today:</span>
          <span className="text-white font-medium">{stats?.jobs_completed_today || 0} done</span>
        </div>
        {(stats?.streak_days || 0) > 0 && (
          <div className="flex items-center gap-1.5 text-sm">
            <Zap className="w-4 h-4 text-orange-400" />
            <span className="text-orange-400 font-medium">{stats?.streak_days} day streak</span>
          </div>
        )}
      </div>

      <main className="p-4 space-y-4 pb-24">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
          </div>
        ) : activeJobs.length === 0 && pendingReview.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-20 h-20 bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-4">
              <Wrench className="w-10 h-10 text-gray-600" />
            </div>
            <p className="text-gray-400 text-lg">No jobs right now</p>
            <p className="text-gray-600 text-sm mt-1">Take a break! 🎉</p>
          </div>
        ) : (
          <>
            {/* Active Jobs */}
            {activeJobs.map((job) => {
              const isNew = job.status === 'assigned'
              const isWorking = job.status === 'in_progress'
              
              return (
                <button
                  key={job.id}
                  onClick={() => openJob(job.id)}
                  className={`w-full rounded-2xl p-5 text-left transition-all active:scale-[0.98] ${
                    isWorking 
                      ? 'bg-purple-600 shadow-lg shadow-purple-500/25' 
                      : isNew 
                        ? 'bg-blue-600 shadow-lg shadow-blue-500/25'
                        : 'bg-gray-800 border border-gray-700'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <p className={`text-xs uppercase tracking-wide mb-1 ${
                        isWorking || isNew ? 'text-white/70' : 'text-gray-500'
                      }`}>
                        {STATUS_LABELS[job.status]}
                      </p>
                      <h3 className="text-white font-bold text-lg truncate">{job.vehicle_info}</h3>
                      <p className={`text-sm mt-1 ${isWorking || isNew ? 'text-white/60' : 'text-gray-500'}`}>
                        {job.services_count} service{job.services_count !== 1 ? 's' : ''}
                      </p>
                    </div>
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${
                      isWorking ? 'bg-white/20' : isNew ? 'bg-white/20' : 'bg-gray-700'
                    }`}>
                      {isWorking ? (
                        <PlayCircle className="w-6 h-6 text-white" />
                      ) : isNew ? (
                        <span className="text-2xl">🆕</span>
                      ) : (
                        <Wrench className="w-6 h-6 text-amber-400" />
                      )}
                    </div>
                  </div>
                </button>
              )
            })}

            {/* Pending Review */}
            {pendingReview.length > 0 && (
              <div className="pt-4">
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Awaiting Review</p>
                {pendingReview.map((job) => (
                  <div
                    key={job.id}
                    className="bg-gray-800/50 rounded-xl p-4 border border-gray-700/50 flex items-center gap-3"
                  >
                    <Clock className="w-5 h-5 text-orange-400 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-white font-medium truncate">{job.vehicle_info}</p>
                      <p className="text-xs text-gray-500">{job.order_number}</p>
                    </div>
                    <span className="text-xs text-orange-400 bg-orange-500/20 px-2 py-1 rounded-full shrink-0">
                      Pending
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </main>

      {/* Bottom Nav - Fixed within container */}
      <div className="fixed bottom-0 left-0 right-0 z-10">
        <div className="max-w-lg mx-auto bg-gray-800 border-t border-gray-700 px-4 py-3 flex justify-around">
          <button
            onClick={() => setView('list')}
            className={`flex flex-col items-center gap-1 ${view === 'list' ? 'text-amber-400' : 'text-gray-500 hover:text-gray-300'}`}
          >
            <Wrench className="w-6 h-6" />
            <span className="text-xs">Jobs</span>
          </button>
          <button
            onClick={() => setView('history')}
            className={`flex flex-col items-center gap-1 ${view === 'history' ? 'text-amber-400' : 'text-gray-500 hover:text-gray-300'}`}
          >
            <History className="w-6 h-6" />
            <span className="text-xs">History</span>
          </button>
          <button
            onClick={() => setView('stats')}
            className={`flex flex-col items-center gap-1 ${view === 'stats' ? 'text-amber-400' : 'text-gray-500 hover:text-gray-300'}`}
          >
            <Trophy className="w-6 h-6" />
            <span className="text-xs">Stats</span>
          </button>
        </div>
      </div>
    </Container>
  )
}
