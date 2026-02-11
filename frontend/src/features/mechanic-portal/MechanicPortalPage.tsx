import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import { useTheme } from '../../contexts/ThemeContext'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useNotificationManager } from '../../hooks/useNotificationManager'
import NotificationBanner from '../../components/NotificationBanner'
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
  User,
  Eye,
  EyeOff,
  LogOut,
  Palette,
  Check,
  RotateCcw,
  ChevronDown,
  Camera,
  X
} from 'lucide-react'
import { ACCENT_OPTIONS, FONT_SIZE_OPTIONS } from '../../contexts/ThemeContext'

interface MechanicJob {
  id: string
  order_number: string
  status: string
  vehicle_info: string
  description: string | null
  services_count: number
  updated_at: string
  work_started_at: string | null
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
  work_started_at: string | null
  work_completed_at: string | null
}

interface WorkHistoryItem {
  id: string
  order_number: string
  status: string
  vehicle_info: string
  completed_at: string
  services_count: number
  actual_hours: number | null
  points_earned: number
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

interface WorkPhoto {
  id: string
  image_url: string
  caption: string | null
  uploaded_at: string
  mechanic_name: string
}

const STATUS_LABELS: Record<string, string> = {
  assigned: 'New Job',
  acknowledged: 'Ready to Start',
  in_progress: 'Working',
  pending_review: 'Pending Review',
  completed: 'Completed',
  invoiced: 'Completed',
  paid: 'Completed',
}

type ViewType = 'list' | 'detail' | 'history' | 'stats' | 'request' | 'profile'

function LiveTimer({ startedAt }: { startedAt: string }) {
  const calc = useCallback(() => {
    const secs = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
    if (secs < 0) return '0m 0s'
    const h = Math.floor(secs / 3600)
    const m = Math.floor((secs % 3600) / 60)
    const s = secs % 60
    return h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`
  }, [startedAt])

  const [display, setDisplay] = useState(calc())

  useEffect(() => {
    const id = setInterval(() => setDisplay(calc()), 1000)
    return () => clearInterval(id)
  }, [calc])

  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 text-center">
      <p className="text-xs text-amber-400 uppercase tracking-wide mb-1">Time on job</p>
      <p className="text-2xl font-mono font-bold text-amber-400">{display}</p>
    </div>
  )
}

// Responsive container - full width on mobile, max 512px on larger screens, centered
const Container = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <div className={`min-h-screen bg-gray-900 ${className}`}>
    <div className="w-full sm:max-w-lg sm:mx-auto bg-gray-900 min-h-screen relative sm:shadow-2xl sm:shadow-black/50">
      {children}
    </div>
  </div>
)

export default function MechanicPortalPage() {
  const { user, logout, setUser } = useAuthStore()
  const { accentColors, accent, setAccent, fontSize, setFontSize, resetToDefaults } = useTheme()
  const queryClient = useQueryClient()
  
  // Notification manager for queued, deduplicated notifications
  const { notify, banners, dismissBanner, clearBanners } = useNotificationManager()
  
  // Connect to WebSocket for real-time updates
  useWebSocket({ onNotification: notify })
  
  const [view, setView] = useState<ViewType>('list')
  const [previousView, setPreviousView] = useState<ViewType>('list')
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  
  // Expandable job cards state
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null)
  const toggleExpand = (jobId: string) => {
    setExpandedJobId(prev => prev === jobId ? null : jobId)
    setShowPhotoPreview(null)
    setPhotoCaption('')
  }
  
  // Request form state
  const [requestType, setRequestType] = useState<'pto' | 'cash'>('pto')
  const [ptoStartDate, setPtoStartDate] = useState('')
  const [ptoEndDate, setPtoEndDate] = useState('')
  const [requestNotes, setRequestNotes] = useState('')
  
  // Profile form state
  const [isEditingProfile, setIsEditingProfile] = useState(false)
  const [isChangingPassword, setIsChangingPassword] = useState(false)
  const [firstName, setFirstName] = useState(user?.first_name || '')
  const [lastName, setLastName] = useState(user?.last_name || '')
  const [email, setEmail] = useState(user?.email || '')
  const [phone, setPhone] = useState(user?.phone || '')
  const [profilePassword, setProfilePassword] = useState('')
  const [showProfilePassword, setShowProfilePassword] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showCurrentPassword, setShowCurrentPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const originalEmail = user?.email || ''

  // Active jobs
  const { data: jobs, isLoading } = useQuery<MechanicJob[]>({
    queryKey: ['mechanic-jobs'],
    queryFn: async () => {
      const response = await api.get('/mechanics/my-jobs')
      return response.data
    },
    refetchOnWindowFocus: true, // WebSocket handles real-time updates
  })

  // Stats
  const { data: stats } = useQuery<MechanicStats>({
    queryKey: ['mechanic-stats'],
    queryFn: async () => {
      const response = await api.get('/mechanics/my-stats')
      return response.data
    },
  })

  // History (always load for empty state preview)
  const { data: history, isLoading: historyLoading } = useQuery<WorkHistoryItem[]>({
    queryKey: ['mechanic-history'],
    queryFn: async () => {
      const response = await api.get('/mechanics/my-history')
      return response.data
    },
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

  // Job detail (for full-page detail view - history items)
  const { data: jobDetail } = useQuery<MechanicJobDetail>({
    queryKey: ['mechanic-job-detail', selectedJobId],
    queryFn: async () => {
      const response = await api.get(`/mechanics/my-jobs/${selectedJobId}`)
      return response.data
    },
    enabled: !!selectedJobId && view === 'detail',
  })
  
  // Expanded job detail (for inline expandable cards)
  const { data: expandedJobDetail, isLoading: expandedJobLoading } = useQuery<MechanicJobDetail>({
    queryKey: ['mechanic-job-detail', expandedJobId],
    queryFn: async () => {
      const response = await api.get(`/mechanics/my-jobs/${expandedJobId}`)
      return response.data
    },
    enabled: !!expandedJobId,
  })
  
  // Work photos for expanded job
  const { data: workPhotos } = useQuery<WorkPhoto[]>({
    queryKey: ['work-photos', expandedJobId],
    queryFn: async () => {
      const response = await api.get(`/mechanics/my-jobs/${expandedJobId}/photos`)
      return response.data
    },
    enabled: !!expandedJobId,
  })
  
  // Photo upload state
  const [isUploadingPhoto, setIsUploadingPhoto] = useState(false)
  const [photoCaption, setPhotoCaption] = useState('')
  const [showPhotoPreview, setShowPhotoPreview] = useState<string | null>(null)
  const fileInputRef = useCallback((node: HTMLInputElement | null) => {
    // Store ref for triggering file input
    if (node) {
      (window as any).__photoFileInput = node
    }
  }, [])

  // Mutations
  // Combined: Accept + Start in one action (skips acknowledge if already acknowledged)
  const acceptAndStartMutation = useMutation({
    mutationFn: async ({ orderId, currentStatus }: { orderId: string; currentStatus: string }) => {
      if (currentStatus === 'assigned') {
        await api.post(`/repair-orders/${orderId}/acknowledge`)
      }
      await api.post(`/repair-orders/${orderId}/start-work`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-job-detail'] })
      toast.success('Job accepted & started!')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed'),
  })

  const completeWorkMutation = useMutation({
    mutationFn: (orderId: string) => api.post(`/repair-orders/${orderId}/complete-work`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-stats'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-history'] })
      setExpandedJobId(null) // Collapse expanded card
      setView('list')
      setSelectedJobId(null)
      toast.success('🎉 Job completed!')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed'),
  })
  
  const uploadPhotoMutation = useMutation({
    mutationFn: async ({ jobId, image, caption }: { jobId: string; image: string; caption?: string }) => {
      const response = await api.post(`/mechanics/my-jobs/${jobId}/photos`, { image, caption })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['work-photos', expandedJobId] })
      setShowPhotoPreview(null)
      setPhotoCaption('')
      toast.success('Photo uploaded!')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to upload photo'),
  })
  
  const deletePhotoMutation = useMutation({
    mutationFn: async ({ jobId, photoId }: { jobId: string; photoId: string }) => {
      await api.delete(`/mechanics/my-jobs/${jobId}/photos/${photoId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['work-photos', expandedJobId] })
      toast.success('Photo deleted')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to delete photo'),
  })
  
