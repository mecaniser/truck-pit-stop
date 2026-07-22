import { useState, useEffect, useCallback, useRef } from 'react'
import { Spinner } from '@/components/ui'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import { useTheme } from '../../contexts/ThemeContext'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useNotificationManager } from '../../hooks/useNotificationManager'
import { useCoreCountdown } from '@/hooks/useCoreCountdown'
import { useMechanicSuggestion } from '@/hooks/useMechanicSuggestion'
import { useSuggestionToasts } from '@/hooks/useSuggestionToasts'
import { useTimerPanelPersistence } from '@/hooks/useTimerPanelPersistence'
import NotificationBanner from '../../components/NotificationBanner'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import { StatusLED } from '@/components/ui/GlassNoirCard'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import { 
  Wrench, 
  Truck, 
  CheckCircle, 
  PlayCircle, 
  ArrowLeft,
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
  X,
  PauseCircle
} from 'lucide-react'
import { ACCENT_OPTIONS, FONT_SIZE_OPTIONS } from '../../contexts/ThemeContext'
import { MISC_WORK_OPTIONS } from '@/lib/mechanicWorkLabels'
import { formatSuggestedNextAction, getSuggestedActionButtonLabel } from '@/lib/mechanicSuggestions'

interface MechanicJob {
  id: string
  order_number: string
  status: string
  vehicle_info: string
  description: string | null
  services_count: number
  created_at: string
  updated_at: string
  work_started_at: string | null
  hold_reason: string | null
  held_at: string | null
  ro_today_tracked_minutes: number
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
  hold_reason: string | null
  held_at: string | null
  ro_today_tracked_minutes: number
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

interface SelectedWorkPhoto {
  name: string
  dataUrl: string
}

interface MechanicDaySummary {
  date: string
  timezone: string
  shift_start_local: string
  shift_end_local: string
  core_target_minutes: number
  tracked_minutes: number
  ro_minutes: number
  misc_minutes: number
  overtime_minutes: number
  utilization_percent: number
  efficiency_percent: number | null
  book_hours: number
  actual_ro_hours: number
  active_session: {
    id: string
    session_type: 'repair_order' | 'misc'
    repair_order_id?: string | null
    misc_category: string | null
    started_at?: string | null
  } | null
  attendance_active: boolean
  attendance_started_at: string | null
  attendance_ended_at: string | null
  break_active: boolean
  break_started_at: string | null
  attendance_minutes: number
  break_minutes: number
  idle_minutes: number
  late_arrival_minutes: number
  early_leave_minutes: number
  flex_budget_minutes: number
  flex_used_minutes: number
  flex_remaining_minutes: number
  flex_overrun_minutes: number
  core_gap_minutes: number
  core_countdown_elapsed_minutes: number
  core_countdown_remaining_minutes: number
  tracked_vs_attendance_gap_minutes: number
  work_coverage_percent: number | null
  trend_7_days: Array<{
    date: string
    tracked_minutes: number
    utilization_percent: number
    efficiency_percent: number | null
  }>
}

interface TimerActionResponse {
  success: boolean
  session_id?: string
  attendance_session_id?: string
  break_session_id?: string
  auto_clocked_in?: boolean
  auto_stopped_timer_session_id?: string
  auto_ended_break_session_id?: string
  message: string
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

const HOLD_REASONS = [
  { value: 'waiting_for_parts', label: 'Waiting for Parts' },
  { value: 'waiting_for_customer_approval', label: 'Waiting for Customer Approval' },
  { value: 'need_more_info', label: 'Need More Info' },
  { value: 'other', label: 'Other' },
] as const

// Includes system-generated hold reasons for display (not user-selectable)
const HOLD_REASON_LABELS: Record<string, string> = {
  waiting_for_parts: 'Waiting for Parts',
  waiting_for_customer_approval: 'Waiting for Customer Approval',
  need_more_info: 'Need More Info',
  other: 'Other',
  switched_to_other_ro: 'Switched to another job',
}

type ViewType = 'list' | 'detail' | 'history' | 'stats' | 'request' | 'profile'

function formatSecondsAsClock(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(safeSeconds / 3600)
  const minutes = Math.floor((safeSeconds % 3600) / 60)
  const seconds = safeSeconds % 60
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
}


function formatMinutesShort(totalMinutes: number): string {
  const safeMinutes = Math.max(0, Math.floor(totalMinutes || 0))
  const h = Math.floor(safeMinutes / 60)
  const m = safeMinutes % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function LiveTimer({ startedAt, totalMinutesToday = 0 }: { startedAt: string; totalMinutesToday?: number }) {
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
      <p className="mt-1 text-xs text-amber-200">
        Total time on this RO today: <span className="font-semibold">{formatMinutesShort(totalMinutesToday)}</span>
      </p>
    </div>
  )
}

// Responsive container - full width on mobile, max 512px on larger screens, centered
const Container = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <div className={`min-h-screen bg-zinc-950 touch-manipulation ${className}`}>
    <div className="w-full sm:max-w-lg sm:mx-auto bg-zinc-950 min-h-screen relative sm:shadow-2xl sm:shadow-black/50 pb-[env(safe-area-inset-bottom)]">
      {children}
    </div>
  </div>
)

export default function MechanicPortalPage() {
  const { user, logout, setUser } = useAuthStore()
  const { accent, setAccent, fontSize, setFontSize, resetToDefaults } = useTheme()
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
    setSelectedPhotoPreviews([])
    setPhotoCaption('')
  }
  
  // Request form state
  const [requestType, setRequestType] = useState<'pto' | 'cash'>('pto')
  const [ptoStartDate, setPtoStartDate] = useState('')
  const [ptoEndDate, setPtoEndDate] = useState('')
  const [requestNotes, setRequestNotes] = useState('')
  const [miscCategory, setMiscCategory] = useState('shop_cleanup')
  const [miscNote, setMiscNote] = useState('')
  
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

  // Hold state
  const [holdTarget, setHoldTarget] = useState<string | null>(null)
  const [holdReason, setHoldReason] = useState('')

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

