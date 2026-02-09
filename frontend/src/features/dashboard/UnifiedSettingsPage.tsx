import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../../stores/authStore'
import api from '../../lib/api'
import { formatUSPhone, isValidUSPhone } from '@/utils/phone'
import toast from 'react-hot-toast'
import { 
  User, Lock, Settings, CreditCard, Bell, Percent, QrCode, LogOut,
  CheckCircle, AlertCircle, ExternalLink, RefreshCw, Save, Upload, Trash2, ImageIcon, Palette, Check, RotateCcw, Type
} from 'lucide-react'
import { useTheme, ACCENT_OPTIONS, FONT_FAMILY_OPTIONS, FONT_SIZE_OPTIONS } from '../../contexts/ThemeContext'

// ============ SCHEMAS ============
const profileSchema = z.object({
  first_name: z.string().min(1, 'First name is required').min(2, 'Min 2 characters'),
  last_name: z.string().min(1, 'Last name is required').min(2, 'Min 2 characters'),
  email: z.string().email('Valid email required'),
  phone: z.string().optional().refine((val) => isValidUSPhone(val), {
    message: 'Invalid phone number',
  }),
  password: z.string().optional(),
})

const passwordSchema = z.object({
  current_password: z.string().min(1, 'Current password is required'),
  new_password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Must contain uppercase letter')
    .regex(/[a-z]/, 'Must contain lowercase letter')
    .regex(/[0-9]/, 'Must contain a number'),
  confirm_password: z.string().min(1, 'Please confirm password'),
}).refine((data) => data.new_password === data.confirm_password, {
  message: "Passwords don't match",
  path: ["confirm_password"],
})

type ProfileFormData = z.infer<typeof profileSchema>
type PasswordFormData = z.infer<typeof passwordSchema>

// ============ TYPES ============
type SettingsSection = 'profile' | 'security' | 'appearance' | 'payments' | 'zelle' | 'notifications' | 'fees'

interface ConnectStatus {
  is_connected: boolean
  onboarding_complete: boolean
  charges_enabled: boolean
  payouts_enabled: boolean
  account_id: string | null
}

interface ZelleSettings {
  zelle_email: string | null
  zelle_phone: string | null
  zelle_qr_image: string | null
}

interface ReminderSettings {
  invoice_reminders_enabled: boolean
  reminder_frequency_days: number
  max_invoice_reminders: number
}

interface TaxFeeSettings {
  sales_tax_rate: number
  shop_supplies_rate: number
  service_fee_rate: number
}

// ============ SECTION COMPONENTS ============

