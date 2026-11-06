import NotificationPreferencesSection from './NotificationPreferencesSection'
import AccountConfirmationDialog from './AccountConfirmationDialog'
import { CookiePrivacySettings } from '@/components/PrivacyControls'
import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { useState, useEffect } from 'react'
import { Spinner } from '@/components/ui'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query'
import { getAuthenticatedSessionIdentity, isCurrentAuthEpoch, useAuthStore } from '../../stores/authStore'
import api from '../../lib/api'
import { Customer } from '../../types'
import PaymentMethodsCard, { type SavedCardConfig } from './PaymentMethodsCard'
import VehiclesCard from './VehiclesCard'
import { formatUSPhone, isValidUSPhone } from '@/utils/phone'
import toast from 'react-hot-toast'
import { User, Palette, LogOut, Check, RotateCcw, Type, Building2, ArrowRightLeft } from 'lucide-react'
import { useTheme, ACCENT_OPTIONS, FONT_FAMILY_OPTIONS, FONT_SIZE_OPTIONS } from '../../contexts/ThemeContext'
import { getPortalPreferences, savePortalPreferences, type CustomerPortalPreferences } from './portal-preferences'
import { format } from 'date-fns'

// ============ SCHEMAS ============
const profileSchema = z.object({
  first_name: z.string().min(1, 'First name is required').min(2, 'Min 2 characters'),
  last_name: z.string().min(1, 'Last name is required').min(2, 'Min 2 characters'),
  email: z.string().min(1, 'Email is required').email('Invalid email'),
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
type SettingsSection = 'profile' | 'security' | 'appearance' | 'payments' | 'vehicles' | 'shops' | 'notifications'

// ============ SECTION COMPONENTS ============

function ProfileSection() {
  const { user, setUser, authSessionEpoch } = useAuthStore()
  const queryClient = useQueryClient()
  const [isEditing, setIsEditing] = useState(false)
  const [originalEmail, setOriginalEmail] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  const { data: customer, isLoading } = useQuery<Customer>({
    queryKey: ['customer', user?.customer_id],
    queryFn: async () => {
      if (!user?.customer_id) throw new Error('No customer ID')
      const response = await api.get(`/customers/${user.customer_id}`)
      return response.data
    },
    enabled: !!user?.customer_id,
  })

  const { register, handleSubmit, reset, setValue, watch, formState: { errors, isDirty } } = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
  })

  const currentEmailValue = watch('email')

  useEffect(() => {
    if (customer) {
      reset({
        first_name: customer.first_name,
        last_name: customer.last_name,
        email: customer.email,
        phone: formatUSPhone(customer.phone || ''),
        password: '',
      })
      setOriginalEmail(customer.email)
    }
  }, [customer, reset])

  const updateMutation = useMutation({
    mutationFn: async (data: ProfileFormData) => {
      const response = await api.put('/auth/me', data)
      return response.data
    },
    onSuccess: (data) => {
      if (!isCurrentAuthEpoch(authSessionEpoch)) return
      const responseUser = data.user || data
      const isVerificationPending = data.email_verification_pending || false
      setUser(responseUser, authSessionEpoch)
      queryClient.invalidateQueries({ queryKey: ['customer'] })
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
      if (!isCurrentAuthEpoch(authSessionEpoch)) return
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!customer) {
    return (
      <div className="text-center py-12">
        <div className="text-4xl mb-3">⚠️</div>
        <p className="text-gray-400">Customer profile not found</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <div className="w-14 h-14 rounded-full bg-amber-500/20 flex items-center justify-center">
          <User className="w-7 h-7 text-amber-400" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-white">{customer.first_name} {customer.last_name}</h2>
          <p className="text-sm text-gray-400">{customer.email}</p>
        </div>
      </div>

      {!isEditing ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-400">First Name</label>
              <p className="text-white">{customer.first_name}</p>
            </div>
            <div>
              <label className="text-xs text-gray-400">Last Name</label>
              <p className="text-white">{customer.last_name}</p>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400">Email</label>
            <p className="text-white break-all">{customer.email}</p>
          </div>
          <div>
            <label className="text-xs text-gray-400">Phone</label>
            <p className="text-white">{customer.phone ? formatUSPhone(customer.phone) : 'Not set'}</p>
          </div>
          <ControlButton
            onClick={() => setIsEditing(true)}
            className="px-4  bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Edit Profile
          </ControlButton>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">First Name</label>
              <ControlInput {...register('first_name')} className={inputClasses(!!errors.first_name)} />
              {errors.first_name && <p className="mt-1 text-xs text-red-400">{errors.first_name.message}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Last Name</label>
              <ControlInput {...register('last_name')} className={inputClasses(!!errors.last_name)} />
              {errors.last_name && <p className="mt-1 text-xs text-red-400">{errors.last_name.message}</p>}
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Email</label>
            <ControlInput {...register('email')} type="email" className={inputClasses(!!errors.email)} />
            {errors.email && <p className="mt-1 text-xs text-red-400">{errors.email.message}</p>}
            {currentEmailValue !== originalEmail && (
              <p className="mt-1 text-xs text-blue-400">📧 You'll receive a verification link at the new email</p>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Phone</label>
            <ControlInput
              {...register('phone')} 
              className={inputClasses(!!errors.phone)} 
              placeholder="(555) 123-4567"
              onChange={(e) => setValue('phone', formatUSPhone(e.target.value))}
            />
            {errors.phone && <p className="mt-1 text-xs text-red-400">{errors.phone.message}</p>}
          </div>
          
          {currentEmailValue !== originalEmail && (
            <div>
              <label className="block text-xs font-medium text-amber-400 mb-1">Password (required for email change)</label>
              <div className="relative">
                <ControlInput
                  {...register('password')}
                  type={showPassword ? 'text' : 'password'}
                  className={inputClasses(false)}
                  placeholder="Enter your password"
                />
                <ControlButton
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white text-sm"
                >
                  {showPassword ? 'Hide' : 'Show'}
                </ControlButton>
              </div>
            </div>
          )}

          <p className="text-sm text-gray-400">Use at least 8 characters, including an uppercase letter, a lowercase letter, and a number.</p>
          <div className="flex gap-3">
            <ControlButton
              type="button"
              onClick={() => { setIsEditing(false); reset() }}
              className="px-4  bg-gray-600 hover:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Cancel
            </ControlButton>
            <ControlButton
              type="submit"
              disabled={!isDirty || updateMutation.isPending}
              className="px-4  bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
            </ControlButton>
          </div>
        </form>
      )}
    </div>
  )
}

// Kept during the transition so existing profile mutation behavior remains easy to compare.
void ProfileSection

function SecuritySection() {
  const { logout, authSessionEpoch } = useAuthStore()
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
      if (!isCurrentAuthEpoch(authSessionEpoch)) return
      reset()
      toast.success('Password changed! Redirecting to login...')
      setTimeout(() => {
        if (!isCurrentAuthEpoch(authSessionEpoch)) return
        logout()
        navigate('/login')
      }, 2000)
    },
    onError: (err: any) => {
      if (!isCurrentAuthEpoch(authSessionEpoch)) return
      toast.error(err.response?.data?.detail || 'Failed to change password')
    },
  })

  const inputClasses = (hasError: boolean) => {
    // text-base (16px) prevents iOS Safari auto-zoom on focus
    const base = "w-full px-4 py-3 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 text-base"
    return hasError
      ? `${base} border-red-500 focus:ring-red-500`
      : `${base} border-[#30384b] focus:border-violet-500 focus:ring-violet-500/30`
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Change Password</h3>
        <p className="text-sm text-gray-400">Update your password to keep your account secure.</p>
      </div>

      {!showForm ? (
        <ControlButton
          onClick={() => setShowForm(true)}
          className="rounded-xl bg-violet-600 px-4  text-sm font-medium text-white transition-colors hover:bg-violet-500"
        >
          Change Password
        </ControlButton>
      ) : (
        <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4 max-w-md">
          <div>
            <label htmlFor="current_password" className="block text-xs font-medium text-gray-400 mb-1">Current Password</label>
            <ControlInput {...register('current_password')} id="current_password" autoComplete="current-password" type="password" className={inputClasses(!!errors.current_password)} />
            {errors.current_password && <p className="mt-1 text-xs text-red-400">{errors.current_password.message}</p>}
          </div>
          <div>
            <label htmlFor="new_password" className="block text-xs font-medium text-gray-400 mb-1">New Password</label>
            <ControlInput {...register('new_password')} id="new_password" autoComplete="new-password" type="password" className={inputClasses(!!errors.new_password)} />
            {errors.new_password && <p className="mt-1 text-xs text-red-400">{errors.new_password.message}</p>}
          </div>
          <div>
            <label htmlFor="confirm_password" className="block text-xs font-medium text-gray-400 mb-1">Confirm New Password</label>
            <ControlInput {...register('confirm_password')} id="confirm_password" autoComplete="new-password" type="password" className={inputClasses(!!errors.confirm_password)} />
            {errors.confirm_password && <p className="mt-1 text-xs text-red-400">{errors.confirm_password.message}</p>}
          </div>
          <p className="text-sm text-gray-400">Use at least 8 characters, including an uppercase letter, a lowercase letter, and a number.</p>
          <div className="flex gap-3">
            <ControlButton
              type="button"
              disabled={mutation.isPending}
              onClick={() => { setShowForm(false); reset() }}
              className="px-4  bg-gray-600 hover:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Cancel
            </ControlButton>
            <ControlButton
              type="submit"
              disabled={mutation.isPending}
              className="rounded-xl bg-violet-600 px-4  text-sm font-medium text-white transition-colors hover:bg-violet-500 disabled:bg-gray-600"
            >
              {mutation.isPending ? 'Changing...' : 'Change Password'}
            </ControlButton>
          </div>
        </form>
      )}

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
          <p className="text-sm text-gray-400">Customize your portal theme and typography.</p>
        </div>
        <ControlButton
          onClick={resetToDefaults}
          className="px-3  text-sm text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors flex items-center gap-2"
        >
          <RotateCcw className="w-4 h-4" />
          Reset
        </ControlButton>
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
          <span aria-hidden="true"
            className="inline-flex min-h-11 items-center px-4 rounded-lg text-white text-sm font-medium transition-colors"
            style={{ backgroundColor: accentColors[500], color: accent === 'indigo' ? '#ffffff' : '#0d1018' }}
          >
            Primary button
          </span>
          <span aria-hidden="true"
            className="inline-flex min-h-11 items-center px-4 rounded-lg text-sm font-medium transition-colors border"
            style={{ borderColor: accentColors[500], color: accentColors[500] }}
          >
            Secondary button
          </span>
          <span 
            className="px-3 py-1.5 rounded-full text-xs font-medium"
            style={{ backgroundColor: accentColors[500] + '20', color: accentColors[400] }}
          >
            Badge
          </span>
        </div>
      </div>

      {/* Accent Color */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-6">
        <label className="block text-sm font-medium text-gray-300 mb-4">Accent Color</label>
        <div className="grid grid-cols-3 gap-4 sm:grid-cols-5">
          {ACCENT_OPTIONS.map((option) => (
            <ControlButton controlKind="content"
              key={option.id}
              aria-pressed={accent === option.id}
              onClick={() => setAccent(option.id)}
              className="group flex min-h-11 min-w-11 flex-col items-center gap-2 rounded-lg p-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-300"
            >
              <div
                className={`w-12 h-12 rounded-full flex items-center justify-center transition-all ${
                  accent === option.id
                    ? 'ring-2 ring-offset-2 ring-offset-slate-900 ring-white scale-110'
                    : 'hover:scale-105'
                }`}
                style={{ backgroundColor: option.colors[500] }}
              >
                {accent === option.id && (
                  <Check className="w-5 h-5 text-white drop-shadow-md" />
                )}
              </div>
              <span className={`text-xs font-medium transition-colors ${
                accent === option.id ? 'text-white' : 'text-gray-400 group-hover:text-gray-300'
              }`}>
                {option.label}
              </span>
            </ControlButton>
          ))}
        </div>
      </div>

      {/* Font Family */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-6">
        <label className="block text-sm font-medium text-gray-300 mb-4">
          <Type className="w-4 h-4 inline mr-2" />
          Font Family
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {FONT_FAMILY_OPTIONS.map((option) => (
            <ControlButton controlKind="content"
              key={option.id}
              aria-pressed={fontFamily === option.id}
              onClick={() => setFontFamily(option.id)}
              className={`p-4 rounded-lg border text-left transition-all ${
                fontFamily === option.id
                  ? 'border-white/40 bg-white/10'
                  : 'border-white/10 hover:border-white/20 hover:bg-white/5'
              }`}
              style={{ fontFamily: option.stack }}
            >
              <span className={`block text-sm font-medium ${fontFamily === option.id ? 'text-white' : 'text-gray-300'}`}>
                {option.label}
              </span>
              <span className="block text-xs text-gray-400 mt-1">Aa Bb Cc 123</span>
            </ControlButton>
          ))}
        </div>
      </div>

      {/* Font Size */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4 sm:p-6">
        <label className="block text-sm font-medium text-gray-300 mb-4">Font Size</label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {FONT_SIZE_OPTIONS.map((option) => (
            <ControlButton
              key={option.id}
              aria-pressed={fontSize === option.id}
              onClick={() => setFontSize(option.id)}
              className={`  px-2 sm:px-4 rounded-lg border text-center transition-all ${
                fontSize === option.id
                  ? 'border-white/40 bg-white/10'
                  : 'border-white/10 hover:border-white/20 hover:bg-white/5'
              }`}
            >
              <span className={`block text-xs sm:text-sm font-medium whitespace-nowrap ${fontSize === option.id ? 'text-white' : 'text-gray-300'}`}>
                {option.label}
              </span>
              <span className="hidden sm:block text-xs text-gray-400 mt-1">
                {option.previewPx}px
              </span>
            </ControlButton>
          ))}
        </div>
      </div>

      <p className="text-xs text-gray-400">
        Appearance changes are saved automatically on this browser.
      </p>
    </div>
  )
}

function PaymentsSection() {
  return <PaymentMethodsCard />
}

function VehiclesSection() {
  return <VehiclesCard embedded />
}

interface ShopOption {
  id: string
  name: string
  slug: string
  logo_url: string | null
}

function ShopsSection() {
  const { user, login } = useAuthStore()
  const navigate = useNavigate()
  const [switching, setSwitching] = useState<string | null>(null)

  const { data: shops = [], isLoading, isError, refetch, isFetching } = useQuery<ShopOption[]>({
    queryKey: ['my-shops'],
    queryFn: async () => {
      const res = await api.get('/auth/my-shops')
      return res.data
    },
  })

  const handleSwitch = async (tenantId: string) => {
    setSwitching(tenantId)
    try {
      const res = await api.post('/auth/switch-shop', { tenant_id: tenantId })
      const { access_token, refresh_token } = res.data
      api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
      const meRes = await api.get('/auth/me', { headers: { Authorization: `Bearer ${access_token}` } })
      login(access_token, refresh_token, meRes.data)
      navigate('/portal')
    } catch {
      toast.error('Failed to switch shop. Please try again.')
    } finally {
      setSwitching(null)
    }
  }

  if (isLoading) {
    return <div className="flex items-center justify-center py-12"><Spinner size="lg" /></div>
  }

  if (isError) return <div role="alert" className="space-y-3">
    <p>Unable to load your shops.</p>
    <ControlButton type="button" disabled={isFetching} onClick={() => void refetch()} className="text-violet-300 underline">Retry loading shops</ControlButton>
  </div>

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white mb-1">Shops</h2>
        <p className="text-sm text-gray-400">
          {shops.length > 1
            ? 'Your account is linked to multiple shops. Switch between them here.'
            : shops.length === 1 ? 'Your account is linked to this shop.' : 'No shops are linked to your account.'}
        </p>
      </div>

      <div className="space-y-3">
        {shops.map((shop) => {
          const isCurrent = shop.id === user?.tenant_id
          const isSwitching = switching === shop.id

          return (
            <div
              key={shop.id}
              className={`flex items-center gap-4 p-4 rounded-xl border transition-colors ${
                isCurrent
                  ? 'border-violet-400/40 bg-violet-500/10'
                  : 'border-white/10 bg-white/5'
              }`}
            >
              {shop.logo_url ? (
                <img src={shop.logo_url} alt={shop.name} className="h-10 w-10 rounded-lg object-contain bg-white p-1 flex-shrink-0" />
              ) : (
                <div className="h-10 w-10 rounded-lg bg-white/10 flex items-center justify-center flex-shrink-0">
                  <Building2 className="w-5 h-5 text-gray-400" />
                </div>
              )}

              <div className="flex-1 min-w-0">
                <p className="font-medium text-white truncate">{shop.name}</p>
                {isCurrent && (
                  <span className="mt-0.5 inline-flex items-center gap-1 text-xs font-medium text-violet-300">
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-violet-400" />
                    Active
                  </span>
                )}
              </div>

              {!isCurrent && shops.length > 1 && (
                <ControlButton
                  onClick={() => handleSwitch(shop.id)}
                  disabled={!!switching}
                  className="flex items-center gap-2 px-3  text-sm font-medium rounded-lg border border-white/20 text-gray-300 hover:text-white hover:border-white/40 hover:bg-white/10 transition-colors disabled:opacity-50 flex-shrink-0"
                >
                  {isSwitching ? (
                    <Spinner size="xs" className="border-white/40 border-t-white" />
                  ) : (
                    <ArrowRightLeft className="w-3.5 h-3.5" />
                  )}
                  {isSwitching ? 'Switching…' : 'Switch'}
                </ControlButton>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface SavedPaymentMethod {
  id: string
  brand: string
  last4: string
  is_default: boolean
}

function ContactDetailsSection({ onDirtyChange, onManagePayments }: { onDirtyChange: (dirty: boolean) => void; onManagePayments: () => void }) {
  const auth = useAuthStore()
  const { user, setUser, authSessionEpoch } = auth
  const queryClient = useQueryClient()
  const [preferences, setPreferences] = useState<CustomerPortalPreferences>(() => getPortalPreferences(user?.customer_id))

  const { data: customer, isLoading, isError, refetch, isFetching } = useQuery<Customer>({
    queryKey: ['customer', user?.customer_id],
    queryFn: async () => (await api.get(`/customers/${user!.customer_id}`)).data,
    enabled: Boolean(user?.customer_id),
  })
  const cardScope = getAuthenticatedSessionIdentity(auth)
  const cardConfig = useQuery<SavedCardConfig>({
    queryKey: ['payment-methods-config', cardScope],
    enabled: Boolean(cardScope),
    queryFn: async () => (await api.get('/payments/cards/config')).data,
    retry: false,
  })
  const cards = useQuery<SavedPaymentMethod[]>({
    queryKey: ['payment-methods', cardScope, cardConfig.data?.context_key],
    enabled: Boolean(cardScope) && cardConfig.data?.available === true,
    retry: false,
    queryFn: async () => (await api.get('/payments/cards', { params: { expected_context: cardConfig.data?.context_key } })).data,
  })
  const paymentMethods = cards.data || []
  const cardsLoading = cardConfig.isLoading || cards.isLoading
  const cardsError = cardConfig.isError || cards.isError || cardConfig.data?.available === false

  const { register, handleSubmit, reset, setValue, watch, formState: { errors, isDirty } } = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
  })

  useEffect(() => { onDirtyChange(isDirty) }, [isDirty, onDirtyChange])
  useEffect(() => () => onDirtyChange(false), [onDirtyChange])
  useEffect(() => {
    if (!isDirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [isDirty])
  useEffect(() => {
    if (!customer) return
    reset({
      first_name: customer.first_name,
      last_name: customer.last_name,
      email: customer.email,
      phone: formatUSPhone(customer.phone || ''),
      password: '',
    }, { keepDirtyValues: true })
  }, [customer, reset])

  const updateMutation = useMutation({
    mutationFn: async (data: ProfileFormData) => (await api.put('/auth/me', data)).data,
    onSuccess: (data, submitted) => {
      if (!isCurrentAuthEpoch(authSessionEpoch)) return
      setUser(data.user || data, authSessionEpoch)
      queryClient.invalidateQueries({ queryKey: ['customer'] })
      toast.success(data.email_verification_pending ? 'Check your new email to verify the change.' : 'Contact details saved')
      reset({ ...submitted, phone: formatUSPhone(submitted.phone || ''), password: '' })
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      if (!isCurrentAuthEpoch(authSessionEpoch)) return
      toast.error(error.response?.data?.detail || 'Unable to save contact details')
    },
  })

  if (isLoading) return <div className="flex min-h-[360px] items-center justify-center"><Spinner size="lg" /></div>
  if (isError) return <div role="alert" className="space-y-3 rounded-2xl border border-[#232939] bg-[#161a26] p-5">
    <p>Unable to load your contact details.</p>
    <ControlButton type="button" disabled={isFetching} onClick={() => void refetch()} className="text-violet-300 underline">Retry loading profile</ControlButton>
  </div>
  if (!customer) return <div className="rounded-2xl border border-[#232939] bg-[#161a26] p-8 text-center text-[#8b92a5]">Customer profile not found.</div>

  const emailChanging = watch('email') !== customer.email
  const defaultCard = paymentMethods.find(method => method.is_default) || paymentMethods[0]

  const updatePreferences = (next: CustomerPortalPreferences) => {
    try {
      savePortalPreferences(user?.customer_id, next)
      setPreferences(next)
    } catch {
      toast.error('Your browser could not save this checkout preference. Please try again.')
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <form onSubmit={handleSubmit(data => {
        if (emailChanging && !data.password) {
          toast.error('Enter your password to change your email address')
          return
        }
        updateMutation.mutate(data)
      })} className="overflow-hidden rounded-2xl border border-[#232939] bg-[#161a26]">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1e2432] px-4 py-3.5 sm:px-5">
          <span className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-[#8b92a5]">Contact details</span>
          <span className="text-xs text-[#a5adbf]">Edit fields, then select Save changes</span>
        </div>
        <fieldset disabled={updateMutation.isPending} className="grid gap-4 p-4 sm:grid-cols-2 sm:p-5">
          {[
            { name: 'first_name' as const, label: 'First name', type: 'text' },
            { name: 'last_name' as const, label: 'Last name', type: 'text' },
          ].map(field => (
            <label key={field.name} className="block text-xs font-bold text-[#8b92a5]">
              {field.label}
              <ControlInput
                {...register(field.name)}
                type={field.type}
                className="mt-1.5 h-11 w-full rounded-[10px] border border-[#272d3d] bg-[#12161f] px-3 text-base text-[#eceef4] outline-none focus:border-[#8b7cf7] focus:ring-2 focus:ring-[#8b7cf7]/30"
              />
              {errors[field.name] && <span className="mt-1 block text-[11px] text-[#ff8b8d]">{errors[field.name]?.message}</span>}
            </label>
          ))}
          <label className="block text-xs font-bold text-[#8b92a5] sm:col-span-2">
            Email
            <ControlInput
              {...register('email')}
              type="email"
              autoComplete="email"
              className="mt-1.5  w-full rounded-[10px] border border-[#272d3d] bg-[#12161f] px-3 text-base text-[#eceef4] outline-none focus:border-[#8b7cf7] focus:ring-2 focus:ring-[#8b7cf7]/30"
            />
            {errors.email && <span className="mt-1 block text-[11px] text-[#ff8b8d]">{errors.email.message}</span>}
          </label>
          <label className="block text-xs font-bold text-[#8b92a5] sm:col-span-2">
            Phone
            <ControlInput
              {...register('phone')}
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              onChange={event => setValue('phone', formatUSPhone(event.target.value), { shouldDirty: true, shouldValidate: true })}
              className="mt-1.5  w-full rounded-[10px] border border-[#272d3d] bg-[#12161f] px-3 text-base text-[#eceef4] outline-none focus:border-[#8b7cf7] focus:ring-2 focus:ring-[#8b7cf7]/30"
            />
            {errors.phone && <span className="mt-1 block text-[11px] text-[#ff8b8d]">{errors.phone.message}</span>}
          </label>
          {emailChanging && (
            <label className="block text-xs font-bold text-[#f0b959] sm:col-span-2">
              Current password required to change email
              <ControlInput
                {...register('password')}
                type="password"
                autoComplete="current-password"
                className="mt-1.5  w-full rounded-[10px] border border-[#f0b959]/40 bg-[#12161f] px-3 text-base text-[#eceef4] outline-none focus:ring-2 focus:ring-[#f0b959]/25"
              />
            </label>
          )}
        </fieldset>
        <div className="flex flex-col gap-2 border-t border-[#1e2432] bg-[#12161f] p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <div className="flex flex-wrap items-center gap-3"><ControlButton
            type="submit"
            disabled={!isDirty || updateMutation.isPending}
            className=" rounded-[11px] bg-[#8b7cf7] px-5 text-sm font-extrabold text-[#0e1118] disabled:opacity-50"
          >
            {updateMutation.isPending ? 'Saving…' : 'Save changes'}
          </ControlButton>
          {isDirty && <ControlButton type="button" disabled={updateMutation.isPending} onClick={() => reset({ first_name: customer.first_name, last_name: customer.last_name, email: customer.email, phone: formatUSPhone(customer.phone || ''), password: '' })} className="text-gray-300">Cancel</ControlButton>}
          <span role="status" className="text-xs text-gray-400">{isDirty ? 'Unsaved changes' : ''}</span></div>
          <span className="text-xs text-[#a5adbf]">Last updated {format(new Date(customer.updated_at), 'MMM d, yyyy')}</span>
        </div>
      </form>

      <aside className="space-y-3">
        <section className="rounded-[14px] border border-[#232939] bg-[#161a26] p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-[46px] w-[46px] items-center justify-center rounded-full border border-[#8b7cf7] bg-[#241f3d] text-sm font-extrabold text-[#c9bfff]">
              {(customer.first_name[0] || '')}{(customer.last_name[0] || '')}
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-extrabold">{customer.company_name || `${customer.first_name} ${customer.last_name}`}</h2>
              <p className="mt-1 text-[11px] text-[#8b92a5]">Customer since {format(new Date(customer.created_at), 'MMM yyyy')}</p>
            </div>
          </div>
        </section>

        <section className="rounded-[14px] border border-[#232939] bg-[#161a26] p-4">
          <h2 className="text-sm font-semibold">Preferred checkout method</h2>
          <p className="mt-1 text-xs text-gray-400">Selected automatically when you open an invoice on this browser.</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {(['zelle', 'card'] as const).map(method => (
              <ControlButton
                key={method}
                type="button"
                aria-pressed={preferences.defaultPaymentMethod === method}
                onClick={() => updatePreferences({ ...preferences, defaultPaymentMethod: method })}
                className={` rounded-[10px] border text-xs font-extrabold uppercase ${
                  preferences.defaultPaymentMethod === method
                    ? method === 'zelle'
                      ? 'border-[#2dd4bf]/40 bg-[#2dd4bf]/10 text-[#2dd4bf]'
                      : 'border-[#8b7cf7] bg-[#8b7cf7]/10 text-[#c9bfff]'
                    : 'border-[#272d3d] bg-[#12161f] text-[#8b92a5]'
                }`}
              >
                {method}
              </ControlButton>
            ))}
          </div>
          <p role="status" className="mt-3 text-xs text-gray-400">{preferences.defaultPaymentMethod === 'zelle' ? 'Zelle is preferred. Payment instructions are shown on each invoice.' : 'Card is preferred. Available cards and fees are shown at checkout.'}</p>
          <p className="mt-3 border-t border-[#272d3d] pt-3 text-xs text-[#a5adbf]">Saved card for this shop</p>
          <p className="mt-1 text-xs text-[#8b92a5]">
            {cardConfig.data?.save_pending ? 'Card save unconfirmed. Open Payment methods for details.'
              : cardsError ? 'Saved cards unavailable. Open Payment methods to retry.'
              : cardsLoading ? 'Loading saved cards…'
                : defaultCard ? `Card on file: ${defaultCard.brand} ···${defaultCard.last4}` : 'No card on file'}
          </p>
          <ControlButton type="button" onClick={onManagePayments} className="mt-2 text-violet-300 underline">Manage payment methods</ControlButton>
        </section>
      </aside>
    </div>
  )
}

// ============ LAYOUT ============

const SECTION_GROUPS = [
  { label: 'Account', sections: [{ id: 'profile', label: 'Profile' }, { id: 'security', label: 'Security' }] },
  { label: 'Preferences', sections: [{ id: 'notifications', label: 'Notifications' }, { id: 'appearance', label: 'Appearance' }] },
  { label: 'Business', sections: [{ id: 'payments', label: 'Payment methods' }, { id: 'vehicles', label: 'Vehicles' }, { id: 'shops', label: 'Shops' }] },
] as const
const SECTIONS = SECTION_GROUPS.flatMap(group => [...group.sections])

export default function ProfileSettingsPage() {
  const navigate = useNavigate()
  const auth = useAuthStore()
  const { user, logout } = auth
  const accountScope = getAuthenticatedSessionIdentity(auth)
  const [settingsDirty, setSettingsDirty] = useState(false)
  const [pendingAction, setPendingAction] = useState<({ type: 'section'; section: SettingsSection } | { type: 'signout' }) & { scope: string | null } | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab') as SettingsSection | null
  const activeSection = requestedTab && SECTIONS.some(section => section.id === requestedTab) ? requestedTab : 'profile'
  const [mobileSectionOpen, setMobileSectionOpen] = useState(Boolean(requestedTab && SECTIONS.some(section => section.id === requestedTab)))

  useEffect(() => { setPendingAction(null) }, [accountScope])

  const selectSection = (section: SettingsSection) => {
    setMobileSectionOpen(true)
    const next = new URLSearchParams(searchParams)
    if (section === 'profile') next.delete('tab')
    else next.set('tab', section)
    setSearchParams(next, { replace: true })
    requestAnimationFrame(() => document.getElementById('account-section-heading')?.focus())
  }
  const requestSection = (section: SettingsSection) => {
    if (section !== activeSection && settingsDirty) setPendingAction({ type: 'section', section, scope: accountScope })
    else selectSection(section)
  }
  const signOut = () => { logout(); navigate('/login', { replace: true, state: { signedOut: true } }) }
  const confirmAction = () => {
    const action = pendingAction
    setPendingAction(null)
    if (!action || action.scope !== accountScope) return
    if (action.type === 'section') selectSection(action.section)
    else if (action?.type === 'signout') signOut()
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-extrabold tracking-[-0.01em]">Account settings</h1>
        <p className="mt-1 text-[13px] text-[#8b92a5]">
          {[user?.first_name, user?.last_name].filter(Boolean).join(' ') || 'Customer'} · {user?.email}
        </p>
      </div>

      <div className="grid items-start gap-6 md:grid-cols-[200px_minmax(0,1fr)] md:gap-8">
        <nav className={[(mobileSectionOpen ? 'hidden md:block' : ''), 'space-y-6'].join(' ')} aria-label="Account sections">
          {SECTION_GROUPS.map(group => <div key={group.label}>
            <h2 className="mb-3 border-b border-[#272d3d] px-3 pb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-[#a5adbf]">{group.label}</h2>
            <div className="space-y-1">{group.sections.map(section => <ControlButton
              key={section.id} type="button" controlKind="content"
              aria-current={activeSection === section.id ? 'page' : undefined}
              onClick={() => requestSection(section.id)}
              className={['flex min-h-11 w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-300', activeSection === section.id ? 'bg-violet-400/10 text-[#d4ccff]' : 'text-[#b5bdcf] hover:bg-white/5 hover:text-white'].join(' ')}>
              {section.label}<span aria-hidden="true" className="md:hidden">›</span>
            </ControlButton>)}</div>
          </div>)}
          <div className="border-t border-[#272d3d] pt-3">
            <ControlButton type="button" onClick={() => settingsDirty ? setPendingAction({ type: 'signout', scope: accountScope }) : signOut()} className="w-full justify-start text-[var(--semantic-danger-500)] hover:bg-red-500/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-400"><LogOut className="h-4 w-4" aria-hidden="true" />Sign out</ControlButton>
          </div>
        </nav>
        <div className={[(mobileSectionOpen ? '' : 'hidden md:block'), 'min-w-0'].join(' ')}>
          <ControlButton type="button" onClick={() => {
            setMobileSectionOpen(false)
            requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('nav[aria-label="Account sections"] button[aria-current="page"]')?.focus())
          }} className="mb-4 text-[#c9bfff] md:hidden">← All settings</ControlButton>
          <div id="account-section-heading" role="region" aria-label={SECTIONS.find(section => section.id === activeSection)?.label} tabIndex={-1} className="rounded-2xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-300">
            {activeSection === 'profile' ? (
              <ContactDetailsSection onDirtyChange={setSettingsDirty} onManagePayments={() => requestSection('payments')} />
            ) : (
              <div className="rounded-2xl border border-[#232939] bg-[#161a26] p-4 sm:p-6">
                {activeSection === 'security' && <><SecuritySection /><div className="[&_.cookie-privacy-settings]:border-[#272d3d] [&_.cookie-privacy-settings_p]:text-gray-400"><CookiePrivacySettings /></div></>}
                {activeSection === 'appearance' && <AppearanceSection />}
                {activeSection === 'payments' && <PaymentsSection />}
                {activeSection === 'vehicles' && <VehiclesSection />}
                {activeSection === 'shops' && <ShopsSection />}
                {activeSection === 'notifications' && <NotificationPreferencesSection onDirtyChange={setSettingsDirty} />}
              </div>
            )}
          </div>
        </div>
      </div>
      <AccountConfirmationDialog
        open={pendingAction !== null && pendingAction.scope === accountScope}
        title={pendingAction?.type === 'signout' ? 'Discard changes and sign out?' : 'Discard unsaved changes?'}
        description={pendingAction?.type === 'signout' ? 'Signing out will discard your unsaved changes.' : 'Leaving this section will discard your unsaved changes.'}
        confirmLabel={pendingAction?.type === 'signout' ? 'Discard and sign out' : 'Discard changes'}
        cancelLabel="Keep editing"
        onCancel={() => setPendingAction(null)}
        onConfirm={confirmAction}
      />
    </div>
  )
}