  // Handle photo file selection
  const handlePhotoSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    
    // Convert to base64
    const reader = new FileReader()
    reader.onload = () => {
      const base64 = reader.result as string
      setShowPhotoPreview(base64)
    }
    reader.readAsDataURL(file)
    
    // Reset input
    e.target.value = ''
  }
  
  const handlePhotoUpload = () => {
    if (!showPhotoPreview || !expandedJobId) return
    setIsUploadingPhoto(true)
    uploadPhotoMutation.mutate(
      { jobId: expandedJobId, image: showPhotoPreview, caption: photoCaption || undefined },
      { onSettled: () => setIsUploadingPhoto(false) }
    )
  }

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

  const updateProfileMutation = useMutation({
    mutationFn: async (data: { first_name?: string; last_name?: string; email?: string; phone?: string; password?: string }) => {
      const response = await api.put('/auth/me', data)
      return response.data
    },
    onSuccess: (data) => {
      // Handle new response format with user object wrapped
      const responseUser = data.user || data
      const isVerificationPending = data.email_verification_pending || false
      
      // Always update auth store - other fields may have been updated
      setUser(responseUser)
      setFirstName(responseUser.first_name)
      setLastName(responseUser.last_name)
      setEmail(responseUser.email)
      setPhone(responseUser.phone || '')
      
      if (isVerificationPending) {
        toast.success('Profile updated! Check your new email to confirm the email change.')
        setProfilePassword('')
        setIsEditingProfile(false)
      } else {
        toast.success('Profile updated!')
        setIsEditingProfile(false)
      }
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to update profile'),
  })

  const changePasswordMutation = useMutation({
    mutationFn: async (data: { current_password: string; new_password: string }) => {
      const response = await api.post('/auth/change-password', data)
      return response.data
    },
    onSuccess: () => {
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setIsChangingPassword(false)
      toast.success('Password changed! Please log in again.')
      setTimeout(() => {
        logout()
      }, 2000)
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to change password'),
  })

  const handleLogout = async () => {
    try { await api.post('/auth/logout') } catch {}
    logout()
  }

  const openJob = (jobId: string, fromView: ViewType = 'list') => {
    setSelectedJobId(jobId)
    setPreviousView(fromView)
    setView('detail')
  }

  const goBack = () => {
    setSelectedJobId(null)
    setView(previousView)
  }

  const isPending = acceptAndStartMutation.isPending || completeWorkMutation.isPending

  // Bottom Navigation Component - defined here so it's available in all views
  const BottomNav = () => {
    const currentView = view as ViewType
    return (
      <div className="fixed bottom-0 left-0 right-0 z-10">
        <div className="max-w-lg mx-auto bg-gray-800 border-t border-gray-700 px-4 py-3 flex justify-around">
          <button
            onClick={() => setView('list')}
            className={`flex flex-col items-center gap-1 ${currentView !== 'list' && currentView !== 'detail' ? 'text-gray-500 hover:text-gray-300' : ''}`}
            style={(currentView === 'list' || currentView === 'detail') ? { color: accentColors[500] } : undefined}
          >
            <Wrench className="w-6 h-6" />
            <span className="text-xs">Jobs</span>
          </button>
          <button
            onClick={() => setView('history')}
            className={`flex flex-col items-center gap-1 ${currentView !== 'history' ? 'text-gray-500 hover:text-gray-300' : ''}`}
            style={currentView === 'history' ? { color: accentColors[500] } : undefined}
          >
            <History className="w-6 h-6" />
            <span className="text-xs">History</span>
          </button>
          <button
            onClick={() => setView('stats')}
            className={`flex flex-col items-center gap-1 ${currentView !== 'stats' && currentView !== 'request' ? 'text-gray-500 hover:text-gray-300' : ''}`}
            style={(currentView === 'stats' || currentView === 'request') ? { color: accentColors[500] } : undefined}
          >
            <Trophy className="w-6 h-6" />
            <span className="text-xs">Rewards</span>
          </button>
          <button
            onClick={() => setView('profile')}
            className={`flex flex-col items-center gap-1 ${currentView !== 'profile' ? 'text-gray-500 hover:text-gray-300' : ''}`}
            style={currentView === 'profile' ? { color: accentColors[500] } : undefined}
          >
            <User className="w-6 h-6" />
            <span className="text-xs">Profile</span>
          </button>
        </div>
      </div>
    )
  }

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

          {/* Live Timer */}
          {jobDetail.status === 'in_progress' && jobDetail.work_started_at && (
            <div className="px-4">
              <LiveTimer startedAt={jobDetail.work_started_at} />
            </div>
          )}

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
            {(jobDetail.status === 'assigned' || jobDetail.status === 'acknowledged') && (
              <button
                onClick={() => acceptAndStartMutation.mutate({ orderId: jobDetail.id, currentStatus: jobDetail.status })}
                disabled={isPending}
                className="w-full py-5 bg-purple-600 hover:bg-purple-700 active:bg-purple-800 disabled:bg-gray-600 text-white text-xl font-bold rounded-2xl transition-all flex items-center justify-center gap-3 shadow-lg shadow-purple-500/25"
              >
                {isPending ? <Loader2 className="w-7 h-7 animate-spin" /> : <PlayCircle className="w-7 h-7" />}
                ACCEPT & START
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

            {['completed', 'invoiced', 'paid'].includes(jobDetail.status) && (
              <div className="bg-green-500/20 border border-green-500/50 rounded-2xl p-5 text-center">
                <CheckCircle className="w-10 h-10 text-green-400 mx-auto mb-2" />
                <p className="text-green-300 font-medium text-lg">Job Completed</p>
                {jobDetail.work_completed_at && (
                  <p className="text-green-400/70 text-sm mt-1">
                    {format(new Date(jobDetail.work_completed_at), 'MMM d, yyyy')}
                  </p>
                )}
              </div>
            )}
          </div>
          {/* Spacer for bottom nav */}
          <div className="h-20" />
        </div>
        <BottomNav />
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
                <button
                  key={item.id}
                  onClick={() => openJob(item.id, 'history')}
                  className="w-full text-left bg-gray-800 rounded-xl p-4 border border-gray-700 hover:border-gray-600 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-sm text-gray-500">{item.order_number}</span>
                    <span className="text-xs text-green-400 bg-green-500/20 px-2 py-0.5 rounded-full">
                      +{item.points_earned.toLocaleString()} pts
                    </span>
                  </div>
                  <p className="text-white font-medium">{item.vehicle_info}</p>
                  <div className="flex items-center gap-3 mt-1">
                    <p className="text-xs text-gray-500">
                      {format(new Date(item.completed_at), 'MMM d, yyyy')}
                    </p>
                    {item.actual_hours != null && (
                      <span className="text-xs text-amber-400 font-mono">{item.actual_hours}h worked</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <History className="w-12 h-12 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400">No completed jobs yet</p>
            </div>
          )}
        </div>
        {/* Spacer for bottom nav */}
        <div className="h-20" />
        <BottomNav />
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
        {/* Spacer for bottom nav */}
        <div className="h-20" />
        <BottomNav />
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
        {/* Spacer for bottom nav */}
        <div className="h-20" />
        <BottomNav />
      </Container>
    )
  }

  // ============ PROFILE VIEW ============
  if (view === 'profile') {
    const handleProfileUpdate = () => {
      if (!firstName.trim() || !lastName.trim()) {
        toast.error('Name is required')
        return
      }
      if (!email.trim() || !email.includes('@')) {
        toast.error('Valid email is required')
        return
      }
      
      const isEmailChanging = email !== originalEmail
      
      // If email is changing, password is required
      if (isEmailChanging && !profilePassword) {
        toast.error('Password required to change email')
        return
      }
      
      updateProfileMutation.mutate({
        first_name: firstName,
        last_name: lastName,
        email: email,
        phone: phone || undefined,
        password: isEmailChanging ? profilePassword : undefined,
      })
    }

    const handlePasswordChange = () => {
      if (!currentPassword || !newPassword) {
        toast.error('All password fields are required')
        return
      }
      if (newPassword !== confirmPassword) {
        toast.error('Passwords do not match')
        return
      }
      if (newPassword.length < 8) {
        toast.error('Password must be at least 8 characters')
        return
      }
      changePasswordMutation.mutate({
        current_password: currentPassword,
        new_password: newPassword,
      })
    }

    return (
      <Container>
        <header className="bg-gray-800 px-4 py-3 flex items-center gap-3">
          <button onClick={() => setView('list')} className="p-2 -ml-2 hover:bg-gray-700 rounded-lg">
            <ArrowLeft className="w-6 h-6 text-gray-400" />
          </button>
          <h1 className="text-lg font-bold text-white">Profile Settings</h1>
        </header>

        <div className="p-4 space-y-6 pb-24">
          {/* Profile Info */}
          <div className="bg-gray-800 rounded-2xl p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold">Personal Information</h2>
              {!isEditingProfile && (
                <button
                  onClick={() => {
                    setFirstName(user?.first_name || '')
                    setLastName(user?.last_name || '')
                    setEmail(user?.email || '')
                    setPhone(user?.phone || '')
                    setIsEditingProfile(true)
                  }}
                  className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
                >
                  Edit
                </button>
              )}
            </div>
            
            {!isEditingProfile ? (
              <div className="space-y-3">
                <div>
                  <div className="text-xs text-gray-400">Name</div>
                  <div className="text-white">{user?.first_name} {user?.last_name}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">Email</div>
                  <div className="text-white">{user?.email}</div>
                </div>
                {user?.phone && (
                  <div>
                    <div className="text-xs text-gray-400">Phone</div>
                    <div className="text-white">{user?.phone}</div>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">First Name</label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="text-xs text-gray-400 block mb-1">Last Name</label>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="text-xs text-gray-400 block mb-1">Email Address</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
                <p className="text-xs text-gray-500 mt-1">This is your login email</p>
                {email !== originalEmail && (
                  <div className="mt-2 bg-blue-500/10 border border-blue-500/30 rounded-lg p-2">
                    <p className="text-blue-400 text-xs">
                      📧 You'll receive a verification link at the new email
                    </p>
                  </div>
                )}
              </div>

              <div>
                <label className="text-xs text-gray-400 block mb-1">Phone</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="(555) 123-4567"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
              </div>

              {/* Password confirmation - shown when email is changing */}
              {email !== originalEmail && (
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Confirm Password</label>
                  <div className="relative">
                    <input
                      type={showProfilePassword ? 'text' : 'password'}
                      value={profilePassword}
                      onChange={(e) => setProfilePassword(e.target.value)}
                      placeholder="Enter your current password"
                      className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowProfilePassword(!showProfilePassword)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white p-1"
                    >
                      {showProfilePassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <p className="text-xs text-amber-400 mt-1">
                    🔒 Password required for security
                  </p>
                </div>
              )}

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setFirstName(user?.first_name || '')
                      setLastName(user?.last_name || '')
                      setEmail(user?.email || '')
                      setPhone(user?.phone || '')
                      setProfilePassword('')
                      setIsEditingProfile(false)
                    }}
                    className="flex-1 py-3 bg-gray-700 hover:bg-gray-600 text-white font-medium rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleProfileUpdate}
                    disabled={updateProfileMutation.isPending}
                    className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                  >
                    {updateProfileMutation.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <CheckCircle className="w-5 h-5" />}
                    Save
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Change Password */}
          <div className="bg-gray-800 rounded-2xl p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold">Change Password</h2>
              {!isChangingPassword && (
                <button
                  onClick={() => {
                    setCurrentPassword('')
                    setNewPassword('')
                    setConfirmPassword('')
                    setIsChangingPassword(true)
                  }}
                  className="px-3 py-1.5 text-sm bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition-colors"
                >
                  Change
                </button>
              )}
            </div>
            
            {isChangingPassword && (
              <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Current Password</label>
                <div className="relative">
                  <input
                    type={showCurrentPassword ? 'text' : 'password'}
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white p-1"
                  >
                    {showCurrentPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div>
                <label className="text-xs text-gray-400 block mb-1">New Password</label>
                <div className="relative">
                  <input
                    type={showNewPassword ? 'text' : 'password'}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white p-1"
                  >
                    {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-xs text-gray-500 mt-1">Min 8 characters</p>
              </div>

              <div>
                <label className="text-xs text-gray-400 block mb-1">Confirm New Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                />
              </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setCurrentPassword('')
                      setNewPassword('')
                      setConfirmPassword('')
                      setIsChangingPassword(false)
                    }}
                    className="flex-1 py-3 bg-gray-700 hover:bg-gray-600 text-white font-medium rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handlePasswordChange}
                    disabled={changePasswordMutation.isPending || !currentPassword || !newPassword || !confirmPassword}
                    className="flex-1 py-3 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                  >
                    {changePasswordMutation.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <CheckCircle className="w-5 h-5" />}
                    Change
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Appearance Settings */}
          <div className="bg-gray-800 rounded-2xl p-4 border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Palette className="w-5 h-5 text-purple-400" />
                <h2 className="text-white font-semibold">Appearance</h2>
              </div>
              <button
                onClick={resetToDefaults}
                className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
            </div>
            
            {/* Accent Color */}
            <div className="mb-4">
              <label className="text-xs text-gray-400 block mb-2">Accent Color</label>
              <div className="flex gap-2">
                {ACCENT_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    onClick={() => setAccent(option.id)}
                    className={`w-10 h-10 rounded-full flex items-center justify-center transition-all ${
                      accent === option.id ? 'ring-2 ring-offset-2 ring-offset-gray-800 ring-white scale-110' : ''
                    }`}
                    style={{ backgroundColor: option.colors[500] }}
                  >
                    {accent === option.id && <Check className="w-4 h-4 text-white" />}
                  </button>
                ))}
              </div>
            </div>

            {/* Font Size */}
            <div>
              <label className="text-xs text-gray-400 block mb-2">Font Size</label>
              <div className="flex gap-2">
                {FONT_SIZE_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    onClick={() => setFontSize(option.id)}
                    className={`flex-1 py-2 px-3 rounded-lg text-xs font-medium transition-all ${
                      fontSize === option.id
                        ? 'bg-purple-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
        {/* Spacer for bottom nav */}
        <div className="h-20" />
        <BottomNav />
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
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full transition-colors"
              style={{ backgroundColor: accentColors[500] + '30' }}
            >
              <Star className="w-4 h-4" style={{ color: accentColors[400] }} />
              <span className="font-bold" style={{ color: accentColors[400] }}>{stats?.available_points || 0}</span>
            </button>
            <button
              onClick={handleLogout}
              className="p-2 text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded-lg"
              title="Logout"
            >
              <LogOut className="w-5 h-5" />
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
        {/* Real-time notification banners */}
        <NotificationBanner
          banners={banners}
          onDismiss={dismissBanner}
          onDismissAll={clearBanners}
          autoDismissMs={8000}
        />

        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
          </div>
        ) : activeJobs.length === 0 && pendingReview.length === 0 ? (
          <>
            {/* No Active Jobs - Show Stats Instead */}
            <div className="text-center py-8">
              <div className="w-20 h-20 bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-4">
                <Wrench className="w-10 h-10 text-gray-600" />
              </div>
              <p className="text-gray-400 text-lg font-semibold">All caught up!</p>
              <p className="text-gray-600 text-sm mt-1">No active jobs right now 🎉</p>
            </div>

            {/* Quick Stats */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
                <p className="text-2xl font-bold text-white">{stats?.jobs_completed_today || 0}</p>
                <p className="text-xs text-gray-500 uppercase">Today</p>
              </div>
              <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
                <p className="text-2xl font-bold text-white">{stats?.jobs_completed_week || 0}</p>
                <p className="text-xs text-gray-500 uppercase">This Week</p>
              </div>
              <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
                <p className="text-2xl font-bold text-white">{stats?.jobs_completed_month || 0}</p>
                <p className="text-xs text-gray-500 uppercase">This Month</p>
              </div>
            </div>

            {/* Recent Completed */}
            {history && history.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm text-gray-400 font-medium">Recent Completed</h3>
                  <button
                    onClick={() => setView('history')}
                    className="text-xs hover:opacity-80"
                    style={{ color: accentColors[400] }}
                  >
                    View All →
                  </button>
                </div>
                <div className="space-y-2">
                  {history.slice(0, 3).map((item) => (
                    <div key={item.id} className="bg-gray-800 rounded-xl p-3 border border-gray-700">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <p className="text-white font-medium text-sm">{item.vehicle_info}</p>
                          <p className="text-xs text-gray-500 mt-0.5">{item.order_number}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-green-400 bg-green-500/20 px-2 py-0.5 rounded-full">
                            +{item.points_earned.toLocaleString()} pts
                          </span>
                          <CheckCircle className="w-4 h-4 text-green-400" />
                        </div>
                      </div>
                      <p className="text-xs text-gray-600 mt-1">
                        {format(new Date(item.completed_at), 'MMM d, h:mm a')}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Points Highlight */}
            {stats && stats.available_points > 0 && (
              <div className="bg-gradient-to-br from-amber-500/20 to-orange-500/20 border border-amber-500/30 rounded-2xl p-5">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-amber-500/20 rounded-xl flex items-center justify-center">
                    <Trophy className="w-6 h-6 text-amber-400" />
                  </div>
                  <div className="flex-1">
                    <p className="text-amber-200 text-sm">Available Points</p>
                    <p className="text-2xl font-bold text-white">{stats.available_points.toLocaleString()}</p>
                  </div>
                  <button
                    onClick={() => setView('stats')}
                    className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium rounded-lg"
                  >
                    Redeem
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            {/* Active Jobs - Expandable Cards */}
            {activeJobs.map((job) => {
              const isNew = job.status === 'assigned'
              const isWorking = job.status === 'in_progress'
              const isExpanded = expandedJobId === job.id
              const detail = isExpanded ? expandedJobDetail : null
              
              // Status-based accent color
              const borderColor = isWorking ? 'border-purple-500' : isNew ? 'border-blue-500' : 'border-gray-700'
              const statusBg = isWorking ? 'bg-purple-500' : isNew ? 'bg-blue-500' : 'bg-gray-600'
              
              return (
                <div 
                  key={job.id} 
                  className={`rounded-2xl overflow-hidden bg-gray-800/50 border-2 ${borderColor} transition-all`}
                >
                  {/* Header - Always visible */}
                  <button
                    onClick={() => toggleExpand(job.id)}
                    className="w-full p-4 text-left transition-all active:scale-[0.99]"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        {/* Status indicator dot */}
                        <div className={`w-3 h-3 rounded-full shrink-0 ${statusBg} ${isWorking ? 'animate-pulse' : ''}`} />
                        <div className="min-w-0 flex-1">
                          <h3 className="text-white font-semibold truncate">{job.vehicle_info}</h3>
                          <p className="text-sm text-gray-400">
                            {job.services_count} service{job.services_count !== 1 ? 's' : ''} · {job.order_number}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`px-2 py-1 rounded-md text-xs font-medium text-white ${statusBg}`}>
                          {STATUS_LABELS[job.status]}
                        </span>
                        <ChevronDown className={`w-5 h-5 text-gray-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
                      </div>
                    </div>
                  </button>
                  
                  {/* Expanded Content */}
                  <div className={`overflow-hidden transition-all duration-200 ${
                    isExpanded ? 'max-h-[800px] opacity-100' : 'max-h-0 opacity-0'
                  }`}>
                    <div className="px-4 pb-4 space-y-3">
                      {expandedJobLoading ? (
                        <div className="flex justify-center py-6">
                          <Loader2 className="w-6 h-6 animate-spin text-gray-500" />
                        </div>
                      ) : detail ? (
                        <>
                          {/* Vehicle Details */}
                          <div className="flex items-center gap-3 py-2 border-t border-gray-700/50">
                            <Truck className="w-4 h-4 text-gray-500 shrink-0" />
                            <div className="min-w-0 flex-1">
                              <p className="text-white text-sm">
                                {detail.vehicle_year} {detail.vehicle_make} {detail.vehicle_model}
                              </p>
                              {detail.vehicle_license_plate && (
                                <p className="text-xs text-gray-500">{detail.vehicle_license_plate}</p>
                              )}
                            </div>
                          </div>
                          
                          {/* Live Timer */}
                          {isWorking && detail.work_started_at && (
                            <LiveTimer startedAt={detail.work_started_at} />
                          )}
                          
                          {/* Services List */}
                          {detail.services.length > 0 && (
                            <div>
                              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Services</p>
                              <div className="space-y-1.5">
                                {detail.services.map((svc, idx) => (
                                  <div 
                                    key={idx} 
                                    className="flex items-center gap-2 text-sm"
                                  >
                                    <Wrench className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                                    <span className="text-gray-200">{svc.name}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          
                          {/* Work Photos Section */}
                          {['assigned', 'acknowledged', 'in_progress'].includes(job.status) && (
                            <div>
                              <div className="flex items-center justify-between mb-2">
                                <p className="text-xs text-gray-500 uppercase tracking-wide">Photos</p>
                                <label className="p-1.5 rounded-md bg-gray-700 hover:bg-gray-600 cursor-pointer transition-colors">
                                  <Camera className="w-4 h-4 text-gray-300" />
                                  <input
                                    type="file"
                                    accept="image/*"
                                    capture="environment"
                                    className="hidden"
                                    onChange={handlePhotoSelect}
                                    ref={fileInputRef}
                                  />
                                </label>
                              </div>
                              
                              {/* Photo Preview */}
                              {showPhotoPreview && (
                                <div className="rounded-lg bg-gray-700/50 p-2 mb-2">
                                  <div className="relative">
                                    <img 
                                      src={showPhotoPreview} 
                                      alt="Preview" 
                                      className="w-full rounded max-h-40 object-cover"
                                    />
                                    <button
                                      onClick={() => { setShowPhotoPreview(null); setPhotoCaption('') }}
                                      className="absolute top-1.5 right-1.5 p-1 bg-black/60 rounded-full"
                                    >
                                      <X className="w-3 h-3 text-white" />
                                    </button>
                                  </div>
                                  <input
                                    type="text"
                                    placeholder="Add note..."
                                    value={photoCaption}
                                    onChange={(e) => setPhotoCaption(e.target.value)}
                                    className="w-full mt-2 px-2 py-1.5 rounded bg-gray-600 text-sm text-white placeholder-gray-400"
                                  />
                                  <button
                                    onClick={handlePhotoUpload}
                                    disabled={isUploadingPhoto}
                                    className="w-full mt-2 py-1.5 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white text-sm font-medium rounded flex items-center justify-center gap-1.5"
                                  >
                                    {isUploadingPhoto ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Camera className="w-3.5 h-3.5" />}
                                    Upload
                                  </button>
                                </div>
                              )}
                              
                              {/* Photo Gallery */}
                              {workPhotos && workPhotos.length > 0 && (
                                <div className="grid grid-cols-4 gap-1.5">
                                  {workPhotos.map((photo) => (
                                    <div key={photo.id} className="relative group">
                                      <img
                                        src={photo.image_url}
                                        alt={photo.caption || 'Work photo'}
                                        className="w-full aspect-square object-cover rounded"
                                      />
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          if (confirm('Delete this photo?')) {
                                            deletePhotoMutation.mutate({ jobId: job.id, photoId: photo.id })
                                          }
                                        }}
                                        className="absolute top-0.5 right-0.5 p-0.5 bg-black/60 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                                      >
                                        <X className="w-2.5 h-2.5 text-white" />
                                      </button>
                                    </div>
                                  ))}
                                </div>
                              )}
                              
                              {/* Empty state */}
                              {(!workPhotos || workPhotos.length === 0) && !showPhotoPreview && (
                                <p className="text-xs text-gray-600 text-center py-2">No photos</p>
                              )}
                            </div>
                          )}
                          
                          {/* Action Button */}
                          <div className="pt-2">
                            {(job.status === 'assigned' || job.status === 'acknowledged') && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  acceptAndStartMutation.mutate({ orderId: job.id, currentStatus: job.status })
                                }}
                                disabled={isPending}
                                className="w-full py-3 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:bg-gray-700 text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2"
                              >
                                {isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <PlayCircle className="w-5 h-5" />}
                                ACCEPT & START
                              </button>
                            )}
                            
                            {job.status === 'in_progress' && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  completeWorkMutation.mutate(job.id)
                                }}
                                disabled={isPending}
                                className="w-full py-3 bg-green-600 hover:bg-green-700 active:bg-green-800 disabled:bg-gray-700 text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2"
                              >
                                {isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <CheckCircle className="w-5 h-5" />}
                                JOB DONE
                              </button>
                            )}
                          </div>
                        </>
                      ) : null}
                    </div>
                  </div>
                </div>
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
                      Pending Review
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </main>

      {/* Spacer for bottom nav */}
      <div className="h-20" />

      {/* Bottom Nav */}
      <BottomNav />
    </Container>
  )
}
