import { useState, useEffect } from 'react'
import { Spinner } from '@/components/ui'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../../stores/authStore'
import api from '../../lib/api'
import { Customer } from '../../types'
import PaymentMethodsCard from './PaymentMethodsCard'
import VehiclesCard from './VehiclesCard'
import { formatUSPhone, isValidUSPhone } from '@/utils/phone'
import toast from 'react-hot-toast'
import { User, Lock, CreditCard, Truck, Palette, LogOut, Check, RotateCcw, Type, Building2, ArrowRightLeft } from 'lucide-react'
import { useTheme, ACCENT_OPTIONS, FONT_FAMILY_OPTIONS, FONT_SIZE_OPTIONS } from '../../contexts/ThemeContext'

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
type SettingsSection = 'profile' | 'security' | 'appearance' | 'payments' | 'vehicles' | 'shops'

// ============ SECTION COMPONENTS ============

function ProfileSection() {
  const { user, setUser } = useAuthStore()
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
        phone: customer.phone || '',
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
      const responseUser = data.user || data
      const isVerificationPending = data.email_verification_pending || false
      setUser(responseUser)
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
          <button
            onClick={() => setIsEditing(true)}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Edit Profile
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
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
            {currentEmailValue !== originalEmail && (
              <p className="mt-1 text-xs text-blue-400">📧 You'll receive a verification link at the new email</p>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Phone</label>
            <input 
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
                <input
                  {...register('password')}
                  type={showPassword ? 'text' : 'password'}
                  className={inputClasses(false)}
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white text-sm"
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
              disabled={!isDirty || updateMutation.isPending}
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
    // text-base (16px) prevents iOS Safari auto-zoom on focus
    const base = "w-full px-4 py-3 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 text-base"
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
          className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 border border-red-500/30 text-red-400 text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
        >
          <LogOut className="w-4 h-4" />
          Sign Out
        </button>
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
          <p className="text-sm text-gray-400">Customize your portal theme and typography.</p>
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
      </div>

      {/* Accent Color */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-6">
        <label className="block text-sm font-medium text-gray-300 mb-4">Accent Color</label>
        <div className="grid grid-cols-5 gap-4">
          {ACCENT_OPTIONS.map((option) => (
            <button
              key={option.id}
              onClick={() => setAccent(option.id)}
              className="group flex flex-col items-center gap-2"
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
            </button>
          ))}
        </div>
      </div>

      {/* Font Family */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-6">
        <label className="block text-sm font-medium text-gray-300 mb-4">
          <Type className="w-4 h-4 inline mr-2" />
          Font Family
        </label>
        <div className="grid grid-cols-3 gap-3">
          {FONT_FAMILY_OPTIONS.map((option) => (
            <button
              key={option.id}
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
              <span className="block text-xs text-gray-500 mt-1">Aa Bb Cc 123</span>
            </button>
          ))}
        </div>
      </div>

      {/* Font Size */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4 sm:p-6">
        <label className="block text-sm font-medium text-gray-300 mb-4">Font Size</label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
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
                {option.previewPx}px
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

function PaymentsSection() {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Payment Methods</h3>
        <p className="text-sm text-gray-400">Manage your saved payment methods.</p>
      </div>
      <PaymentMethodsCard />
    </div>
  )
}

function VehiclesSection() {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">My Vehicles</h3>
        <p className="text-sm text-gray-400">Manage vehicles registered to your account.</p>
      </div>
      <VehiclesCard />
    </div>
  )
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

  const { data: shops = [], isLoading } = useQuery<ShopOption[]>({
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

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-1">My Shops</h3>
        <p className="text-sm text-gray-400">
          {shops.length > 1
            ? 'Your account is linked to multiple shops. Switch between them here.'
            : 'Your account is linked to this shop.'}
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
                  ? 'border-amber-500/40 bg-amber-500/10'
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
                  <span className="inline-flex items-center gap-1 text-xs text-amber-400 font-medium mt-0.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
                    Active
                  </span>
                )}
              </div>

              {!isCurrent && shops.length > 1 && (
                <button
                  onClick={() => handleSwitch(shop.id)}
                  disabled={!!switching}
                  className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-lg border border-white/20 text-gray-300 hover:text-white hover:border-white/40 hover:bg-white/10 transition-colors disabled:opacity-50 flex-shrink-0"
                >
                  {isSwitching ? (
                    <Spinner size="xs" className="border-white/40 border-t-white" />
                  ) : (
                    <ArrowRightLeft className="w-3.5 h-3.5" />
                  )}
                  {isSwitching ? 'Switching…' : 'Switch'}
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ============ LAYOUT ============

const SECTIONS = [
  { id: 'profile' as const, label: 'Profile', icon: User },
  { id: 'security' as const, label: 'Security', icon: Lock },
  { id: 'appearance' as const, label: 'Appearance', icon: Palette },
  { id: 'payments' as const, label: 'Payments', icon: CreditCard },
  { id: 'vehicles' as const, label: 'Vehicles', icon: Truck },
  { id: 'shops' as const, label: 'Shops', icon: Building2 },
]

export default function ProfileSettingsPage() {
  const [activeSection, setActiveSection] = useState<SettingsSection>('profile')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Profile Settings</h1>
        <p className="text-gray-400 mt-1">Manage your account and preferences</p>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Sidebar */}
        <div className="lg:w-56 flex-shrink-0">
          <div className="bg-white/5 rounded-xl border border-white/10 p-2 lg:p-3 lg:sticky lg:top-4">
            <nav className="flex lg:flex-col gap-1 overflow-x-auto lg:overflow-visible scrollbar-hide" style={{ WebkitOverflowScrolling: 'touch' }}>
              {SECTIONS.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={`flex items-center gap-1.5 lg:gap-2 px-2.5 lg:px-3 py-2 lg:py-2.5 rounded-lg text-xs lg:text-sm font-medium transition-colors flex-shrink-0 ${
                    activeSection === section.id
                      ? 'bg-amber-600/20 text-amber-400'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <section.icon className="w-4 h-4 flex-shrink-0" />
                  <span className="whitespace-nowrap">{section.label}</span>
                </button>
              ))}
            </nav>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 bg-white/5 rounded-xl p-6 border border-white/10 min-h-[500px]">
          {activeSection === 'profile' && <ProfileSection />}
          {activeSection === 'security' && <SecuritySection />}
          {activeSection === 'appearance' && <AppearanceSection />}
          {activeSection === 'payments' && <PaymentsSection />}
          {activeSection === 'vehicles' && <VehiclesSection />}
          {activeSection === 'shops' && <ShopsSection />}
        </div>
      </div>
    </div>
  )
}