  const { data: daySummary } = useQuery<MechanicDaySummary>({
    queryKey: ['mechanic-day-summary'],
    queryFn: async () => {
      const response = await api.get('/mechanics/me/day-summary')
      return response.data
    },
    refetchOnWindowFocus: true,
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
  const [selectedPhotoPreviews, setSelectedPhotoPreviews] = useState<SelectedWorkPhoto[]>([])
  const [showClockOutModal, setShowClockOutModal] = useState(false)
  const [isTimerPanelExpanded, handleTimerPanelToggle] = useTimerPanelPersistence(user?.id)
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
      return { currentStatus }
    },
    onSuccess: ({ currentStatus }) => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-job-detail'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      toast.success(currentStatus === 'in_progress' ? 'Timer resumed' : 'Job accepted & started!')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed'),
  })

  const completeWorkMutation = useMutation({
    mutationFn: (orderId: string) => api.post(`/repair-orders/${orderId}/complete-work`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-stats'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-history'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      setExpandedJobId(null) // Collapse expanded card
      setView('list')
      setSelectedJobId(null)
      toast.success('🎉 Job completed!')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed'),
  })

  const holdOrderMutation = useMutation({
    mutationFn: ({ orderId, reason }: { orderId: string; reason: string }) =>
      api.post(`/repair-orders/${orderId}/hold`, { reason }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-job-detail'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      setHoldTarget(null)
      setHoldReason('')
      toast.success('Job put on hold')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to hold job'),
  })

  const resumeOrderMutation = useMutation({
    mutationFn: (orderId: string) => api.post(`/repair-orders/${orderId}/resume`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-job-detail'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      toast.success('Job resumed — timer started')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to resume job'),
  })

  const uploadPhotoMutation = useMutation({
    mutationFn: async ({ jobId, image, caption }: { jobId: string; image: string; caption?: string }) => {
      const response = await api.post(`/mechanics/my-jobs/${jobId}/photos`, { image, caption })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['work-photos', expandedJobId] })
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
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    if (files.length === 0) return

    const imageFiles = files.filter((file) => {
      if (!file.type.startsWith('image/')) {
        toast.error(`${file.name} is not an image file`)
        return false
      }
      return true
    })
    if (imageFiles.length === 0) return

    const readFile = (file: File) => new Promise<SelectedWorkPhoto>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve({ name: file.name, dataUrl: reader.result as string })
      reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
      reader.readAsDataURL(file)
    })

    try {
      setSelectedPhotoPreviews(await Promise.all(imageFiles.map(readFile)))
    } catch (error: any) {
      toast.error(error.message || 'Failed to read selected photos')
    }
  }
  
  const handlePhotoUpload = async () => {
    if (selectedPhotoPreviews.length === 0 || !expandedJobId) return
    setIsUploadingPhoto(true)
    try {
      let uploadedCount = 0
      for (const photo of selectedPhotoPreviews) {
        try {
          await uploadPhotoMutation.mutateAsync(
            { jobId: expandedJobId, image: photo.dataUrl, caption: photoCaption || undefined }
          )
          uploadedCount += 1
        } catch {
          // The mutation's onError shows the failed upload; keep the batch moving.
        }
      }
      if (uploadedCount > 0) {
        toast.success(`${uploadedCount} photo${uploadedCount === 1 ? '' : 's'} uploaded!`)
        setSelectedPhotoPreviews([])
        setPhotoCaption('')
      }
    } finally {
      setIsUploadingPhoto(false)
    }
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

  const startMiscTimerMutation = useMutation({
    mutationFn: async (payload: { misc_category: string; note?: string }) => {
      const response = await api.post<TimerActionResponse>('/mechanics/me/timer/start-misc', payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      toast.success('Misc timer started')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to start misc timer'),
  })

  const stopTimerMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<TimerActionResponse>('/mechanics/me/timer/stop')
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      toast.success('Timer stopped')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to stop timer'),
  })

  const clockInMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<TimerActionResponse>('/mechanics/me/attendance/clock-in', {})
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-detail'] })
      toast.success('Clocked in')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to clock in'),
  })

  const clockOutMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<TimerActionResponse>('/mechanics/me/attendance/clock-out', {})
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-detail'] })
      toast.success('Clocked out')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to clock out'),
  })

  const startBreakMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<TimerActionResponse>('/mechanics/me/break/start', {})
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-detail'] })
      toast.success('Break started')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to start break'),
  })

  const endBreakMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<TimerActionResponse>('/mechanics/me/break/end', {})
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-detail'] })
      toast.success('Break ended')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to end break'),
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
  const isClockedIn = !!daySummary?.attendance_active
  const isOnBreak = !!daySummary?.break_active
  const hasActiveDayTimer = !!daySummary?.active_session
  const isActiveRoTimer = daySummary?.active_session?.session_type === 'repair_order'
  const timerToggleBusy = startMiscTimerMutation.isPending || stopTimerMutation.isPending
  const attendanceToggleBusy = clockInMutation.isPending || clockOutMutation.isPending
  const breakToggleBusy = startBreakMutation.isPending || endBreakMutation.isPending
  const { countdownNowMs } = useCoreCountdown(daySummary)
  // Keep this frontend recommendation layer aligned with backend `compute_next_action_recommendation`.
  const {
    mechanicSuggestion,
    isMiscSuggestion,
    highlightedJobId,
    shouldPulseTimerToggle,
  } = useMechanicSuggestion(daySummary, jobs)
  const breakStartedMs = daySummary?.break_started_at ? new Date(daySummary.break_started_at).getTime() : NaN
  const breakElapsedSeconds = isOnBreak
    ? (Number.isNaN(breakStartedMs)
      ? (daySummary?.break_minutes || 0) * 60
      : Math.max(Math.floor((countdownNowMs - breakStartedMs) / 1000), 0))
    : (daySummary?.break_minutes || 0) * 60
  const activeSessionStartedMs = daySummary?.active_session?.started_at
    ? new Date(daySummary.active_session.started_at).getTime()
    : NaN
  const activeSessionElapsedSeconds = hasActiveDayTimer && !Number.isNaN(activeSessionStartedMs)
    ? Math.max(Math.floor((countdownNowMs - activeSessionStartedMs) / 1000), 0)
    : 0
  const collapsedInlineTimerLabel = isOnBreak
    ? `Break ${formatSecondsAsClock(breakElapsedSeconds)}`
    : hasActiveDayTimer
      ? `Active ${formatSecondsAsClock(activeSessionElapsedSeconds)}`
      : `${((daySummary?.tracked_minutes ?? 0) / 60).toFixed(1)}h logged`
  const showPanelBreakControl = isClockedIn && !isOnBreak

  const handleTimerToggle = () => {
    if (hasActiveDayTimer) {
      stopTimerMutation.mutate()
      return
    }
    startMiscTimerMutation.mutate({ misc_category: miscCategory, note: miscNote || undefined })
  }

  const handleAttendanceToggle = () => {
    if (isClockedIn) {
      clockOutMutation.mutate()
      return
    }
    clockInMutation.mutate()
  }

  const handleBreakToggle = () => {
    if (isOnBreak) {
      endBreakMutation.mutate()
      return
    }
    startBreakMutation.mutate()
  }

  const handleHeaderClockOutAction = () => {
    if (isClockedIn) {
      setShowClockOutModal(true)
      return
    }
    setView('profile')
  }

  const handleConfirmClockOut = () => {
    clockOutMutation.mutate(undefined, {
      onSuccess: () => setShowClockOutModal(false),
    })
  }

  useEffect(() => {
    if (!isClockedIn && showClockOutModal) {
      setShowClockOutModal(false)
    }
  }, [isClockedIn, showClockOutModal])

  useSuggestionToasts({
    userId: user?.id,
    view,
    isClockedIn,
    suggestion: mechanicSuggestion,
  })

  // B3: Auto-scroll to suggested job card
  const suggestedJobRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (view !== 'list' || !highlightedJobId) return
    const timeout = setTimeout(() => {
      suggestedJobRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }, 300)
    return () => clearTimeout(timeout)
  }, [highlightedJobId, view])

  // B1: Sticky action bar handler
  const handleStickyAction = () => {
    switch (mechanicSuggestion.action) {
      case 'clock_in':
        clockInMutation.mutate()
        break
      case 'end_break':
        endBreakMutation.mutate()
        break
      case 'clock_out':
        setShowClockOutModal(true)
        break
      case 'start_misc':
        startMiscTimerMutation.mutate({ misc_category: miscCategory, note: miscNote || undefined })
        break
      case 'stop_misc_pick_ro':
        stopTimerMutation.mutate(undefined, {
          onSuccess: () => {
            if (mechanicSuggestion.recommendedJob) {
              setExpandedJobId(mechanicSuggestion.recommendedJob.id)
            }
          },
        })
        break
      case 'start_assigned_ro':
        if (mechanicSuggestion.recommendedJob) {
          acceptAndStartMutation.mutate({
            orderId: mechanicSuggestion.recommendedJob.id,
            currentStatus: mechanicSuggestion.recommendedJob.status,
          })
        }
        break
      case 'continue_ro':
        if (mechanicSuggestion.recommendedJob) {
          setExpandedJobId(mechanicSuggestion.recommendedJob.id)
          setTimeout(() => {
            suggestedJobRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
          }, 150)
        }
        break
    }
  }
  const stickyActionBusy = clockInMutation.isPending || endBreakMutation.isPending || stopTimerMutation.isPending || startMiscTimerMutation.isPending || acceptAndStartMutation.isPending

  const formatCreatedAt = (createdAt?: string | null) => {
    if (!createdAt) return 'Unknown'
    const parsed = new Date(createdAt)
    if (Number.isNaN(parsed.getTime())) return 'Unknown'
    return format(parsed, 'MMM d, yyyy h:mm a')
  }

  // Sticky action bar + Bottom Navigation Component
  const isActiveMisc = hasActiveDayTimer && daySummary?.active_session?.session_type === 'misc'
  const showStickyBar = isClockedIn && !isOnBreak && view === 'list' && !(mechanicSuggestion.action === 'start_misc' && isActiveMisc)
  const stickyIsLiveTimer = mechanicSuggestion.action === 'continue_ro' && hasActiveDayTimer

  const BottomNav = () => {
    const currentView = view as ViewType
    return (
      <div className="fixed bottom-0 left-0 right-0 z-10">
        {showStickyBar ? (
          <div className="max-w-lg mx-auto bg-zinc-900/95 border-t border-zinc-700/50 px-4 py-3 backdrop-blur-sm">
            {stickyIsLiveTimer ? (
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-base text-[var(--accent-300)] min-w-0 truncate">
                  <StatusLED status="active" size="sm" />
                  <span className="font-mono">{mechanicSuggestion.recommendedJob?.order_number}</span>
                  <span className="font-mono text-emerald-300">{formatSecondsAsClock(activeSessionElapsedSeconds)}</span>
                </div>
                <button
                  onClick={() => mechanicSuggestion.recommendedJob && completeWorkMutation.mutate(mechanicSuggestion.recommendedJob.id)}
                  disabled={completeWorkMutation.isPending || !mechanicSuggestion.recommendedJob}
                  className="px-5 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white text-base font-semibold disabled:opacity-50 disabled:cursor-not-allowed shrink-0 border border-emerald-400/50 transition-all hover:shadow-[0_0_24px_rgba(16,185,129,0.5)]"
                >
                  {completeWorkMutation.isPending ? 'Completing...' : 'Job Done'}
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3">
                <div className="flex-1 min-w-0 text-base text-zinc-300 truncate">
                  {mechanicSuggestion.action === 'start_misc'
                    ? `Start ${MISC_WORK_OPTIONS.find((o) => o.value === miscCategory)?.label || 'misc'} timer`
                    : formatSuggestedNextAction(mechanicSuggestion.action)}
                </div>
                <button
                  onClick={handleStickyAction}
                  disabled={stickyActionBusy}
                  className="px-5 py-3 rounded-xl bg-[var(--accent-600)] hover:bg-[var(--accent-500)] active:scale-[0.98] text-white text-base font-semibold disabled:opacity-50 disabled:cursor-not-allowed shrink-0 border border-[var(--accent-400)]/50 transition-all hover:shadow-[0_0_24px_var(--accent-500)]"
                >
                  {stickyActionBusy
                    ? '...'
                    : mechanicSuggestion.action === 'start_misc'
                      ? `Start ${MISC_WORK_OPTIONS.find((o) => o.value === miscCategory)?.label || 'Misc'}`
                      : getSuggestedActionButtonLabel(mechanicSuggestion.action)}
                </button>
              </div>
            )}
          </div>
        ) : null}
        <div className="max-w-lg mx-auto bg-zinc-900/95 backdrop-blur-sm border-t border-zinc-700/50 px-2 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] flex justify-around">
          <button
            onClick={() => setView('list')}
            className={`flex flex-col items-center justify-center gap-0.5 min-h-[48px] min-w-[64px] rounded-xl active:bg-zinc-800/60 transition-colors ${currentView !== 'list' && currentView !== 'detail' ? 'text-zinc-500' : 'text-[var(--accent-400)]'}`}
          >
            <Wrench className="w-7 h-7" />
            <span className="text-[11px] font-medium">Jobs</span>
          </button>
          <button
            onClick={() => setView('history')}
            className={`flex flex-col items-center justify-center gap-0.5 min-h-[48px] min-w-[64px] rounded-xl active:bg-zinc-800/60 transition-colors ${currentView !== 'history' ? 'text-zinc-500' : 'text-[var(--accent-400)]'}`}
          >
            <History className="w-7 h-7" />
            <span className="text-[11px] font-medium">History</span>
          </button>
          <button
            onClick={() => setView('stats')}
            className={`flex flex-col items-center justify-center gap-0.5 min-h-[48px] min-w-[64px] rounded-xl active:bg-zinc-800/60 transition-colors ${currentView !== 'stats' && currentView !== 'request' ? 'text-zinc-500' : 'text-[var(--accent-400)]'}`}
          >
            <Trophy className="w-7 h-7" />
            <span className="text-[11px] font-medium">Rewards</span>
          </button>
          <button
            onClick={() => setView('profile')}
            className={`flex flex-col items-center justify-center gap-0.5 min-h-[48px] min-w-[64px] rounded-xl active:bg-zinc-800/60 transition-colors ${currentView !== 'profile' ? 'text-zinc-500' : 'text-[var(--accent-400)]'}`}
          >
            <User className="w-7 h-7" />
            <span className="text-[11px] font-medium">Profile</span>
          </button>
        </div>
      </div>
    )
  }

  // ============ JOB DETAIL VIEW ============
  if (view === 'detail' && selectedJobId && jobDetail) {
    const isTimedForDetail = daySummary?.active_session?.session_type === 'repair_order'
      && daySummary.active_session.repair_order_id === jobDetail.id
    const timedStartForDetail = daySummary?.active_session?.started_at || jobDetail.work_started_at

    return (
      <Container className="flex flex-col">
        <div className="flex flex-col min-h-screen">
          {/* Header */}
          <header className="bg-zinc-900/80 backdrop-blur-sm px-4 py-3 flex items-center gap-3 border-b border-zinc-700/50">
            <button onClick={goBack} className="p-3 -ml-3 active:bg-zinc-800 rounded-xl">
              <ArrowLeft className="w-6 h-6 text-zinc-400" />
            </button>
            <div className="flex-1">
              <p className="text-xs text-zinc-500 uppercase tracking-wide">
                {STATUS_LABELS[jobDetail.status] || jobDetail.status}
              </p>
              <h1 className="text-lg font-bold text-zinc-100">{jobDetail.order_number}</h1>
            </div>
          </header>

          {/* Vehicle Card */}
          <div className="p-4">
            <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-[var(--accent-500)]/20 rounded-xl flex items-center justify-center border border-[var(--accent-500)]/30">
                  <Truck className="w-6 h-6 text-[var(--accent-400)]" />
                </div>
                <div className="flex-1 min-w-0">
                  <h2 className="text-zinc-100 font-bold text-lg truncate">
                    {jobDetail.vehicle_year} {jobDetail.vehicle_make} {jobDetail.vehicle_model}
                  </h2>
                  {jobDetail.vehicle_license_plate && (
                    <p className="text-zinc-400 text-sm">{jobDetail.vehicle_license_plate}</p>
                  )}
                  <p className="text-zinc-500 text-xs mt-1">Created {formatCreatedAt(jobDetail.created_at)}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Live Timer */}
          {jobDetail.status === 'in_progress' && isTimedForDetail && timedStartForDetail && (
            <div className="px-4">
              <LiveTimer startedAt={timedStartForDetail} totalMinutesToday={jobDetail.ro_today_tracked_minutes} />
            </div>
          )}
          {jobDetail.status === 'in_progress' && !isTimedForDetail && (
            <div className="px-4">
              <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                In-progress job is currently not timed. Resume timer for this repair order.
              </div>
            </div>
          )}

          {/* Services */}
          {jobDetail.services.length > 0 && (
            <div className="px-4 flex-1">
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 mb-2">Work to do</p>
              <div className="space-y-2">
                {jobDetail.services.map((svc, idx) => (
                  <div key={idx} className="flex items-center gap-3 bg-zinc-800/60 rounded-xl p-3 border border-zinc-700/50">
                    <Wrench className="w-5 h-5 text-[var(--accent-400)] shrink-0" />
                    <span className="text-zinc-100 font-medium">{svc.name}</span>
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
                className="w-full py-5 bg-[var(--accent-600)] hover:bg-[var(--accent-500)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white text-xl font-bold rounded-2xl transition-all flex items-center justify-center gap-3 border border-[var(--accent-400)]/50 hover:shadow-[0_0_32px_var(--accent-500)]"
              >
                {isPending ? <Spinner size="lg" /> : <PlayCircle className="w-7 h-7" />}
                ACCEPT & START
              </button>
            )}

            {jobDetail.status === 'in_progress' && jobDetail.hold_reason && (
              <div className="space-y-3">
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl px-4 py-3 flex items-center gap-2">
                  <StatusLED status="warning" />
                  <span className="text-amber-200 font-medium">
                    On hold: {HOLD_REASON_LABELS[jobDetail.hold_reason || ''] || jobDetail.hold_reason}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={() => resumeOrderMutation.mutate(jobDetail.id)}
                    disabled={isPending}
                    className="w-full py-5 bg-[var(--accent-600)] hover:bg-[var(--accent-500)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white text-xl font-bold rounded-2xl transition-all flex items-center justify-center gap-3 border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)]"
                  >
                    {isPending ? <Spinner size="lg" /> : <PlayCircle className="w-7 h-7" />}
                    RESUME
                  </button>
                  <button
                    onClick={() => completeWorkMutation.mutate(jobDetail.id)}
                    disabled={isPending}
                    className="w-full py-5 bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white text-xl font-bold rounded-2xl transition-all flex items-center justify-center gap-3 border border-emerald-400/50 hover:shadow-[0_0_24px_rgba(16,185,129,0.5)]"
                  >
                    {isPending ? <Spinner size="lg" /> : <CheckCircle className="w-7 h-7" />}
                    JOB DONE
                  </button>
                </div>
              </div>
            )}

            {jobDetail.status === 'in_progress' && !jobDetail.hold_reason && (
              <div className="space-y-3">
                {holdTarget === jobDetail.id ? (
                  <div className="space-y-3">
                    <p className="text-sm text-zinc-400 font-medium">Why are you pausing?</p>
                    <div className="flex flex-wrap gap-2">
                      {HOLD_REASONS.map((r) => (
                        <button
                          key={r.value}
                          type="button"
                          onClick={() => setHoldReason(r.value)}
                          className={`px-4 py-2.5 rounded-full border text-sm font-medium transition-all ${
                            holdReason === r.value
                              ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                              : 'bg-zinc-800/60 border-zinc-600/50 text-zinc-300 active:bg-zinc-700'
                          }`}
                        >
                          {r.label}
                        </button>
                      ))}
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <button
                        onClick={() => { setHoldTarget(null); setHoldReason('') }}
                        className="py-4 bg-zinc-800/80 hover:bg-zinc-700 active:scale-[0.98] text-zinc-300 text-lg font-semibold rounded-2xl transition-all border border-zinc-600/50"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => holdReason && holdOrderMutation.mutate({ orderId: jobDetail.id, reason: holdReason })}
                        disabled={!holdReason || holdOrderMutation.isPending}
                        className="py-4 bg-amber-600 hover:bg-amber-500 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white text-lg font-semibold rounded-2xl transition-all border border-amber-400/50"
                      >
                        {holdOrderMutation.isPending ? 'Holding...' : 'Confirm Hold'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className={`grid gap-3 ${isTimedForDetail ? 'grid-cols-2' : 'grid-cols-3'}`}>
                      {!isTimedForDetail && (
                        <button
                          onClick={() => acceptAndStartMutation.mutate({ orderId: jobDetail.id, currentStatus: jobDetail.status })}
                          disabled={isPending}
                          className="w-full py-5 bg-[var(--accent-600)] hover:bg-[var(--accent-500)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white text-xl font-bold rounded-2xl transition-all flex items-center justify-center gap-3 border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)]"
                        >
                          {isPending ? <Spinner size="lg" /> : <PlayCircle className="w-7 h-7" />}
                          RESUME
                        </button>
                      )}
                      <button
                        onClick={() => setHoldTarget(jobDetail.id)}
                        className="w-full py-5 bg-amber-600/80 hover:bg-amber-600 active:scale-[0.98] text-white text-xl font-bold rounded-2xl transition-all flex items-center justify-center gap-3 border border-amber-400/50"
                      >
                        <PauseCircle className="w-7 h-7" />
                        HOLD
                      </button>
                      <button
                        onClick={() => completeWorkMutation.mutate(jobDetail.id)}
                        disabled={isPending}
                        className="w-full py-5 bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white text-xl font-bold rounded-2xl transition-all flex items-center justify-center gap-3 border border-emerald-400/50 hover:shadow-[0_0_24px_rgba(16,185,129,0.5)]"
                      >
                        {isPending ? <Spinner size="lg" /> : <CheckCircle className="w-7 h-7" />}
                        DONE
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {jobDetail.status === 'pending_review' && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-5 text-center">
                <StatusLED status="warning" />
                <p className="text-amber-300 font-medium text-lg mt-2">Waiting for manager approval</p>
              </div>
            )}

            {['completed', 'invoiced', 'paid'].includes(jobDetail.status) && (
              <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-5 text-center">
                <StatusLED status="active" />
                <p className="text-emerald-300 font-medium text-lg mt-2">Job Completed</p>
                {jobDetail.work_completed_at && (
                  <p className="text-emerald-400/70 text-sm mt-1">
                    {format(new Date(jobDetail.work_completed_at), 'MMM d, yyyy')}
                  </p>
                )}
              </div>
            )}
          </div>
          {/* Spacer for bottom nav */}
          <div className="h-24" />
        </div>
        <BottomNav />
      </Container>
    )
  }

  // ============ HISTORY VIEW ============
  if (view === 'history') {
    return (
      <Container>
        <header className="bg-zinc-900/80 backdrop-blur-sm px-4 py-3 flex items-center gap-3 border-b border-zinc-700/50">
          <button onClick={() => setView('list')} className="p-3 -ml-3 active:bg-zinc-800 rounded-xl">
            <ArrowLeft className="w-6 h-6 text-zinc-400" />
          </button>
          <h1 className="text-lg font-bold text-zinc-100">Work History</h1>
        </header>

        <div className="p-4">
          {historyLoading ? (
            <div className="flex justify-center py-12">
              <Spinner size="lg" />
            </div>
          ) : history && history.length > 0 ? (
            <div className="space-y-3">
              {history.map((item) => (
                <button
                  key={item.id}
                  onClick={() => openJob(item.id, 'history')}
                  className="w-full text-left bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 hover:border-[var(--accent-500)]/40 transition-all shadow-xl shadow-black/20 hover:shadow-[var(--accent-500)]/10"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-sm text-zinc-500">{item.order_number}</span>
                    <span className="inline-flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-500/20 px-2.5 py-1 rounded-full border border-emerald-500/30">
                      <StatusLED status="active" size="sm" />
                      +{item.points_earned.toLocaleString()} pts
                    </span>
                  </div>
                  <p className="text-zinc-100 font-medium">{item.vehicle_info}</p>
                  <div className="flex items-center gap-3 mt-1">
                    <p className="text-xs text-zinc-500">
                      {format(new Date(item.completed_at), 'MMM d, yyyy')}
                    </p>
                    {item.actual_hours != null && (
                      <span className="text-xs text-[var(--accent-400)] font-mono">{item.actual_hours}h worked</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <div className="w-16 h-16 bg-zinc-900/80 rounded-full flex items-center justify-center mx-auto mb-3 border border-zinc-700/50">
                <History className="w-8 h-8 text-zinc-600" />
              </div>
              <p className="text-zinc-400">No completed jobs yet</p>
            </div>
          )}
        </div>
        {/* Spacer for bottom nav */}
        <div className="h-24" />
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
        <header className="bg-zinc-900/80 backdrop-blur-sm px-4 py-3 flex items-center gap-3 border-b border-zinc-700/50">
          <button onClick={() => setView('list')} className="p-3 -ml-3 active:bg-zinc-800 rounded-xl">
            <ArrowLeft className="w-6 h-6 text-zinc-400" />
          </button>
          <h1 className="text-lg font-bold text-zinc-100">My Stats & Rewards</h1>
        </header>

        <div className="p-4 space-y-4">
          {/* Available Points Card */}
          <div className="relative bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-6 text-center border border-[var(--accent-500)]/30 shadow-xl shadow-black/20 overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-[var(--accent-500)]/20 to-transparent" />
            <div className="relative">
              <div className="w-16 h-16 bg-[var(--accent-500)]/20 rounded-2xl flex items-center justify-center mx-auto mb-3 border border-[var(--accent-400)]/30">
                <Trophy className="w-8 h-8 text-[var(--accent-400)]" />
              </div>
              <p className="text-zinc-400 text-sm uppercase tracking-[0.2em] font-bold">Available Points</p>
              <p className="text-5xl font-black text-zinc-100 mt-1">{availablePoints.toLocaleString()}</p>
              <p className="text-zinc-500 text-sm mt-2">
                Lifetime earned: {(stats?.total_points || 0).toLocaleString()}
              </p>
            </div>
          </div>

          {/* Streak & Multiplier */}
          {(stats?.streak_days || 0) > 0 && (
            <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20 flex items-center gap-4">
              <div className="w-12 h-12 bg-amber-500/20 rounded-xl flex items-center justify-center border border-amber-500/30">
                <Zap className="w-6 h-6 text-amber-400" />
              </div>
              <div className="flex-1">
                <p className="text-zinc-400 text-sm">Current Streak</p>
                <p className="text-2xl font-bold text-zinc-100">{stats?.streak_days} days</p>
              </div>
              {(stats?.streak_multiplier || 1) > 1 && (
                <div className="bg-emerald-500/20 px-3 py-1.5 rounded-full border border-emerald-500/30">
                  <span className="text-emerald-400 font-bold">{stats?.streak_multiplier}x</span>
                </div>
              )}
            </div>
          )}

          {/* Redemption Options */}
          <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 mb-3">Redeem Your Points</p>
            
            {/* PTO Option */}
            <div className={`p-4 rounded-xl mb-3 ${canRedeemPTO ? 'bg-[var(--accent-500)]/10 border border-[var(--accent-500)]/30' : 'bg-zinc-800/60 border border-zinc-700/50'}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Calendar className="w-5 h-5 text-[var(--accent-400)]" />
                  <span className="text-zinc-100 font-medium">PTO Day</span>
                </div>
                <span className="text-zinc-400 text-sm">8,000 pts = 1 day</span>
              </div>
              {canRedeemPTO ? (
                <p className="text-[var(--accent-400)] text-sm">
                  You can redeem <strong>{ptoDays} day{ptoDays > 1 ? 's' : ''}</strong> of PTO!
                </p>
              ) : (
                <p className="text-zinc-500 text-sm">
                  Need {(8000 - availablePoints).toLocaleString()} more points
                </p>
              )}
            </div>

            {/* Cash Option */}
            <div className={`p-4 rounded-xl ${availablePoints > 0 ? 'bg-emerald-500/10 border border-emerald-500/30' : 'bg-zinc-800/60 border border-zinc-700/50'}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <DollarSign className="w-5 h-5 text-emerald-400" />
                  <span className="text-zinc-100 font-medium">Cash Out</span>
                </div>
                <span className="text-zinc-400 text-sm">$0.0375/pt</span>
              </div>
              {availablePoints > 0 ? (
                <p className="text-emerald-400 text-sm">
                  Worth <strong>${cashValue}</strong> cash
                </p>
              ) : (
                <p className="text-zinc-500 text-sm">Complete jobs to earn points</p>
              )}
            </div>

            {/* Request Button */}
            <button
              onClick={() => setView('request')}
              disabled={availablePoints <= 0}
              className="w-full py-4 bg-[var(--accent-600)] hover:bg-[var(--accent-500)] disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-all mt-3 border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)]"
            >
              Request PTO or Cash
            </button>
          </div>

          {/* Job Counts */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 text-center shadow-xl shadow-black/20">
              <p className="text-3xl font-bold text-zinc-100">{stats?.jobs_completed_today || 0}</p>
              <p className="text-xs text-zinc-500 uppercase">Today</p>
            </div>
            <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 text-center shadow-xl shadow-black/20">
              <p className="text-3xl font-bold text-zinc-100">{stats?.jobs_completed_week || 0}</p>
              <p className="text-xs text-zinc-500 uppercase">This Week</p>
            </div>
            <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 text-center shadow-xl shadow-black/20">
              <p className="text-3xl font-bold text-zinc-100">{stats?.jobs_completed_month || 0}</p>
              <p className="text-xs text-zinc-500 uppercase">This Month</p>
            </div>
          </div>

          {/* How Points Work */}
          <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 mb-3">How Points Work</p>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2 text-zinc-300">
                <StatusLED status="active" size="sm" />
                <span>1 point per $1 of labor value</span>
              </div>
              <div className="flex items-center gap-2 text-zinc-300">
                <StatusLED status="active" size="sm" />
                <span>5+ day streak = 1.1x bonus</span>
              </div>
              <div className="flex items-center gap-2 text-zinc-300">
                <StatusLED status="active" size="sm" />
                <span>10+ day streak = 1.25x bonus</span>
              </div>
              <div className="flex items-center gap-2 text-zinc-300">
                <StatusLED status="active" size="sm" />
                <span>Bigger jobs = more points!</span>
              </div>
            </div>
          </div>

          {/* Milestones */}
          <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 mb-3">Milestones</p>
            <div className="space-y-3">
              {[
                { pts: 1000, label: 'Rookie', icon: Wrench },
                { pts: 5000, label: 'Pro', icon: Star },
                { pts: 10000, label: 'Expert', icon: Trophy },
                { pts: 50000, label: 'Master', icon: Zap },
              ].map((m) => {
                const achieved = (stats?.total_points || 0) >= m.pts
                const IconComponent = m.icon
                return (
                  <div key={m.pts} className={`flex items-center gap-3 p-2 rounded-xl transition-all ${achieved ? 'bg-zinc-800/40' : 'opacity-40'}`}>
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${achieved ? 'bg-[var(--accent-500)]/20 border border-[var(--accent-500)]/30' : 'bg-zinc-800 border border-zinc-700/50'}`}>
                      <IconComponent className={`w-5 h-5 ${achieved ? 'text-[var(--accent-400)]' : 'text-zinc-600'}`} />
                    </div>
                    <div className="flex-1">
                      <p className={`font-medium ${achieved ? 'text-zinc-100' : 'text-zinc-500'}`}>{m.label}</p>
                      <p className="text-xs text-zinc-500">{m.pts.toLocaleString()} points</p>
                    </div>
                    {achieved && <StatusLED status="active" />}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
        {/* Spacer for bottom nav */}
        <div className="h-24" />
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
        <header className="bg-zinc-900/80 backdrop-blur-sm px-4 py-3 flex items-center gap-3 border-b border-zinc-700/50">
          <button onClick={() => setView('stats')} className="p-3 -ml-3 active:bg-zinc-800 rounded-xl">
            <ArrowLeft className="w-6 h-6 text-zinc-400" />
          </button>
          <h1 className="text-lg font-bold text-zinc-100">Request Rewards</h1>
        </header>

        <div className="p-4 space-y-4">
          {/* Available Points */}
          <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20 flex items-center justify-between">
            <span className="text-zinc-400">Available Points</span>
            <span className="text-2xl font-bold text-[var(--accent-400)]">{availablePoints.toLocaleString()}</span>
          </div>

          {/* Request Type Toggle */}
          <div className="flex gap-2 bg-zinc-900/80 backdrop-blur-sm p-1.5 rounded-2xl border border-zinc-700/50">
            <button
              onClick={() => setRequestType('pto')}
              className={`flex-1 py-3 rounded-xl font-medium flex items-center justify-center gap-2 transition-all ${
                requestType === 'pto' 
                  ? 'bg-[var(--accent-500)]/20 text-white border border-[var(--accent-500)]/50' 
                  : 'text-zinc-500 border border-transparent hover:text-zinc-300 hover:bg-zinc-800/40'
              }`}
            >
              <Calendar className="w-5 h-5" />
              PTO
            </button>
            <button
              onClick={() => setRequestType('cash')}
              className={`flex-1 py-3 rounded-xl font-medium flex items-center justify-center gap-2 transition-all ${
                requestType === 'cash' 
                  ? 'bg-emerald-500/20 text-white border border-emerald-500/50' 
                  : 'text-zinc-500 border border-transparent hover:text-zinc-300 hover:bg-zinc-800/40'
              }`}
            >
              <DollarSign className="w-5 h-5" />
              Cash
            </button>
          </div>

          {/* PTO Form */}
          {requestType === 'pto' && (
            <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20 space-y-4">
              <p className="text-sm text-zinc-400">Select your PTO dates (8,000 pts/day)</p>
              
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-2">Start Date</label>
                  <input
                    type="date"
                    value={ptoStartDate}
                    onChange={(e) => setPtoStartDate(e.target.value)}
                    min={format(new Date(), 'yyyy-MM-dd')}
                    className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-2">End Date</label>
                  <input
                    type="date"
                    value={ptoEndDate}
                    onChange={(e) => setPtoEndDate(e.target.value)}
                    min={ptoStartDate || format(new Date(), 'yyyy-MM-dd')}
                    className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all"
                  />
                </div>
              </div>

              {ptoDays > 0 && (
                <div className="bg-zinc-800/60 rounded-xl p-3 border border-zinc-700/50">
                  <div className="flex justify-between text-sm">
                    <span className="text-zinc-400">Days requested</span>
                    <span className="text-zinc-100 font-medium">{ptoDays}</span>
                  </div>
                  <div className="flex justify-between text-sm mt-1">
                    <span className="text-zinc-400">Points needed</span>
                    <span className={ptoPointsNeeded <= availablePoints ? 'text-emerald-400' : 'text-red-400'}>
                      {ptoPointsNeeded.toLocaleString()}
                    </span>
                  </div>
                </div>
              )}

              <textarea
                value={requestNotes}
                onChange={(e) => setRequestNotes(e.target.value)}
                placeholder="Notes (optional)"
                className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 resize-none focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all"
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
                className="w-full py-4 bg-[var(--accent-600)] hover:bg-[var(--accent-500)] disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-all flex items-center justify-center gap-2 border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)]"
              >
                {createRequestMutation.isPending ? <Spinner size="sm" /> : <Calendar className="w-5 h-5" />}
                Request PTO
              </button>
            </div>
          )}

          {/* Cash Form */}
          {requestType === 'cash' && (
            <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20 space-y-4">
              <p className="text-sm text-zinc-400">Cash out your points ($0.0375/pt)</p>
              
              <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4 text-center">
                <p className="text-emerald-400 text-sm">You can cash out</p>
                <p className="text-3xl font-bold text-zinc-100">${cashValue}</p>
                <p className="text-emerald-400/60 text-xs mt-1">({availablePoints.toLocaleString()} points)</p>
              </div>

              <textarea
                value={requestNotes}
                onChange={(e) => setRequestNotes(e.target.value)}
                placeholder="Notes (optional)"
                className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 resize-none focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all"
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
                className="w-full py-4 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-all flex items-center justify-center gap-2 border border-emerald-400/50 hover:shadow-[0_0_24px_rgba(16,185,129,0.5)]"
              >
                {createRequestMutation.isPending ? <Spinner size="sm" /> : <DollarSign className="w-5 h-5" />}
                Request Cash Out
              </button>
            </div>
          )}

          {/* My Requests */}
          {myRequests && myRequests.length > 0 && (
            <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20">
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 mb-3">My Requests</p>
              <div className="space-y-2">
                {myRequests.map((req) => (
                  <div key={req.id} className="bg-zinc-800/60 rounded-xl p-3 border border-zinc-700/50">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {req.request_type === 'pto' ? (
                          <Calendar className="w-4 h-4 text-[var(--accent-400)]" />
                        ) : (
                          <DollarSign className="w-4 h-4 text-emerald-400" />
                        )}
                        <span className="text-zinc-100 font-medium">
                          {req.request_type === 'pto' 
                            ? `${req.pto_days} day${req.pto_days !== 1 ? 's' : ''} PTO`
                            : `$${req.cash_value?.toFixed(2)} cash`
                          }
                        </span>
                      </div>
                      <span className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
                        req.status === 'pending' ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' :
                        req.status === 'approved' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' :
                        req.status === 'denied' ? 'bg-red-500/20 text-red-400 border-red-500/30' :
                        'bg-zinc-800 text-zinc-400 border-zinc-700/50'
                      }`}>
                        {req.status === 'pending' && <StatusLED status="warning" size="sm" />}
                        {req.status === 'approved' && <StatusLED status="active" size="sm" />}
                        {req.status === 'denied' && <StatusLED status="error" size="sm" />}
                        {req.status}
                      </span>
                    </div>
                    {req.request_type === 'pto' && req.pto_start_date && (
                      <p className="text-xs text-zinc-500 mt-1">
                        {format(new Date(req.pto_start_date), 'MMM d')} - {format(new Date(req.pto_end_date!), 'MMM d, yyyy')}
                      </p>
                    )}
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-xs text-zinc-500">
                        {format(new Date(req.created_at), 'MMM d, yyyy')}
                      </span>
                      {req.status === 'pending' && (
                        <button
                          onClick={() => cancelRequestMutation.mutate(req.id)}
                          className="text-xs text-red-400 hover:text-red-300 transition-colors"
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                    {req.manager_notes && (
                      <p className="text-xs text-zinc-400 mt-2 italic bg-zinc-800/40 rounded-lg p-2">"{req.manager_notes}"</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        {/* Spacer for bottom nav */}
        <div className="h-24" />
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
        <header className="bg-zinc-900/80 backdrop-blur-sm px-4 py-3 flex items-center gap-3 border-b border-zinc-700/50">
          <button onClick={() => setView('list')} className="p-3 -ml-3 active:bg-zinc-800 rounded-xl">
            <ArrowLeft className="w-6 h-6 text-zinc-400" />
          </button>
          <h1 className="text-lg font-bold text-zinc-100">Profile Settings</h1>
        </header>

        <div className="p-4 space-y-6 pb-24">
          {/* Profile Info */}
          <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-zinc-100 font-semibold">Personal Information</h2>
              {!isEditingProfile && (
                <button
                  onClick={() => {
                    setFirstName(user?.first_name || '')
                    setLastName(user?.last_name || '')
                    setEmail(user?.email || '')
                    setPhone(user?.phone || '')
                    setIsEditingProfile(true)
                  }}
                  className="px-4 py-2 text-sm bg-[var(--accent-600)] hover:bg-[var(--accent-500)] text-white rounded-xl transition-all border border-[var(--accent-400)]/50 hover:shadow-[0_0_16px_var(--accent-500)]"
                >
                  Edit
                </button>
              )}
            </div>
            
            {!isEditingProfile ? (
              <div className="space-y-3">
                <div>
                  <div className="text-xs font-medium text-zinc-400 mb-1">Name</div>
                  <div className="text-zinc-100">{user?.first_name} {user?.last_name}</div>
                </div>
                <div>
                  <div className="text-xs font-medium text-zinc-400 mb-1">Email</div>
                  <div className="text-zinc-100">{user?.email}</div>
                </div>
                {user?.phone && (
                  <div>
                    <div className="text-xs font-medium text-zinc-400 mb-1">Phone</div>
                    <div className="text-zinc-100">{user?.phone}</div>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-2">First Name</label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all hover:border-zinc-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-2">Last Name</label>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all hover:border-zinc-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-2">Email Address</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all hover:border-zinc-500"
                />
                <p className="text-xs text-zinc-500 mt-1">This is your login email</p>
                {email !== originalEmail && (
                  <div className="mt-2 bg-[var(--accent-500)]/10 border border-[var(--accent-500)]/30 rounded-xl p-3">
                    <p className="text-[var(--accent-400)] text-xs">
                      You'll receive a verification link at the new email
                    </p>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-2">Phone</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="(555) 123-4567"
                  className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all hover:border-zinc-500"
                />
              </div>

              {/* Password confirmation - shown when email is changing */}
              {email !== originalEmail && (
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-2">Confirm Password</label>
                  <div className="relative">
                    <input
                      type={showProfilePassword ? 'text' : 'password'}
                      value={profilePassword}
                      onChange={(e) => setProfilePassword(e.target.value)}
                      placeholder="Enter your current password"
                      className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all hover:border-zinc-500 pr-12"
                    />
                    <button
                      type="button"
                      onClick={() => setShowProfilePassword(!showProfilePassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-100 p-1 transition-colors"
                    >
                      {showProfilePassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <p className="text-xs text-amber-400 mt-1">
                    Password required for security
                  </p>
                </div>
              )}

                <div className="flex gap-2 pt-2">
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
                    className="flex-1 py-3 bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-semibold rounded-xl transition-all border border-zinc-600/50 hover:border-zinc-500"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleProfileUpdate}
                    disabled={updateProfileMutation.isPending}
                    className="flex-1 py-3 bg-[var(--accent-600)] hover:bg-[var(--accent-500)] disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2 border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)]"
                  >
                    {updateProfileMutation.isPending ? <Spinner size="sm" /> : <CheckCircle className="w-5 h-5" />}
                    Save
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Change Password */}
          <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-zinc-100 font-semibold">Change Password</h2>
              {!isChangingPassword && (
                <button
                  onClick={() => {
                    setCurrentPassword('')
                    setNewPassword('')
                    setConfirmPassword('')
                    setIsChangingPassword(true)
                  }}
                  className="px-4 py-2 text-sm bg-amber-600 hover:bg-amber-500 text-white rounded-xl transition-all border border-amber-400/50 hover:shadow-[0_0_16px_rgba(251,191,36,0.4)]"
                >
                  Change
                </button>
              )}
            </div>
            
            {isChangingPassword && (
              <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-2">Current Password</label>
                <div className="relative">
                  <input
                    type={showCurrentPassword ? 'text' : 'password'}
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all hover:border-zinc-500 pr-12"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-100 p-1 transition-colors"
                  >
                    {showCurrentPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-2">New Password</label>
                <div className="relative">
                  <input
                    type={showNewPassword ? 'text' : 'password'}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all hover:border-zinc-500 pr-12"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-100 p-1 transition-colors"
                  >
                    {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-xs text-zinc-500 mt-1">Min 8 characters</p>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-2">Confirm New Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all hover:border-zinc-500"
                />
              </div>

                <div className="flex gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setCurrentPassword('')
                      setNewPassword('')
                      setConfirmPassword('')
                      setIsChangingPassword(false)
                    }}
                    className="flex-1 py-3 bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-semibold rounded-xl transition-all border border-zinc-600/50 hover:border-zinc-500"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handlePasswordChange}
                    disabled={changePasswordMutation.isPending || !currentPassword || !newPassword || !confirmPassword}
                    className="flex-1 py-3 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2 border border-amber-400/50 hover:shadow-[0_0_24px_rgba(251,191,36,0.4)]"
                  >
                    {changePasswordMutation.isPending ? <Spinner size="sm" /> : <CheckCircle className="w-5 h-5" />}
                    Change
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Appearance Settings */}
          <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Palette className="w-5 h-5 text-[var(--accent-400)]" />
                <h2 className="text-zinc-100 font-semibold">Appearance</h2>
              </div>
              <button
                onClick={resetToDefaults}
                className="p-2 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-xl transition-all"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
            </div>
            
            {/* Accent Color */}
            <div className="mb-4">
              <label className="block text-xs font-medium text-zinc-400 mb-2">Accent Color</label>
              <div className="flex gap-2">
                {ACCENT_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    onClick={() => setAccent(option.id)}
                    className={`w-10 h-10 rounded-full flex items-center justify-center transition-all ${
                      accent === option.id ? 'ring-2 ring-offset-2 ring-offset-zinc-900 ring-white scale-110' : 'hover:scale-105'
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
              <label className="block text-xs font-medium text-zinc-400 mb-2">Font Size</label>
              <div className="flex gap-2">
                {FONT_SIZE_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    onClick={() => setFontSize(option.id)}
                    className={`flex-1 py-2.5 px-3 rounded-xl text-xs font-semibold transition-all ${
                      fontSize === option.id
                        ? 'bg-[var(--accent-500)] text-white border border-[var(--accent-400)]/50 shadow-[0_0_12px_var(--accent-500)/40]'
                        : 'bg-zinc-800/80 text-zinc-300 hover:bg-zinc-700 border border-zinc-600/50'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20">
            <h2 className="text-zinc-100 font-semibold">Session</h2>
            <p className="text-sm text-zinc-400 mt-1">Sign out from this device.</p>
            <button
              onClick={handleLogout}
              className="w-full mt-4 py-4 bg-red-950/80 hover:bg-red-900 active:scale-[0.98] text-red-400 text-base font-semibold rounded-xl transition-all flex items-center justify-center gap-2 border border-red-800/50 hover:border-red-600"
            >
              <LogOut className="w-4 h-4" />
              Sign Out
            </button>
          </div>
        </div>
        {/* Spacer for bottom nav */}
        <div className="h-24" />
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
      <header className="bg-zinc-900/80 backdrop-blur-sm px-4 py-3 border-b border-zinc-700/50">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-zinc-400">Hey, {user?.first_name}!</p>
            <h1 className="text-xl font-bold text-zinc-100">My Jobs</h1>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setView('stats')}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-full transition-colors active:opacity-70 bg-[var(--accent-500)]/20 border border-[var(--accent-500)]/30"
            >
              <Star className="w-5 h-5 text-[var(--accent-400)]" />
              <span className="font-bold text-base text-[var(--accent-400)]">{stats?.available_points || 0}</span>
            </button>
            {isClockedIn ? (
              <button
                onClick={handleHeaderClockOutAction}
                className="p-3 text-zinc-400 active:text-amber-300 active:bg-zinc-800 rounded-xl"
                title="Clock Out"
              >
                <LogOut className="w-6 h-6" />
              </button>
            ) : null}
          </div>
        </div>
      </header>

      {/* Quick Stats Bar */}
      {isClockedIn && !isOnBreak && (
        <div className="bg-zinc-900/60 backdrop-blur-sm px-4 py-2 flex items-center gap-4 border-b border-zinc-700/50">
          <div className="flex items-center gap-1.5 text-sm">
            <span className="text-zinc-500">Today:</span>
            <span className="text-zinc-100 font-medium">{stats?.jobs_completed_today || 0} done</span>
          </div>
          {(stats?.streak_days || 0) > 0 && (
            <div className="flex items-center gap-1.5 text-sm">
              <Zap className="w-4 h-4 text-amber-400" />
              <span className="text-amber-400 font-medium">{stats?.streak_days} day streak</span>
            </div>
          )}
        </div>
      )}

      <main className="p-4 space-y-4 pb-44">
        {/* Real-time notification banners */}
        <NotificationBanner
          banners={banners}
          onDismiss={dismissBanner}
          onDismissAll={clearBanners}
          autoDismissMs={8000}
        />

        {!daySummary ? (
          <div className="flex items-center justify-center py-10">
            <Spinner size="lg" />
          </div>
        ) : null}

        {daySummary && !isClockedIn ? (
          <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-5 border border-zinc-700/50 shadow-xl shadow-black/20 space-y-4">
            <div className="flex items-start gap-3">
              <StatusLED status="inactive" />
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500">Morning Start</p>
                <h2 className="text-2xl font-semibold text-zinc-100 mt-1">Clock in to start your day</h2>
                <p className="text-sm text-zinc-400 mt-1">
                  Shift {daySummary.shift_start_local} - {daySummary.shift_end_local} · Core target {(daySummary.core_target_minutes / 60).toFixed(1)}h
                </p>
              </div>
            </div>
            <button
              onClick={handleAttendanceToggle}
              disabled={attendanceToggleBusy}
              className="w-full py-5 text-white text-xl font-bold rounded-2xl transition-all disabled:opacity-50 disabled:cursor-not-allowed bg-emerald-600 active:bg-emerald-700 hover:shadow-[0_0_24px_rgba(16,185,129,0.5)] shadow-lg shadow-emerald-500/25"
            >
              {attendanceToggleBusy ? 'Clocking In...' : 'Clock In'}
            </button>
          </div>
        ) : null}

        {daySummary && isClockedIn ? (
          <>
            {isTimerPanelExpanded ? (
              <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20 space-y-3">
                <button onClick={handleTimerPanelToggle} className="flex items-center justify-between w-full active:opacity-70">
                  <div className="flex items-center gap-2">
                    <StatusLED status="active" />
                    <span className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500">Timer Panel</span>
                  </div>
                  <span className="text-sm text-[var(--accent-400)] font-medium">▲ Collapse</span>
                </button>
            {isOnBreak ? (
              <>
                <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <StatusLED status="warning" />
                      <span className="text-xs font-bold uppercase tracking-[0.2em] text-amber-300">Break Time</span>
                    </div>
                    <span className="font-mono text-lg font-semibold text-amber-100">{formatSecondsAsClock(breakElapsedSeconds)}</span>
                  </div>
                </div>
                <button
                  onClick={handleBreakToggle}
                  disabled={breakToggleBusy}
                  className="w-full py-4 text-white text-base font-semibold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed bg-[var(--accent-600)] active:bg-[var(--accent-500)] hover:shadow-[0_0_24px_var(--accent-500)]"
                >
                  {breakToggleBusy ? 'Ending Break...' : 'End Break'}
                </button>
              </>
            ) : (
              <>
                {/*
                 * Timer Language Alternatives (documented for future reference):
                 *
                 * Option A (current): Progress Toward Goal
                 *   - "Today's Progress", "Xh logged", "Xh toward your Yh goal"
                 *   - Pro: Supportive, feels like progress tracking not surveillance
                 *
                 * Option B: Earnings/Value Focus
                 *   - "You've logged $480 in billable work today"
                 *   - Requires: labor rates per service, calculation logic
                 *   - Pro: Directly ties work to value
                 *   - Con: May feel transactional; needs rate data
                 *
                 * Option C: Minimal Display
                 *   - Default: Just show active timer (no metrics)
                 *   - Expand to see day summary
                 *   - Pro: Least intrusive
                 *   - Con: Loses at-a-glance progress visibility
                 *
                 * Option D: Gamification
                 *   - "5-day streak! Keep it going"
                 *   - Daily achievements: "First job done before 9am"
                 *   - Pro: Engaging, positive reinforcement
                 *   - Con: May feel patronizing; already have rewards system
                 */}
                {/* Today's Progress — positive framing */}
                <div>
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className="text-zinc-400">Today's Progress</span>
                    <span className="font-mono text-sm font-semibold text-[var(--accent-400)]">{(daySummary.tracked_minutes / 60).toFixed(1)}h logged</span>
                  </div>
                  <div className="h-2.5 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-2.5 bg-[var(--accent-500)] rounded-full transition-all"
                      style={{ width: `${daySummary.core_target_minutes > 0 ? Math.min((daySummary.tracked_minutes / daySummary.core_target_minutes) * 100, 100) : 0}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-zinc-500 mt-1">
                    {daySummary.tracked_minutes >= daySummary.core_target_minutes
                      ? <span className="text-emerald-400">Great day! You've hit your {(daySummary.core_target_minutes / 60).toFixed(1)}h goal</span>
                      : <span>{(daySummary.tracked_minutes / 60).toFixed(1)}h toward your {(daySummary.core_target_minutes / 60).toFixed(1)}h goal</span>
                    }
                  </div>
                </div>

                {/* Misc task pills — horizontal scroll */}
                <div className="flex items-center gap-2 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-hide">
                  {MISC_WORK_OPTIONS.map((option) => {
                    const isSelected = miscCategory === option.value
                    const isSuggestedPick = isMiscSuggestion && !hasActiveDayTimer && isSelected
                    return (
                      <button
                        key={option.value}
                        type="button"
                        disabled={isActiveRoTimer}
                        onClick={() => setMiscCategory(option.value)}
                        className={`shrink-0 px-4 py-2.5 rounded-full border text-sm font-medium transition-all whitespace-nowrap ${
                          isSuggestedPick
                            ? 'bg-[var(--accent-500)]/30 border-[var(--accent-400)] text-white ring-1 ring-[var(--accent-400)]/60 animate-pulse'
                            : isSelected
                            ? 'bg-[var(--accent-500)]/30 border-[var(--accent-400)] text-white'
                            : 'bg-zinc-800/60 border-zinc-600/50 text-zinc-300 active:bg-zinc-700'
                        } disabled:opacity-40 disabled:cursor-not-allowed`}
                      >
                        {option.label}
                      </button>
                    )
                  })}
                </div>

                {/* Timer toggle — shows selected category */}
                <button
                  onClick={handleTimerToggle}
                  disabled={timerToggleBusy || (isActiveRoTimer && !hasActiveDayTimer)}
                  className={`w-full py-4 text-white text-base font-semibold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                    hasActiveDayTimer 
                      ? 'bg-red-950/80 text-red-400 border border-red-800/50 hover:bg-red-900 hover:border-red-600' 
                      : 'bg-[var(--accent-600)] border border-[var(--accent-400)]/50 hover:bg-[var(--accent-500)] hover:shadow-[0_0_24px_var(--accent-500)]'
                  } ${shouldPulseTimerToggle ? 'ring-2 ring-[var(--accent-400)]/70 animate-pulse' : ''}`}
                >
                  {timerToggleBusy
                    ? (hasActiveDayTimer ? 'Stopping...' : 'Starting...')
                    : hasActiveDayTimer
                      ? 'Stop Active Timer'
                      : `Start ${MISC_WORK_OPTIONS.find((o) => o.value === miscCategory)?.label || 'Misc'} Timer`}
                </button>

                {/* Break button */}
                {showPanelBreakControl ? (
                  <button
                    onClick={handleBreakToggle}
                    disabled={breakToggleBusy}
                    className="w-full py-4 text-white text-base font-semibold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed bg-amber-600 border border-amber-400/50 hover:bg-amber-500 hover:shadow-[0_0_24px_rgba(251,191,36,0.5)]"
                  >
                    {breakToggleBusy ? 'Starting Break...' : 'Start Break'}
                  </button>
                ) : null}

                {/* Collapsible breakdown */}
                <details className="rounded-xl border border-zinc-700/50 bg-zinc-800/40 p-3 text-xs">
                  <summary className="cursor-pointer text-zinc-300 font-medium">Time breakdown</summary>
                  <div className="pt-2 space-y-2">
                    <div className="grid grid-cols-3 gap-2 text-zinc-400">
                      <div>Jobs: <span className="text-zinc-100 font-semibold">{(daySummary.ro_minutes / 60).toFixed(1)}h</span></div>
                      <div>Misc: <span className="text-zinc-100 font-semibold">{(daySummary.misc_minutes / 60).toFixed(1)}h</span></div>
                      <div>Break: <span className="text-zinc-100 font-semibold">{(daySummary.break_minutes / 60).toFixed(1)}h</span></div>
                    </div>
                    <input
                      value={miscNote}
                      onChange={(e) => setMiscNote(e.target.value)}
                      placeholder="Misc note (optional)"
                      className="w-full bg-zinc-800/60 border border-zinc-600/50 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all"
                      disabled={isActiveRoTimer}
                    />
                  </div>
                </details>
              </>
            )}
          </div>
        ) : (
          <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl border border-zinc-700/50 shadow-xl shadow-black/20">
                {/* Tappable status + timer area */}
                <button
                  onClick={handleTimerPanelToggle}
                  className="w-full p-4 active:opacity-70"
                >
                  {/* Row 1: status badges */}
                  <div className="flex items-center gap-2 text-xs mb-2">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 font-medium border border-emerald-500/30">
                      <StatusLED status="active" size="sm" />
                      Clocked In
                    </span>
                    {isOnBreak ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-300 font-medium border border-amber-500/30">
                        <StatusLED status="warning" size="sm" />
                        On Break
                      </span>
                    ) : daySummary.active_session ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 font-medium border border-emerald-500/30">
                        <StatusLED status="active" size="sm" />
                        Timer On
                      </span>
                    ) : (
                      <span className="px-2.5 py-1 rounded-full bg-zinc-800 text-zinc-400 font-medium border border-zinc-700/50">Idle</span>
                    )}
                    <span className="ml-auto text-[11px] text-[var(--accent-400)] font-medium">▼ Expand</span>
                  </div>
                  {/* Row 2: prominent timer */}
                  <div className={`font-mono text-3xl font-bold tracking-tight ${isOnBreak ? 'text-amber-200' : hasActiveDayTimer ? 'text-emerald-300' : 'text-zinc-300'}`}>
                    {collapsedInlineTimerLabel}
                  </div>
                </button>

                {/* Quick actions below the tappable area */}
                {(!hasActiveDayTimer && !isOnBreak) || isOnBreak ? (
                  <div className="px-4 pb-4 pt-0">
                    {/* Quick actions when idle (no active timer, not on break) */}
                    {!hasActiveDayTimer && !isOnBreak && (
                      <div className="flex gap-2">
                        <button
                          onClick={handleTimerToggle}
                          disabled={timerToggleBusy}
                          className="flex-1 py-3 text-white text-sm font-semibold rounded-xl bg-[var(--accent-600)] border border-[var(--accent-400)]/50 active:bg-[var(--accent-500)] disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:shadow-[0_0_24px_var(--accent-500)]"
                        >
                          {timerToggleBusy ? 'Starting...' : 'Start Misc Timer'}
                        </button>
                        <button
                          onClick={handleBreakToggle}
                          disabled={breakToggleBusy}
                          className="py-3 px-5 text-white text-sm font-semibold rounded-xl bg-amber-600 border border-amber-400/50 active:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                        >
                          Break
                        </button>
                      </div>
                    )}
                    {/* End break button when on break */}
                    {isOnBreak && (
                      <button
                        onClick={handleBreakToggle}
                        disabled={breakToggleBusy}
                        className="w-full py-3 text-white text-sm font-semibold rounded-xl bg-[var(--accent-600)] border border-[var(--accent-400)]/50 active:bg-[var(--accent-500)] disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:shadow-[0_0_24px_var(--accent-500)]"
                      >
                        {breakToggleBusy ? 'Ending Break...' : 'End Break'}
                      </button>
                    )}
                  </div>
                ) : null}
          </div>
        )}
          </>
        ) : null}

        {isClockedIn && !isOnBreak && (isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : activeJobs.length === 0 && pendingReview.length === 0 ? (
          <>
            {/* No Active Jobs - Show Stats Instead */}
            <div className="text-center py-8">
              <div className="w-20 h-20 bg-zinc-900/80 backdrop-blur-sm rounded-full flex items-center justify-center mx-auto mb-4 border border-zinc-700/50">
                <Wrench className="w-10 h-10 text-zinc-600" />
              </div>
              <p className="text-zinc-300 text-lg font-semibold">All caught up!</p>
              <p className="text-zinc-600 text-sm mt-1">No active jobs right now</p>
            </div>

            {/* Quick Stats */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 text-center shadow-xl shadow-black/20">
                <p className="text-2xl font-bold text-zinc-100">{stats?.jobs_completed_today || 0}</p>
                <p className="text-xs text-zinc-500 uppercase">Today</p>
              </div>
              <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 text-center shadow-xl shadow-black/20">
                <p className="text-2xl font-bold text-zinc-100">{stats?.jobs_completed_week || 0}</p>
                <p className="text-xs text-zinc-500 uppercase">This Week</p>
              </div>
              <div className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 text-center shadow-xl shadow-black/20">
                <p className="text-2xl font-bold text-zinc-100">{stats?.jobs_completed_month || 0}</p>
                <p className="text-xs text-zinc-500 uppercase">This Month</p>
              </div>
            </div>

            {/* Recent Completed */}
            {history && history.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm text-zinc-400 font-medium">Recent Completed</h3>
                  <button
                    onClick={() => setView('history')}
                    className="text-xs text-[var(--accent-400)] hover:opacity-80 transition-opacity"
                  >
                    View All →
                  </button>
                </div>
                <div className="space-y-2">
                  {history.slice(0, 3).map((item) => (
                    <div key={item.id} className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-3 border border-zinc-700/50 shadow-xl shadow-black/20">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <p className="text-zinc-100 font-medium text-sm">{item.vehicle_info}</p>
                          <p className="text-xs text-zinc-500 mt-0.5">{item.order_number}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-emerald-400 bg-emerald-500/20 px-2.5 py-1 rounded-full border border-emerald-500/30">
                            +{item.points_earned.toLocaleString()} pts
                          </span>
                          <StatusLED status="active" size="sm" />
                        </div>
                      </div>
                      <p className="text-xs text-zinc-600 mt-1">
                        {format(new Date(item.completed_at), 'MMM d, h:mm a')}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </>
        ) : (
          <>
            {/* Active Jobs - Expandable Cards */}
            {activeJobs.length > 0 && (
              <div className="flex items-center gap-2 mb-1">
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500">Active Jobs</p>
                <SectionInfoTooltip text="Jobs you can accept, resume, or complete. Expanding a card shows services, photos, and job actions." />
              </div>
            )}
            {activeJobs.map((job) => {
              const isNew = job.status === 'assigned'
              const isWorking = job.status === 'in_progress'
              const isExpanded = expandedJobId === job.id
              const isSuggestedJob = highlightedJobId === job.id
              const detail = isExpanded ? expandedJobDetail : null
              const isTimedForThisJob = daySummary?.active_session?.session_type === 'repair_order'
                && daySummary.active_session.repair_order_id === job.id
              const timedStartForJob = daySummary?.active_session?.started_at || detail?.work_started_at || null
              
              // Status-based accent color using design system
              const borderColor = isSuggestedJob ? 'border-[var(--accent-400)]' : isWorking ? 'border-emerald-500/50' : isNew ? 'border-[var(--accent-500)]/50' : 'border-zinc-700/50'
              const statusLedStatus = isWorking ? 'active' : isNew ? 'info' : 'inactive'
              
              return (
                <div 
                  key={job.id}
                  ref={isSuggestedJob ? suggestedJobRef : undefined}
                  className={`rounded-2xl overflow-hidden bg-zinc-900/80 backdrop-blur-sm border ${borderColor} shadow-xl shadow-black/20 transition-all ${isSuggestedJob ? 'shadow-[0_0_16px_var(--accent-500)/30] ring-1 ring-[var(--accent-400)]/50' : ''} ${isExpanded ? 'border-[var(--accent-500)]/40' : ''}`}
                >
                  {/* Header - Always visible */}
                  <button
                    onClick={() => toggleExpand(job.id)}
                    className="w-full p-4 text-left transition-all active:scale-[0.99]"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        {/* Status LED indicator */}
                        <StatusLED status={statusLedStatus} pulse={isWorking || isSuggestedJob} />
                        <div className="min-w-0 flex-1">
                          <h3 className="text-zinc-100 font-semibold truncate">{job.vehicle_info}</h3>
                          <p className="text-sm text-zinc-400">
                            {job.services_count} service{job.services_count !== 1 ? 's' : ''} · {job.order_number}
                          </p>
                          <p className="text-xs text-zinc-500 mt-0.5">Created {formatCreatedAt(job.created_at)}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {isSuggestedJob ? (
                          <span className="px-2 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wide text-white bg-[var(--accent-500)] border border-[var(--accent-400)]/50 animate-pulse">
                            Next
                          </span>
                        ) : null}
                        {job.hold_reason ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium text-amber-200 bg-amber-500/20 border border-amber-500/30">
                            <StatusLED status="warning" size="sm" />
                            On Hold
                          </span>
                        ) : (
                          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                            isWorking 
                              ? 'text-emerald-300 bg-emerald-500/20 border-emerald-500/30' 
                              : isNew 
                                ? 'text-white bg-[var(--accent-500)]/30 border-[var(--accent-400)]/50' 
                                : 'text-zinc-300 bg-zinc-800 border-zinc-700/50'
                          }`}>
                            {STATUS_LABELS[job.status]}
                          </span>
                        )}
                        <ChevronDown className={`w-5 h-5 text-zinc-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
                      </div>
                    </div>
                  </button>
                  
                  {/* Expanded Content */}
                  <div className={`overflow-hidden transition-all duration-200 ${
                    isExpanded ? 'max-h-[800px] opacity-100' : 'max-h-0 opacity-0'
                  }`}>
                    <div className="px-4 pb-4 space-y-3 border-t border-zinc-700/50 pt-3">
                      {expandedJobLoading ? (
                        <div className="flex justify-center py-6">
                          <Spinner size="md" />
                        </div>
                      ) : detail ? (
                        <>
                          {/* Live Timer */}
                          {isWorking && isTimedForThisJob && timedStartForJob && (
                            <LiveTimer
                              startedAt={timedStartForJob}
                              totalMinutesToday={detail?.ro_today_tracked_minutes ?? job.ro_today_tracked_minutes}
                            />
                          )}
                          {isWorking && !isTimedForThisJob && (
                            <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-xs text-amber-300 flex items-center gap-2">
                              <StatusLED status="warning" size="sm" />
                              In-progress job is currently not timed. Resume timer for this repair order.
                            </div>
                          )}
                          
                          {/* Services List */}
                          {detail.services.length > 0 && (
                            <div>
                              <p className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 mb-2">Services</p>
                              <div className="space-y-1.5">
                                {detail.services.map((svc, idx) => (
                                  <div 
                                    key={idx} 
                                    className="flex items-center gap-2 text-sm"
                                  >
                                    <Wrench className="w-3.5 h-3.5 text-[var(--accent-400)] shrink-0" />
                                    <span className="text-zinc-200">{svc.name}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          
                          {/* Work Photos Section */}
                          {['assigned', 'acknowledged', 'in_progress'].includes(job.status) && (
                            <div>
                              <div className="flex items-center justify-between mb-2">
                                <p className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500">Photos</p>
                                <label className="p-2.5 rounded-xl bg-zinc-800/60 border border-zinc-600/50 active:bg-zinc-700 cursor-pointer transition-all hover:border-zinc-500">
                                  <Camera className="w-5 h-5 text-zinc-300" />
                                  <input
                                    type="file"
                                    accept="image/*"
                                    multiple
                                    className="hidden"
                                    onChange={handlePhotoSelect}
                                    ref={fileInputRef}
                                  />
                                </label>
                              </div>
                              
                              {/* Photo Preview */}
                              {selectedPhotoPreviews.length > 0 && (
                                <div className="rounded-xl bg-zinc-800/60 border border-zinc-700/50 p-3 mb-2">
                                  <div className="relative grid grid-cols-3 gap-1.5">
                                    {selectedPhotoPreviews.map((photo) => (
                                      <img
                                        key={`${photo.name}-${photo.dataUrl.slice(0, 24)}`}
                                        src={photo.dataUrl}
                                        alt={photo.name}
                                        className="aspect-square w-full rounded-lg object-cover"
                                      />
                                    ))}
                                    <button
                                      onClick={() => { setSelectedPhotoPreviews([]); setPhotoCaption('') }}
                                      className="absolute top-1.5 right-1.5 p-1.5 bg-black/60 rounded-full hover:bg-black/80 transition-colors"
                                    >
                                      <X className="w-3 h-3 text-white" />
                                    </button>
                                  </div>
                                  <input
                                    type="text"
                                    placeholder="Add note..."
                                    value={photoCaption}
                                    onChange={(e) => setPhotoCaption(e.target.value)}
                                    className="w-full mt-2 px-4 py-2 rounded-xl bg-zinc-800/60 border border-zinc-600/50 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] transition-all"
                                  />
                                  <button
                                    onClick={handlePhotoUpload}
                                    disabled={isUploadingPhoto}
                                    className="w-full mt-2 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-xl flex items-center justify-center gap-1.5 transition-all hover:shadow-[0_0_16px_rgba(16,185,129,0.4)]"
                                  >
                                    {isUploadingPhoto ? <Spinner size="xs" /> : <Camera className="w-3.5 h-3.5" />}
                                    Upload {selectedPhotoPreviews.length} photo{selectedPhotoPreviews.length === 1 ? '' : 's'}
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
                                        className="w-full aspect-square object-cover rounded-lg"
                                      />
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          if (confirm('Delete this photo?')) {
                                            deletePhotoMutation.mutate({ jobId: job.id, photoId: photo.id })
                                          }
                                        }}
                                        className="absolute top-0.5 right-0.5 p-1 bg-black/60 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                                      >
                                        <X className="w-2.5 h-2.5 text-white" />
                                      </button>
                                    </div>
                                  ))}
                                </div>
                              )}
                              
                              {/* Empty state */}
                              {(!workPhotos || workPhotos.length === 0) && selectedPhotoPreviews.length === 0 && (
                                <p className="text-xs text-zinc-600 text-center py-2">No photos</p>
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
                                className="w-full py-3 bg-[var(--accent-600)] hover:bg-[var(--accent-500)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2 border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)]"
                              >
                                {isPending ? <Spinner size="sm" /> : <PlayCircle className="w-5 h-5" />}
                                ACCEPT & START
                              </button>
                            )}
                            
                            {job.status === 'in_progress' && job.hold_reason && (
                              <div className="space-y-2">
                                <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-3 flex items-center gap-2">
                                  <StatusLED status="warning" size="sm" />
                                  <span className="text-sm text-amber-200">
                                    On hold: {HOLD_REASON_LABELS[job.hold_reason || ''] || job.hold_reason}
                                  </span>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      resumeOrderMutation.mutate(job.id)
                                    }}
                                    disabled={isPending}
                                    className="w-full py-3 bg-[var(--accent-600)] hover:bg-[var(--accent-500)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2 border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)]"
                                  >
                                    {isPending ? <Spinner size="sm" /> : <PlayCircle className="w-5 h-5" />}
                                    RESUME
                                  </button>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      completeWorkMutation.mutate(job.id)
                                    }}
                                    disabled={isPending}
                                    className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2 border border-emerald-400/50 hover:shadow-[0_0_24px_rgba(16,185,129,0.5)]"
                                  >
                                    {isPending ? <Spinner size="sm" /> : <CheckCircle className="w-5 h-5" />}
                                    JOB DONE
                                  </button>
                                </div>
                              </div>
                            )}

                            {job.status === 'in_progress' && !job.hold_reason && (
                              <div className="space-y-2">
                                {holdTarget === job.id ? (
                                  <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
                                    <p className="text-xs text-zinc-400 font-medium">Why are you pausing?</p>
                                    <div className="flex flex-wrap gap-2">
                                      {HOLD_REASONS.map((r) => (
                                        <button
                                          key={r.value}
                                          type="button"
                                          onClick={() => setHoldReason(r.value)}
                                          className={`px-4 py-2.5 rounded-full border text-sm font-medium transition-all ${
                                            holdReason === r.value
                                              ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                                              : 'bg-zinc-800/60 border-zinc-600/50 text-zinc-300 active:bg-zinc-700'
                                          }`}
                                        >
                                          {r.label}
                                        </button>
                                      ))}
                                    </div>
                                    <div className="grid grid-cols-2 gap-2">
                                      <button
                                        onClick={() => { setHoldTarget(null); setHoldReason('') }}
                                        className="py-3 bg-zinc-800/80 hover:bg-zinc-700 active:scale-[0.98] text-zinc-300 text-sm font-semibold rounded-xl transition-all border border-zinc-600/50"
                                      >
                                        Cancel
                                      </button>
                                      <button
                                        onClick={() => holdReason && holdOrderMutation.mutate({ orderId: job.id, reason: holdReason })}
                                        disabled={!holdReason || holdOrderMutation.isPending}
                                        className="py-3 bg-amber-600 hover:bg-amber-500 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-xl transition-all border border-amber-400/50"
                                      >
                                        {holdOrderMutation.isPending ? 'Holding...' : 'Confirm Hold'}
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <div className={`grid gap-2 ${isTimedForThisJob ? 'grid-cols-2' : 'grid-cols-3'}`}>
                                    {!isTimedForThisJob && (
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          acceptAndStartMutation.mutate({ orderId: job.id, currentStatus: job.status })
                                        }}
                                        disabled={isPending}
                                        className="w-full py-3 bg-[var(--accent-600)] hover:bg-[var(--accent-500)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2 border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)]"
                                      >
                                        {isPending ? <Spinner size="sm" /> : <PlayCircle className="w-5 h-5" />}
                                        RESUME
                                      </button>
                                    )}
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        setHoldTarget(job.id)
                                      }}
                                      className="w-full py-3 bg-amber-600/80 hover:bg-amber-600 active:scale-[0.98] text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2 border border-amber-400/50"
                                    >
                                      <PauseCircle className="w-5 h-5" />
                                      HOLD
                                    </button>
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        completeWorkMutation.mutate(job.id)
                                      }}
                                      disabled={isPending}
                                      className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2 border border-emerald-400/50 hover:shadow-[0_0_24px_rgba(16,185,129,0.5)]"
                                    >
                                      {isPending ? <Spinner size="sm" /> : <CheckCircle className="w-5 h-5" />}
                                      DONE
                                    </button>
                                  </div>
                                )}
                              </div>
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
                <div className="flex items-center gap-2 mb-2">
                  <p className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500">Awaiting Review</p>
                  <SectionInfoTooltip text="Completed jobs waiting for manager verification before final closeout." />
                </div>
                {pendingReview.map((job) => (
                  <div
                    key={job.id}
                    className="bg-zinc-900/80 backdrop-blur-sm rounded-2xl p-4 border border-zinc-700/50 shadow-xl shadow-black/20 flex items-center gap-3"
                  >
                    <StatusLED status="warning" />
                    <div className="flex-1 min-w-0">
                      <p className="text-zinc-100 font-medium truncate">{job.vehicle_info}</p>
                      <p className="text-xs text-zinc-500">{job.order_number}</p>
                      <p className="text-xs text-zinc-600 mt-0.5">Created {formatCreatedAt(job.created_at)}</p>
                    </div>
                    <span className="inline-flex items-center gap-1.5 text-xs text-amber-300 bg-amber-500/20 px-2.5 py-1 rounded-full border border-amber-500/30 shrink-0">
                      Pending Review
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        ))}
      </main>

      {showClockOutModal ? (
        <div className="fixed inset-0 z-30 bg-black/70 backdrop-blur-sm flex items-center justify-center px-4">
          <div className="w-full max-w-sm rounded-2xl border border-zinc-700/50 bg-zinc-900/95 backdrop-blur-sm p-5 space-y-4 shadow-2xl shadow-black/50">
            <h3 className="text-zinc-100 text-lg font-semibold">Clock Out</h3>
            <p className="text-sm text-zinc-400">
              End your shift now? Any active timer or break will be closed automatically.
            </p>
            <div className="grid grid-cols-2 gap-3 pt-1">
              <button
                onClick={() => setShowClockOutModal(false)}
                disabled={attendanceToggleBusy}
                className="w-full py-3.5 rounded-xl bg-zinc-800/80 hover:bg-zinc-700 active:scale-[0.98] text-zinc-300 text-base font-medium disabled:opacity-60 border border-zinc-600/50 transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmClockOut}
                disabled={attendanceToggleBusy}
                className="w-full py-3.5 rounded-xl bg-red-950/80 hover:bg-red-900 active:scale-[0.98] text-red-400 text-base font-semibold disabled:opacity-60 border border-red-800/50 hover:border-red-600 transition-all"
              >
                {attendanceToggleBusy ? 'Clocking Out...' : 'Clock Out'}
              </button>
            </div>
            <button
              onClick={() => {
                setShowClockOutModal(false)
                setView('profile')
              }}
              disabled={attendanceToggleBusy}
              className="w-full py-3 text-sm text-zinc-500 hover:text-zinc-300 active:text-zinc-100 disabled:opacity-60 transition-colors"
            >
              Need to sign out too? Go to Profile.
            </button>
          </div>
        </div>
      ) : null}

      {/* Spacer for bottom nav + sticky action bar */}
      <div className={showStickyBar ? 'h-36' : 'h-24'} />

      {/* Bottom Nav */}
      <BottomNav />
    </Container>
  )
}