function ProfileSection() {
  const { user, setUser } = useAuthStore()
  const queryClient = useQueryClient()
  const [isEditing, setIsEditing] = useState(false)
  const [originalEmail, setOriginalEmail] = useState(user?.email || '')
  const [showPassword, setShowPassword] = useState(false)

  const { register, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
  })

  const currentEmailValue = watch('email')

  useEffect(() => {
    if (user) {
      reset({
        first_name: user.first_name || '',
        last_name: user.last_name || '',
        email: user.email || '',
        phone: user.phone || '',
        password: '',
      })
      setOriginalEmail(user.email || '')
    }
  }, [user, reset])

  const updateMutation = useMutation({
    mutationFn: async (data: ProfileFormData) => {
      const response = await api.put('/auth/me', data)
      return response.data
    },
    onSuccess: (data) => {
      const responseUser = data.user || data
      const isVerificationPending = data.email_verification_pending || false
      setUser(responseUser)
      queryClient.invalidateQueries({ queryKey: ['user'] })
      
      if (isVerificationPending) {
        toast.success('Verification email sent! Check your new email to confirm.')
      } else {
        toast.success('Profile updated successfully!')
      }
      setIsEditing(false)
      setValue('password', '')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update profile')
    }
  })

  const onSubmit = (data: ProfileFormData) => {
    const isEmailChanging = data.email !== originalEmail
    if (isEmailChanging && !data.password) {
      toast.error('Password is required to change your email address')
      return
    }
    updateMutation.mutate(data)
  }

  const inputClasses = (hasError: boolean) => {
    const base = "w-full px-4 py-3 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors"
    return hasError
      ? `${base} border-red-500 focus:ring-red-500`
      : `${base} border-white/20 focus:ring-amber-500 focus:border-amber-500`
  }

  const getRoleBadge = () => {
    switch (user?.role) {
      case 'super_admin': return { label: 'Super Admin', color: 'bg-purple-500/20 text-purple-400 border-purple-500/30' }
      case 'garage_owner': return { label: 'Garage Owner', color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' }
      case 'garage_admin': return { label: 'Garage Admin', color: 'bg-amber-500/20 text-amber-400 border-amber-500/30' }
      default: return { label: 'Staff', color: 'bg-gray-500/20 text-gray-400 border-gray-500/30' }
    }
  }

  const roleBadge = getRoleBadge()

  return (
    <div className="space-y-6">
      <div className="flex items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3 sm:gap-4 min-w-0">
          <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full bg-amber-500/20 flex items-center justify-center flex-shrink-0">
            <User className="w-6 h-6 sm:w-7 sm:h-7 text-amber-400" />
          </div>
          <div className="min-w-0">
            <h2 className="text-lg sm:text-xl font-bold text-white truncate">{user?.first_name} {user?.last_name}</h2>
            <p className="text-xs sm:text-sm text-gray-400 truncate">{user?.email}</p>
          </div>
        </div>
        <span className={`text-xs px-2 sm:px-2.5 py-1 rounded-full border whitespace-nowrap flex-shrink-0 ${roleBadge.color}`}>
          {roleBadge.label}
        </span>
      </div>

      {!isEditing ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
            <div>
              <label className="text-xs text-gray-400">First Name</label>
              <p className="text-white">{user?.first_name}</p>
            </div>
            <div>
              <label className="text-xs text-gray-400">Last Name</label>
              <p className="text-white">{user?.last_name}</p>
            </div>
            <div>
              <label className="text-xs text-gray-400">Email</label>
              <p className="text-white break-all">{user?.email}</p>
            </div>
            <div>
              <label className="text-xs text-gray-400">Phone</label>
              <p className="text-white">{user?.phone ? formatUSPhone(user.phone) : 'Not set'}</p>
            </div>
          </div>
          <button
            onClick={() => setIsEditing(true)}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Edit Profile
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">First Name</label>
              <input {...register('first_name')} className={inputClasses(!!errors.first_name)} />
              {errors.first_name && <p className="mt-1 text-xs text-red-400">{errors.first_name.message}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Last Name</label>
              <input {...register('last_name')} className={inputClasses(!!errors.last_name)} />
              {errors.last_name && <p className="mt-1 text-xs text-red-400">{errors.last_name.message}</p>}
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Email</label>
            <input {...register('email')} type="email" className={inputClasses(!!errors.email)} />
            {errors.email && <p className="mt-1 text-xs text-red-400">{errors.email.message}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Phone</label>
            <input {...register('phone')} className={inputClasses(!!errors.phone)} placeholder="(555) 123-4567" />
            {errors.phone && <p className="mt-1 text-xs text-red-400">{errors.phone.message}</p>}
          </div>
          
          {currentEmailValue !== originalEmail && (
            <div>
              <label className="block text-xs font-medium text-amber-400 mb-1">Password (required for email change)</label>
              <div className="relative">
                <input
                  {...register('password')}
                  type={showPassword ? 'text' : 'password'}
                  className={inputClasses(false)}
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>
          )}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => { setIsEditing(false); reset() }}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={updateMutation.isPending}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

function SecuritySection() {
  const { logout } = useAuthStore()
  const navigate = useNavigate()
  const [showForm, setShowForm] = useState(false)

  const { register, handleSubmit, reset, formState: { errors } } = useForm<PasswordFormData>({
    resolver: zodResolver(passwordSchema),
  })

  const mutation = useMutation({
    mutationFn: async (data: PasswordFormData) => {
      await api.post('/auth/change-password', {
        current_password: data.current_password,
        new_password: data.new_password,
      })
    },
    onSuccess: () => {
      reset()
      toast.success('Password changed! Redirecting to login...')
      setTimeout(() => {
        logout()
        navigate('/login')
      }, 2000)
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || 'Failed to change password')
    },
  })

  const inputClasses = (hasError: boolean) => {
    const base = "w-full px-4 py-3 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 text-sm"
    return hasError
      ? `${base} border-red-500 focus:ring-red-500`
      : `${base} border-white/20 focus:ring-amber-500`
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Change Password</h3>
        <p className="text-sm text-gray-400">Update your password to keep your account secure.</p>
      </div>

      {!showForm ? (
        <button
          onClick={() => setShowForm(true)}
          className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg transition-colors"
        >
          Change Password
        </button>
      ) : (
        <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4 max-w-md">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Current Password</label>
            <input {...register('current_password')} type="password" className={inputClasses(!!errors.current_password)} />
            {errors.current_password && <p className="mt-1 text-xs text-red-400">{errors.current_password.message}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">New Password</label>
            <input {...register('new_password')} type="password" className={inputClasses(!!errors.new_password)} />
            {errors.new_password && <p className="mt-1 text-xs text-red-400">{errors.new_password.message}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Confirm New Password</label>
            <input {...register('confirm_password')} type="password" className={inputClasses(!!errors.confirm_password)} />
            {errors.confirm_password && <p className="mt-1 text-xs text-red-400">{errors.confirm_password.message}</p>}
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => { setShowForm(false); reset() }}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {mutation.isPending ? 'Changing...' : 'Change Password'}
            </button>
          </div>
        </form>
      )}

      <div className="border-t border-white/10 pt-6">
        <h3 className="text-lg font-semibold text-white mb-2">Sign Out</h3>
        <p className="text-sm text-gray-400 mb-4">End your session on this device.</p>
        <button
          onClick={() => { logout(); navigate('/login') }}
          className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 border border-red-500/30 text-red-400 text-sm font-medium rounded-lg transition-colors"
        >
          Sign Out
        </button>
      </div>
    </div>
  )
}

function PaymentsSection() {
  const [isRedirecting, setIsRedirecting] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()

  const { data: status, isLoading, refetch } = useQuery<ConnectStatus>({
    queryKey: ['stripe-connect-status'],
    queryFn: async () => {
      const response = await api.get('/stripe/connect/status')
      return response.data
    },
  })

  useEffect(() => {
    const success = searchParams.get('success')
    const refresh = searchParams.get('refresh')
    if (success === 'true') {
      toast.success('Stripe setup completed!')
      refetch()
      setSearchParams({}, { replace: true })
    } else if (refresh === 'true') {
      toast('Please complete your Stripe setup')
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, refetch, setSearchParams])

  const onboardMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/stripe/connect/onboard')
      return response.data
    },
    onSuccess: (data) => {
      setIsRedirecting(true)
      window.location.href = data.url
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to start Stripe setup')
    },
  })

  const refreshMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/stripe/connect/refresh')
      return response.data
    },
    onSuccess: (data) => {
      setIsRedirecting(true)
      window.location.href = data.url
    },
  })

  const dashboardMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/stripe/connect/dashboard')
      return response.data
    },
    onSuccess: (data) => {
      window.open(data.url, '_blank')
    },
  })

  if (isLoading) {
    return <div className="flex justify-center py-8"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-500"></div></div>
  }

  const getStatusDisplay = () => {
    if (!status?.is_connected) {
      return { icon: <AlertCircle className="w-6 h-6 text-gray-400" />, title: 'Not Connected', description: 'Connect your Stripe account to receive payments.', color: 'gray' }
    }
    if (!status.onboarding_complete) {
      return { icon: <AlertCircle className="w-6 h-6 text-amber-500" />, title: 'Setup Incomplete', description: 'Please finish the Stripe onboarding process.', color: 'amber' }
    }
    return { icon: <CheckCircle className="w-6 h-6 text-green-500" />, title: 'Connected & Active', description: 'Payments will be deposited to your account.', color: 'green' }
  }

  const statusDisplay = getStatusDisplay()

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Stripe Payments</h3>
        <p className="text-sm text-gray-400">Accept credit card payments from customers.</p>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-xl p-6">
        <div className="flex items-start gap-4">
          {statusDisplay.icon}
          <div className="flex-1">
            <h4 className="font-semibold text-white">{statusDisplay.title}</h4>
            <p className="text-sm text-gray-400 mt-1">{statusDisplay.description}</p>
            
            {status?.is_connected && status.onboarding_complete && (
              <div className="mt-4 flex flex-wrap gap-2">
                <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs ${status.charges_enabled ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                  {status.charges_enabled ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                  Charges {status.charges_enabled ? 'Enabled' : 'Disabled'}
                </span>
                <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs ${status.payouts_enabled ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                  {status.payouts_enabled ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                  Payouts {status.payouts_enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="mt-6">
          {!status?.is_connected ? (
            <button
              onClick={() => onboardMutation.mutate()}
              disabled={onboardMutation.isPending || isRedirecting}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              {onboardMutation.isPending || isRedirecting ? (
                <><div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div> Redirecting...</>
              ) : (
                <><CreditCard className="w-4 h-4" /> Connect Stripe</>
              )}
            </button>
          ) : !status.onboarding_complete ? (
            <button
              onClick={() => refreshMutation.mutate()}
              disabled={refreshMutation.isPending || isRedirecting}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              {refreshMutation.isPending || isRedirecting ? (
                <><div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div> Redirecting...</>
              ) : (
                <><RefreshCw className="w-4 h-4" /> Continue Setup</>
              )}
            </button>
          ) : (
            <button
              onClick={() => dashboardMutation.mutate()}
              disabled={dashboardMutation.isPending}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 border border-white/20 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              <ExternalLink className="w-4 h-4" /> Open Stripe Dashboard
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function ZelleSection() {
  const queryClient = useQueryClient()
  const [zelleQrPreview, setZelleQrPreview] = useState<string | null>(null)
  const [isUploadingQr, setIsUploadingQr] = useState(false)

  const { data: zelleSettings } = useQuery<ZelleSettings>({
    queryKey: ['zelle-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/zelle-settings')
      return response.data
    },
  })

  const uploadQrMutation = useMutation({
    mutationFn: async (base64Image: string | null) => {
      const response = await api.put('/admin/zelle-qr-image', { zelle_qr_image: base64Image })
      return response.data
    },
    onSuccess: () => {
      toast.success(zelleQrPreview ? 'QR code uploaded' : 'QR code removed')
      queryClient.invalidateQueries({ queryKey: ['zelle-settings'] })
      setZelleQrPreview(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to upload QR code')
    },
  })

  const handleQrFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) { toast.error('Please select an image file'); return }
    if (file.size > 1.5 * 1024 * 1024) { toast.error('Image too large. Max 1.5MB'); return }

    setIsUploadingQr(true)
    const reader = new FileReader()
    reader.onload = (event) => {
      setZelleQrPreview(event.target?.result as string)
      setIsUploadingQr(false)
    }
    reader.onerror = () => { toast.error('Failed to read file'); setIsUploadingQr(false) }
    reader.readAsDataURL(file)
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Zelle Payments</h3>
        <p className="text-sm text-gray-400">Upload a QR code for customers to pay via Zelle.</p>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-xl p-6">
        <div className="flex items-start gap-6">
          <div className="w-32 h-32 bg-white/10 rounded-lg flex items-center justify-center overflow-hidden">
            {zelleQrPreview || zelleSettings?.zelle_qr_image ? (
              <img src={zelleQrPreview || zelleSettings?.zelle_qr_image || ''} alt="Zelle QR" className="w-full h-full object-contain" />
            ) : (
              <QrCode className="w-12 h-12 text-gray-500" />
            )}
          </div>
          <div className="flex-1 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Upload QR Code</label>
              <input
                type="file"
                accept="image/*"
                onChange={handleQrFileChange}
                className="block w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-amber-600 file:text-white hover:file:bg-amber-700"
              />
            </div>
            <div className="flex gap-3">
              {zelleQrPreview && (
                <button
                  onClick={() => uploadQrMutation.mutate(zelleQrPreview)}
                  disabled={uploadQrMutation.isPending}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  <Save className="w-4 h-4" /> Save
                </button>
              )}
              {(zelleSettings?.zelle_qr_image || zelleQrPreview) && (
                <button
                  onClick={() => { uploadQrMutation.mutate(null); setZelleQrPreview(null) }}
                  disabled={uploadQrMutation.isPending}
                  className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 border border-red-500/30 text-red-400 text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  <Trash2 className="w-4 h-4" /> Remove
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function NotificationsSection() {
  const queryClient = useQueryClient()
  const [remindersEnabled, setRemindersEnabled] = useState(true)
  const [reminderFrequency, setReminderFrequency] = useState(3)
  const [maxReminders, setMaxReminders] = useState(3)
  const [isEditing, setIsEditing] = useState(false)

  const { data: reminderSettings } = useQuery<ReminderSettings>({
    queryKey: ['reminder-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/reminder-settings')
      return response.data
    },
  })

  useEffect(() => {
    if (reminderSettings) {
      setRemindersEnabled(reminderSettings.invoice_reminders_enabled)
      setReminderFrequency(reminderSettings.reminder_frequency_days)
      setMaxReminders(reminderSettings.max_invoice_reminders)
    }
  }, [reminderSettings])

  const saveMutation = useMutation({
    mutationFn: async () => {
      const response = await api.put('/admin/reminder-settings', {
        invoice_reminders_enabled: remindersEnabled,
        reminder_frequency_days: reminderFrequency,
        max_invoice_reminders: maxReminders,
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Reminder settings saved')
      queryClient.invalidateQueries({ queryKey: ['reminder-settings'] })
      setIsEditing(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save settings')
    },
  })

  const cancelEdit = () => {
    if (reminderSettings) {
      setRemindersEnabled(reminderSettings.invoice_reminders_enabled)
      setReminderFrequency(reminderSettings.reminder_frequency_days)
      setMaxReminders(reminderSettings.max_invoice_reminders)
    }
    setIsEditing(false)
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Invoice Reminders</h3>
        <p className="text-sm text-gray-400">Configure automatic reminders for overdue invoices.</p>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="font-medium text-white">Enable Reminders</h4>
            <p className="text-sm text-gray-400">Send automatic SMS reminders for overdue invoices</p>
          </div>
          <button
            onClick={() => { setRemindersEnabled(!remindersEnabled); setIsEditing(true) }}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${remindersEnabled ? 'bg-amber-600' : 'bg-gray-600'}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${remindersEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
        </div>

        {remindersEnabled && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Reminder Frequency (days)</label>
              <input
                type="number"
                min="1"
                max="30"
                value={reminderFrequency}
                onChange={(e) => { setReminderFrequency(parseInt(e.target.value) || 3); setIsEditing(true) }}
                className="w-32 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Max Reminders</label>
              <input
                type="number"
                min="1"
                max="10"
                value={maxReminders}
                onChange={(e) => { setMaxReminders(parseInt(e.target.value) || 3); setIsEditing(true) }}
                className="w-32 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
            </div>
          </>
        )}

        {isEditing && (
          <div className="flex gap-3 pt-4 border-t border-white/10">
            <button onClick={cancelEdit} className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors">
              Cancel
            </button>
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function FeesSection() {
  const queryClient = useQueryClient()
  const [salesTaxRate, setSalesTaxRate] = useState('')
  const [shopSuppliesRate, setShopSuppliesRate] = useState('')
  const [serviceFeeRate, setServiceFeeRate] = useState('')
  const [isEditing, setIsEditing] = useState(false)

  const { data: taxFeeSettings } = useQuery<TaxFeeSettings>({
    queryKey: ['tax-fee-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/tax-fee-settings')
      return response.data
    },
  })

  useEffect(() => {
    if (taxFeeSettings) {
      setSalesTaxRate(taxFeeSettings.sales_tax_rate?.toString() || '')
      setShopSuppliesRate(taxFeeSettings.shop_supplies_rate?.toString() || '')
      setServiceFeeRate(taxFeeSettings.service_fee_rate?.toString() || '')
    }
  }, [taxFeeSettings])

  const saveMutation = useMutation({
    mutationFn: async () => {
      const response = await api.put('/admin/tax-fee-settings', {
        sales_tax_rate: parseFloat(salesTaxRate) || 0,
        shop_supplies_rate: parseFloat(shopSuppliesRate) || 0,
        service_fee_rate: parseFloat(serviceFeeRate) || 0,
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Tax & fee settings saved')
      queryClient.invalidateQueries({ queryKey: ['tax-fee-settings'] })
      setIsEditing(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save settings')
    },
  })

  const cancelEdit = () => {
    if (taxFeeSettings) {
      setSalesTaxRate(taxFeeSettings.sales_tax_rate?.toString() || '')
      setShopSuppliesRate(taxFeeSettings.shop_supplies_rate?.toString() || '')
      setServiceFeeRate(taxFeeSettings.service_fee_rate?.toString() || '')
    }
    setIsEditing(false)
  }

  const handleRateChange = (setter: (val: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    if (value === '' || /^\d*\.?\d*$/.test(value)) {
      setter(value)
      setIsEditing(true)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Tax & Fees</h3>
        <p className="text-sm text-gray-400">Configure default rates applied to invoices.</p>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-xl p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Sales Tax Rate (%)</label>
          <div className="relative w-40">
            <input
              type="text"
              value={salesTaxRate}
              onChange={handleRateChange(setSalesTaxRate)}
              placeholder="0"
              className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-amber-500 pr-8"
            />
            <Percent className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Shop Supplies Rate (%)</label>
          <div className="relative w-40">
            <input
              type="text"
              value={shopSuppliesRate}
              onChange={handleRateChange(setShopSuppliesRate)}
              placeholder="0"
              className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-amber-500 pr-8"
            />
            <Percent className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Service Fee Rate (%)</label>
          <div className="relative w-40">
            <input
              type="text"
              value={serviceFeeRate}
              onChange={handleRateChange(setServiceFeeRate)}
              placeholder="0"
              className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-amber-500 pr-8"
            />
            <Percent className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          </div>
        </div>

        {isEditing && (
          <div className="flex gap-3 pt-4 border-t border-white/10">
            <button onClick={cancelEdit} className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors">
              Cancel
            </button>
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function AppearanceSection() {
  const { accent, setAccent, fontFamily, setFontFamily, fontSize, setFontSize, accentColors, resetToDefaults } = useTheme()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white mb-2">Appearance</h3>
          <p className="text-sm text-gray-400">Customize your dashboard theme and typography.</p>
        </div>
        <button
          onClick={resetToDefaults}
          className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors flex items-center gap-2"
        >
          <RotateCcw className="w-4 h-4" />
          Reset
        </button>
      </div>

      {/* Live Preview Card */}
      <div 
        className="bg-white/5 border rounded-xl p-6 transition-all"
        style={{ borderColor: accentColors[500] + '40' }}
      >
        <div className="flex items-center gap-3 mb-4">
          <div 
            className="w-10 h-10 rounded-full flex items-center justify-center"
            style={{ backgroundColor: accentColors[500] + '30' }}
          >
            <Palette className="w-5 h-5" style={{ color: accentColors[500] }} />
          </div>
          <div>
            <h4 className="font-semibold text-white">Preview</h4>
            <p className="text-sm text-gray-400">See how your theme looks</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button 
            className="px-4 py-2 rounded-lg text-white text-sm font-medium transition-colors"
            style={{ backgroundColor: accentColors[500] }}
          >
            Primary Button
          </button>
          <button 
            className="px-4 py-2 rounded-lg text-sm font-medium transition-colors border"
            style={{ borderColor: accentColors[500], color: accentColors[500] }}
          >
            Secondary Button
          </button>
          <span 
            className="px-3 py-1.5 rounded-full text-xs font-medium"
            style={{ backgroundColor: accentColors[500] + '20', color: accentColors[400] }}
          >
            Badge
          </span>
        </div>
        <div className="mt-4 pt-4 border-t border-white/10">
          <p className="text-sm">
            <span className="text-gray-400">Active link: </span>
            <span style={{ color: accentColors[500] }} className="font-medium hover:underline cursor-pointer">
              Example Link
            </span>
          </p>
        </div>
      </div>

      {/* Accent Color */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4 sm:p-6">
        <label className="block text-sm font-medium text-gray-300 mb-4">Accent Color</label>
        <div className="flex flex-wrap gap-3 sm:gap-4">
          {ACCENT_OPTIONS.map((option) => (
            <button
              key={option.id}
              onClick={() => setAccent(option.id)}
              className="group flex flex-col items-center gap-1.5 sm:gap-2"
            >
              <div
                className={`w-10 h-10 sm:w-12 sm:h-12 rounded-full flex items-center justify-center transition-all ${
                  accent === option.id
                    ? 'ring-2 ring-offset-2 ring-offset-blueNoir-900 ring-white scale-110'
                    : 'hover:scale-105'
                }`}
                style={{ backgroundColor: option.colors[500] }}
              >
                {accent === option.id && (
                  <Check className="w-4 h-4 sm:w-5 sm:h-5 text-white drop-shadow-md" />
                )}
              </div>
              <span className={`text-[10px] sm:text-xs font-medium transition-colors ${
                accent === option.id ? 'text-white' : 'text-gray-400 group-hover:text-gray-300'
              }`}>
                {option.label}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Font Family */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4 sm:p-6">
        <label className="block text-sm font-medium text-gray-300 mb-4">
          <Type className="w-4 h-4 inline mr-2" />
          Font Family
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3">
          {FONT_FAMILY_OPTIONS.map((option) => (
            <button
              key={option.id}
              onClick={() => setFontFamily(option.id)}
              className={`p-3 sm:p-4 rounded-lg border text-left transition-all ${
                fontFamily === option.id
                  ? 'border-white/40 bg-white/10'
                  : 'border-white/10 hover:border-white/20 hover:bg-white/5'
              }`}
              style={{ fontFamily: option.stack }}
            >
              <span className={`block text-sm font-medium ${fontFamily === option.id ? 'text-white' : 'text-gray-300'}`}>
                {option.label}
              </span>
              <span className="block text-xs text-gray-500 mt-1">Aa Bb Cc 123</span>
            </button>
          ))}
        </div>
      </div>

      {/* Font Size */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4 sm:p-6">
        <label className="block text-sm font-medium text-gray-300 mb-4">Font Size</label>
        <div className="grid grid-cols-3 gap-2">
          {FONT_SIZE_OPTIONS.map((option) => (
            <button
              key={option.id}
              onClick={() => setFontSize(option.id)}
              className={`py-2.5 sm:py-3 px-2 sm:px-4 rounded-lg border text-center transition-all ${
                fontSize === option.id
                  ? 'border-white/40 bg-white/10'
                  : 'border-white/10 hover:border-white/20 hover:bg-white/5'
              }`}
            >
              <span className={`block text-xs sm:text-sm font-medium whitespace-nowrap ${fontSize === option.id ? 'text-white' : 'text-gray-300'}`}>
                {option.label}
              </span>
              <span className="hidden sm:block text-xs text-gray-500 mt-1">
                {option.scale === 1 ? '16px' : option.scale < 1 ? '14px' : '18px'}
              </span>
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs text-gray-500">
        All preferences are saved automatically and will persist across sessions.
      </p>
    </div>
  )
}

// ============ LAYOUT COMPONENTS ============

const PROFILE_SECTIONS = [
  { id: 'profile' as const, label: 'Profile', shortLabel: 'Profile', icon: User },
  { id: 'security' as const, label: 'Security', shortLabel: 'Security', icon: Lock },
  { id: 'appearance' as const, label: 'Appearance', shortLabel: 'Theme', icon: Palette },
]

const GARAGE_SECTIONS = [
  { id: 'payments' as const, label: 'Stripe Payments', shortLabel: 'Stripe', icon: CreditCard },
  { id: 'zelle' as const, label: 'Zelle', shortLabel: 'Zelle', icon: QrCode },
  { id: 'notifications' as const, label: 'Notifications', shortLabel: 'Alerts', icon: Bell },
  { id: 'fees' as const, label: 'Tax & Fees', shortLabel: 'Fees', icon: Percent },
]

function SidebarLayout({ activeSection, setActiveSection, isGarageUser }: { activeSection: SettingsSection, setActiveSection: (s: SettingsSection) => void, isGarageUser: boolean }) {
  const allSections = isGarageUser 
    ? [...PROFILE_SECTIONS, ...GARAGE_SECTIONS]
    : PROFILE_SECTIONS

  return (
    <div className="flex flex-col lg:flex-row gap-6 w-full max-w-[1200px] mx-auto">
      {/* Mobile: Horizontal scrolling nav */}
      <div className="lg:hidden">
        <div className="bg-white/5 rounded-xl border border-white/10 p-2">
          <nav className="flex gap-1 overflow-x-auto scrollbar-hide" style={{ WebkitOverflowScrolling: 'touch' }}>
            {allSections.map((section) => (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={`flex items-center justify-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-colors flex-shrink-0 ${
                  activeSection === section.id
                    ? 'bg-amber-600/20 text-amber-400'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <section.icon className="w-4 h-4 flex-shrink-0" />
                <span className="whitespace-nowrap">{section.shortLabel}</span>
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Desktop: Vertical sidebar */}
      <div className="hidden lg:block w-64 flex-shrink-0">
        <div className="bg-white/5 rounded-xl border border-white/10 p-4 sticky top-4">
          {/* Profile Group */}
          <div className="mb-6">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-3">Account</h3>
            <nav className="space-y-1">
              {PROFILE_SECTIONS.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    activeSection === section.id
                      ? 'bg-amber-600/20 text-amber-400 border-l-2 border-amber-500'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <section.icon className="w-4 h-4" />
                  {section.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Garage Group */}
          {isGarageUser && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-3">Garage</h3>
              <nav className="space-y-1">
                {GARAGE_SECTIONS.map((section) => (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      activeSection === section.id
                        ? 'bg-amber-600/20 text-amber-400 border-l-2 border-amber-500'
                        : 'text-gray-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <section.icon className="w-4 h-4" />
                    {section.label}
                  </button>
                ))}
              </nav>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 bg-white/5 rounded-xl p-4 sm:p-6 lg:p-8 border border-white/10 min-h-[400px] lg:min-h-[600px]">
        {activeSection === 'profile' && <ProfileSection />}
        {activeSection === 'security' && <SecuritySection />}
        {activeSection === 'appearance' && <AppearanceSection />}
        {activeSection === 'payments' && <PaymentsSection />}
        {activeSection === 'zelle' && <ZelleSection />}
        {activeSection === 'notifications' && <NotificationsSection />}
        {activeSection === 'fees' && <FeesSection />}
      </div>
    </div>
  )
}

// ============ MAIN COMPONENT ============

export default function UnifiedSettingsPage() {
  const { user } = useAuthStore()
  const [activeSection, setActiveSection] = useState<SettingsSection>('profile')

  const isGarageUser = user?.role === 'garage_owner' || user?.role === 'garage_admin'

  return (
    <SidebarLayout activeSection={activeSection} setActiveSection={setActiveSection} isGarageUser={isGarageUser} />
  )
}
