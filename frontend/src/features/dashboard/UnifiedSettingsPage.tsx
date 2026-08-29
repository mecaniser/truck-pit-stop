import { useState, useEffect, useId, useRef } from 'react'
import { LoadingLine } from '@/components/ui'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../../stores/authStore'
import type { User as UserType } from '../../types'
import api from '../../lib/api'
import { scrollSurfaceToTop } from '../../lib/scrollSurface'
import { tenantBrandingQueryKey } from '@/hooks/useTenantBranding'
import { formatUSPhone, isValidUSPhone } from '@/utils/phone'
import toast from 'react-hot-toast'
import { 
  User, Lock, CreditCard, Bell, Percent, QrCode, Globe, Building2,
  AlertCircle, ExternalLink, RefreshCw, Save, Trash2, Palette, Check, RotateCcw, Type,
  ChevronRight, ChevronDown, Zap, Shield, Settings2, Star, Truck, MessageSquare, Landmark, ShieldCheck, X
} from 'lucide-react'
import { useTheme, ACCENT_OPTIONS, FONT_FAMILY_OPTIONS, FONT_SIZE_OPTIONS, NOTIFICATION_POSITION_OPTIONS } from '../../contexts/ThemeContext'
import AppearanceSettingsPanel from './AppearanceSettingsPanel'
import GoogleReviewsPage from '@/features/reviews/GoogleReviewsPage'

// ============ HYBRID DESIGN SYSTEM (Industrial + Organic) ============
const industrialStyles = {
  // Base card - rounded with subtle accent glow
  card: `
    relative bg-zinc-900/80 backdrop-blur-sm border border-zinc-700/50 rounded-2xl
    before:absolute before:inset-0 before:rounded-2xl before:bg-gradient-to-br before:from-white/[0.02] before:to-transparent before:pointer-events-none
    overflow-hidden shadow-xl shadow-black/20
  `,
  // Input - softer rounded style
  input: `
    w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl
    text-zinc-100 text-sm
    placeholder-zinc-500 
    focus:outline-none focus:border-[var(--accent-500)] focus:bg-zinc-800 focus:ring-2 focus:ring-[var(--accent-500)]/20
    transition-all duration-200
    hover:border-zinc-500
  `,
  // Primary button - rounded with glow
  btnPrimary: `
    relative px-6 py-3 rounded-xl
    bg-[var(--accent-600)] hover:bg-[var(--accent-500)] 
    text-white font-semibold text-sm
    border border-[var(--accent-400)]/50
    transition-all duration-200
    hover:shadow-[0_0_24px_var(--accent-500)]
    active:scale-[0.98]
    disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none
  `,
  // Secondary button
  btnSecondary: `
    px-6 py-3 rounded-xl
    bg-zinc-800/80 hover:bg-zinc-700 
    text-zinc-300 font-semibold text-sm
    border border-zinc-600/50 hover:border-zinc-500
    transition-all duration-200
  `,
  // Danger button
  btnDanger: `
    px-6 py-3 rounded-xl
    bg-red-950/80 hover:bg-red-900 
    text-red-400 font-semibold text-sm
    border border-red-800/50 hover:border-red-600
    transition-all duration-200
  `,
  // Section header - keep uppercase for structure
  sectionHeader: `
    text-xs font-bold uppercase tracking-[0.2em] text-zinc-500
    border-b border-zinc-800/50 pb-2 mb-6
    flex items-center gap-3
  `,
  // Label - softer, not all caps
  label: `
    block text-xs font-medium text-zinc-400 mb-2
  `,
  // Status LED - keep the glow effects
  ledActive: `w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.9)] animate-pulse`,
  ledInactive: `w-2.5 h-2.5 rounded-full bg-zinc-600`,
  ledWarning: `w-2.5 h-2.5 rounded-full bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.9)] animate-pulse`,
  ledError: `w-2.5 h-2.5 rounded-full bg-red-400 shadow-[0_0_10px_rgba(248,113,113,0.9)]`,
}

// Staggered animation helper
const staggeredReveal = (index: number) => ({
  animationDelay: `${index * 50}ms`,
})

const isValidOptionalUrl = (value?: string) => {
  if (!value || !value.trim()) {
    return true
  }
  try {
    new URL(value.trim())
    return true
  } catch {
    return false
  }
}

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

const garageProfileSchema = z.object({
  name: z.string().min(1, 'Shop name is required').max(255, 'Maximum 255 characters'),
  address: z.string().optional().refine((value) => !value || value.length <= 500, {
    message: 'Maximum 500 characters',
  }),
  phone: z.string().optional().refine((value) => isValidUSPhone(value), {
    message: 'Invalid phone number',
  }),
  email: z.string().optional().refine((value) => !value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value), {
    message: 'Valid email required',
  }),
  website: z.string().optional()
    .refine((value) => !value || value.length <= 255, {
      message: 'Maximum 255 characters',
    })
    .refine((value) => isValidOptionalUrl(value), {
      message: 'Valid website URL required',
    }),
  logo_url: z.string().optional()
    .refine((value) => !value || value.length <= 500, {
      message: 'Maximum 500 characters',
    })
    .refine((value) => isValidOptionalUrl(value), {
      message: 'Valid logo URL required',
    }),
  partner_summary: z.string().optional().refine((value) => !value || value.length <= 280, {
    message: 'Maximum 280 characters',
  }),
  partner_services: z.string().optional().refine((value) => !value || value.length <= 180, {
    message: 'Maximum 180 characters',
  }),
  order_number_prefix: z.string().optional()
    .refine((value) => !value || value.length <= 10, {
      message: 'Maximum 10 characters',
    })
    .refine((value) => !value || /^[A-Za-z0-9]+$/.test(value), {
      message: 'Letters and numbers only',
    }),
})

type ProfileFormData = z.infer<typeof profileSchema>
type PasswordFormData = z.infer<typeof passwordSchema>
type GarageProfileFormData = z.infer<typeof garageProfileSchema>

// ============ TYPES ============
type SettingsSection = 'profile' | 'security' | 'appearance' | 'integrations' | 'garageProfile' | 'payments' | 'notifications' | 'fees' | 'fleet' | 'googleReviews' | 'workforce'

interface ConnectStatus {
  configured: boolean
  is_connected: boolean
  onboarding_complete: boolean
  charges_enabled: boolean
  payouts_enabled: boolean
  account_id: string | null
  connection_type: 'stripe_hosted' | 'standard_oauth' | 'express_legacy' | null
  verification_status: 'not_connected' | 'setup_incomplete' | 'needs_information' | 'under_review' | 'restricted' | 'unreachable' | 'active'
  requirements: string[]
  mode: 'test' | 'live' | 'unknown'
  account_dashboard_url: string | null
  available_balance: string | null
  pending_balance: string | null
  last_payout_amount: string | null
  last_payout_status: string | null
  last_payout_at: string | null
  recent_payments: Array<{
    invoice_number: string
    amount: string
    status: string
    payment_intent_id: string | null
    created_at: string
  }>
}

interface QuickBooksConnectionStatus {
  configured: boolean
  is_connected: boolean
  realm_id: string | null
  scopes: string[]
  connected_at: string | null
  token_health: 'healthy' | 'refresh_required' | 'reconnect_required' | 'not_connected'
  last_token_refresh_at: string | null
  last_token_refresh_error: string | null
  last_webhook_at: string | null
  last_webhook_event: string | null
  last_webhook_error: string | null
}

interface QuickBooksPlatformStatus {
  platform_ready: boolean
  callback_url: string
  webhook_ready: boolean
  webhook_url: string
  scopes: string[]
}

interface GoogleReviewsPlatformStatus {
  platform_ready: boolean
  callback_url: string
  pubsub_url: string
  pubsub_auth_ready: boolean
}

interface StripePlatformStatus {
  platform_ready: boolean
  onboarding_mode: string
}

function apiErrorDetail(error: unknown, fallback: string): string {
  if (!error || typeof error !== 'object') return fallback
  const response = (error as { response?: { data?: { detail?: unknown } } }).response
  return typeof response?.data?.detail === 'string' ? response.data.detail : fallback
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
  labor_rate: number
  internal_labor_rate: number
  fleet_company_name: string | null
  default_fleet_authority_customer_id: string | null
  default_fleet_authority_company_name: string | null
}

interface FleetManager {
  id: string
  name: string
  email: string
}

interface FleetSettings {
  internal_labor_rate: number
  fleet_company_name: string | null
  default_fleet_authority_customer_id: string | null
  default_fleet_authority_company_name: string | null
  fleet_managers: FleetManager[]
  truck_count: number
}

interface FleetBoardTruck {
  id: string
  unit_number?: string | null
  year?: number | null
  make?: string | null
  model?: string | null
  vin?: string | null
  odometer?: number | null
  status: string
}

interface WorkforceSettings {
  timezone: string
  default_core_hours_minutes: number
  default_shift_start_local: string
  default_shift_end_local: string
}

interface GarageProfile {
  name: string
  slug: string
  address: string | null
  phone: string | null
  email: string | null
  website: string | null
  logo_url: string | null
  partner_summary: string | null
  partner_services: string | null
  order_number_prefix: string | null
  effective_order_number_prefix: string
}

// ============ INDUSTRIAL COMPONENTS ============

function IndustrialCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`${industrialStyles.card} db-settings-floating-card ${className}`}>
      <div className="relative z-10">{children}</div>
    </div>
  )
}

function StatusLED({ status }: { status: 'active' | 'inactive' | 'warning' | 'error' }) {
  const styles = {
    active: industrialStyles.ledActive,
    inactive: industrialStyles.ledInactive,
    warning: industrialStyles.ledWarning,
    error: industrialStyles.ledError,
  }
  return <div className={styles[status]} />
}

function IndustrialBadge({ children, variant = 'default' }: { children: React.ReactNode; variant?: 'default' | 'success' | 'warning' | 'error' }) {
  const variants = {
    default: 'bg-zinc-800/80 text-zinc-300 border-zinc-600/50',
    success: 'bg-emerald-950/80 text-emerald-400 border-emerald-700/50',
    warning: 'bg-amber-950/80 text-amber-400 border-amber-700/50',
    error: 'bg-red-950/80 text-red-400 border-red-700/50',
  }
  return (
    <span className={`inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold rounded-full border whitespace-nowrap ${variants[variant]}`}>
      {children}
    </span>
  )
}

function PaymentIntegrationPanel({
  icon,
  title,
  summary,
  status,
  open,
  onOpenChange,
  children,
}: {
  icon: React.ReactNode
  title: string
  summary: string
  status?: { label: string; variant: 'success' | 'warning' | 'error' | 'default'; led: 'active' | 'inactive' | 'warning' | 'error' }
  open: boolean
  onOpenChange: (nextOpen: boolean) => void
  children: React.ReactNode
}) {
  const triggerId = useId()
  const panelId = useId()

  return (
    <IndustrialCard className="db-settings-payment-card">
      <button
        id={triggerId}
        type="button"
        onClick={() => onOpenChange(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        className="grid w-full grid-cols-[2.5rem_minmax(0,1fr)_1.25rem] items-center gap-x-4 gap-y-3 px-5 py-4 text-left transition-colors hover:bg-white/[0.02] sm:flex sm:gap-4 sm:px-8 sm:py-5"
      >
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-zinc-700/50 bg-zinc-800/60 text-[var(--accent-400)]">
          {icon}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-zinc-100">{title}</span>
          <span className="mt-1 block text-sm text-zinc-400">{summary}</span>
        </span>
        {status && (
          <span className="col-span-2 col-start-2 justify-self-start sm:ml-auto">
            <IndustrialBadge variant={status.variant}>
              <StatusLED status={status.led} />
              {status.label}
            </IndustrialBadge>
          </span>
        )}
        <ChevronDown className={`col-start-3 row-start-1 h-5 w-5 shrink-0 text-zinc-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div id={panelId} role="region" aria-labelledby={triggerId} className="border-t border-zinc-800/70 px-6 py-6 sm:px-8">
          {children}
        </div>
      )}
    </IndustrialCard>
  )
}

function DisconnectStripeDialog({ legacy, pending, onCancel, onConfirm }: {
  legacy: boolean
  pending: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) onCancel()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onCancel, pending])

  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center bg-black/70 p-4 backdrop-blur-sm"
      onMouseDown={(event) => event.target === event.currentTarget && !pending && onCancel()}
    >
      <div role="alertdialog" aria-modal="true" aria-labelledby="disconnect-stripe-title" aria-describedby="disconnect-stripe-description" className="w-full max-w-md rounded-xl border border-red-800/50 bg-zinc-950 p-6 shadow-2xl shadow-black/60">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-red-800/50 bg-red-950/70 text-red-400">
              <AlertCircle className="h-5 w-5" />
            </span>
            <h3 id="disconnect-stripe-title" className="text-lg font-semibold text-zinc-100">
              {legacy ? 'Disconnect legacy Stripe connection?' : 'Disconnect Stripe account?'}
            </h3>
          </div>
          <button type="button" onClick={onCancel} disabled={pending} aria-label="Close confirmation" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-50">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p id="disconnect-stripe-description" className="mt-4 text-sm leading-6 text-zinc-400">
          DieselBridge will stop routing new invoice payments to this connection. The Stripe account and its payment history will not be deleted.
        </p>
        {legacy && (
          <p className="mt-3 rounded-lg border border-amber-800/40 bg-amber-950/20 px-3 py-2 text-sm text-amber-200">
            After disconnecting, you can set up the new Stripe-hosted connection.
          </p>
        )}
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" onClick={onCancel} disabled={pending} className={industrialStyles.btnSecondary}>Cancel</button>
          <button type="button" onClick={onConfirm} disabled={pending} className={industrialStyles.btnDanger}>
            {pending ? 'Disconnecting...' : 'Disconnect Stripe'}
          </button>
        </div>
      </div>
    </div>
  )
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
    return hasError
      ? `${industrialStyles.input} border-red-500 focus:border-red-400`
      : industrialStyles.input
  }

  const getRoleBadge = () => {
    switch (user?.role) {
      case 'super_admin': return { label: 'SUPER ADMIN', variant: 'warning' as const }
      case 'garage_owner': return { label: 'SHOP OWNER', variant: 'success' as const }
      case 'garage_admin': return { label: 'SHOP ADMIN', variant: 'default' as const }
      case 'fleet_manager': return { label: 'FLEET MANAGER', variant: 'default' as const }
      default: return { label: 'STAFF', variant: 'default' as const }
    }
  }

  const roleBadge = getRoleBadge()

  return (
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      {/* Profile Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          {/* Avatar */}
          <div className="relative">
            <div className="w-16 h-16 sm:w-20 sm:h-20 bg-zinc-800/80 border border-zinc-600/50 rounded-2xl flex items-center justify-center">
              <User className="w-8 h-8 sm:w-10 sm:h-10 text-[var(--accent-400)]" />
            </div>
            <div className="absolute -bottom-1 -right-1 w-4 h-4 bg-emerald-500 rounded-full border-2 border-zinc-950 shadow-[0_0_8px_rgba(52,211,153,0.6)]" />
          </div>
          <div>
            <h2 className="text-xl sm:text-2xl font-bold text-zinc-100">
              {user?.first_name} {user?.last_name}
            </h2>
            <p className="text-sm text-zinc-500 mt-1">{user?.email}</p>
          </div>
        </div>
        <IndustrialBadge variant={roleBadge.variant}>
          <StatusLED status={roleBadge.variant === 'success' ? 'active' : roleBadge.variant === 'warning' ? 'warning' : 'inactive'} />
          {roleBadge.label}
        </IndustrialBadge>
      </div>

      <IndustrialCard className="p-6 sm:p-8">
        {!isEditing ? (
          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              {[
                { label: 'First Name', value: user?.first_name },
                { label: 'Last Name', value: user?.last_name },
                { label: 'Email', value: user?.email },
                { label: 'Phone', value: user?.phone ? formatUSPhone(user.phone) : '—' },
              ].map((field, i) => (
                <div key={field.label} style={staggeredReveal(i)} className="animate-[fadeIn_0.3s_ease-out_forwards] opacity-0">
                  <label className={industrialStyles.label}>{field.label}</label>
                  <p className="text-lg text-zinc-100 border-b border-zinc-800/50 pb-2">
                    {field.value}
                  </p>
                </div>
              ))}
            </div>
            <button
              onClick={() => setIsEditing(true)}
              className={industrialStyles.btnPrimary}
            >
              <span className="flex items-center gap-2">
                <Settings2 className="w-4 h-4" />
                Edit Profile
              </span>
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div>
                <label className={industrialStyles.label}>First Name</label>
                <input {...register('first_name')} className={inputClasses(!!errors.first_name)} />
                {errors.first_name && <p className="mt-2 text-xs text-red-400">{errors.first_name.message}</p>}
              </div>
              <div>
                <label className={industrialStyles.label}>Last Name</label>
                <input {...register('last_name')} className={inputClasses(!!errors.last_name)} />
                {errors.last_name && <p className="mt-2 text-xs text-red-400">{errors.last_name.message}</p>}
              </div>
            </div>
            <div>
              <label className={industrialStyles.label}>Email</label>
              <input {...register('email')} type="email" className={inputClasses(!!errors.email)} />
              {errors.email && <p className="mt-2 text-xs text-red-400">{errors.email.message}</p>}
            </div>
            <div>
              <label className={industrialStyles.label}>Phone</label>
              <input {...register('phone')} className={inputClasses(!!errors.phone)} placeholder="(555) 123-4567" />
              {errors.phone && <p className="mt-2 text-xs text-red-400">{errors.phone.message}</p>}
            </div>
            
            {currentEmailValue !== originalEmail && (
              <div className="p-4 bg-amber-950/50 border border-amber-700/50 rounded-xl">
                <label className={`${industrialStyles.label} text-amber-400`}>
                  <Zap className="w-3 h-3 inline mr-2" />
                  Password Required for Email Change
                </label>
                <div className="relative mt-2">
                  <input
                    {...register('password')}
                    type={showPassword ? 'text' : 'password'}
                    className={inputClasses(false)}
                    placeholder="Enter your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium text-zinc-500 hover:text-zinc-300"
                  >
                    {showPassword ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>
            )}

            <div className="flex gap-4 pt-4 border-t border-zinc-800/50">
              <button
                type="button"
                onClick={() => { setIsEditing(false); reset() }}
                className={industrialStyles.btnSecondary}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={updateMutation.isPending}
                className={industrialStyles.btnPrimary}
              >
                {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </form>
        )}
      </IndustrialCard>
    </div>
  )
}

function GarageProfileSection() {
  const { user, setUser } = useAuthStore()
  const queryClient = useQueryClient()
  const [isEditing, setIsEditing] = useState(false)
  const tenantBrandingKey = tenantBrandingQueryKey(user?.tenant_id)

  const { data: garageProfile, isLoading } = useQuery<GarageProfile>({
    queryKey: ['garage-profile'],
    queryFn: async () => {
      const response = await api.get('/admin/garage-profile')
      return response.data
    },
  })

  const { register, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm<GarageProfileFormData>({
    resolver: zodResolver(garageProfileSchema),
  })

  useEffect(() => {
    if (!garageProfile || isEditing) return
    reset({
      name: garageProfile.name || '',
      address: garageProfile.address || '',
      phone: garageProfile.phone || '',
      email: garageProfile.email || '',
      website: garageProfile.website || '',
      logo_url: garageProfile.logo_url || '',
      partner_summary: garageProfile.partner_summary || '',
      partner_services: garageProfile.partner_services || '',
      order_number_prefix: garageProfile.order_number_prefix || '',
    })
  }, [garageProfile, isEditing, reset])

  const websiteValue = watch('website') || ''
  const logoUrlValue = watch('logo_url') || ''

  const syncTenantBranding = (updated: GarageProfile) => {
    queryClient.setQueryData(['garage-profile'], updated)
    queryClient.setQueryData(tenantBrandingKey, {
      name: updated.name,
      slug: updated.slug,
      logo_url: updated.logo_url,
    })
    if (user) {
      setUser({
        ...user,
        tenant_name: updated.name,
        tenant_slug: updated.slug,
        tenant_logo_url: updated.logo_url,
      })
    }
  }

  const updateMutation = useMutation({
    mutationFn: async (data: GarageProfileFormData) => {
      const payload = {
        name: data.name.trim(),
        address: data.address?.trim() || null,
        phone: data.phone?.trim() || null,
        email: data.email?.trim() || null,
        website: data.website?.trim() || null,
        logo_url: data.logo_url?.trim() || null,
        partner_summary: data.partner_summary?.trim() || null,
        partner_services: data.partner_services?.trim() || null,
        order_number_prefix: data.order_number_prefix?.trim() || null,
      }
      const response = await api.put('/admin/garage-profile', payload)
      return response.data as GarageProfile
    },
    onSuccess: (updated) => {
      syncTenantBranding(updated)
      setIsEditing(false)
      toast.success('Shop profile updated')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update garage profile')
    },
  })

  const importLogoMutation = useMutation({
    mutationFn: async (website: string) => {
      const response = await api.post('/admin/garage-profile/import-logo', {
        website: website.trim(),
      })
      return response.data as GarageProfile
    },
    onSuccess: (updated) => {
      syncTenantBranding(updated)
      setValue('website', updated.website || '', { shouldDirty: false, shouldValidate: true })
      setValue('logo_url', updated.logo_url || '', { shouldDirty: false, shouldValidate: true })
      toast.success('Logo imported from website')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to import logo')
    },
  })

  const inputClasses = (hasError: boolean) => {
    return hasError
      ? `${industrialStyles.input} border-red-500 focus:border-red-400`
      : industrialStyles.input
  }

  if (isLoading && !garageProfile) {
    return (
      <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
        <IndustrialCard className="p-6 sm:p-8">
          <div className={industrialStyles.sectionHeader}>
            <Building2 className="w-4 h-4 text-[var(--accent-400)]" />
            <span>Shop Profile</span>
          </div>
          <LoadingLine className="text-zinc-400">Loading shop profile…</LoadingLine>
        </IndustrialCard>
      </div>
    )
  }

  const onSubmit = (data: GarageProfileFormData) => {
    updateMutation.mutate(data)
  }

  const openEditMode = () => {
    if (garageProfile) {
      reset({
        name: garageProfile.name || '',
        address: garageProfile.address || '',
        phone: garageProfile.phone || '',
        email: garageProfile.email || '',
        website: garageProfile.website || '',
        logo_url: garageProfile.logo_url || '',
        partner_summary: garageProfile.partner_summary || '',
        partner_services: garageProfile.partner_services || '',
        order_number_prefix: garageProfile.order_number_prefix || '',
      })
    }
    setIsEditing(true)
  }

  const handleImportLogo = () => {
    const website = websiteValue.trim()
    if (!website) {
      toast.error('Add a website URL before importing a logo')
      return
    }
    importLogoMutation.mutate(website)
  }

  const handleClearLogo = () => {
    setValue('logo_url', '', { shouldDirty: true, shouldValidate: true })
  }

  return (
    <div className="db-settings-shop-profile space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Building2 className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Shop Profile</span>
        </div>

        {!isEditing ? (
          <div className="space-y-6">
            <div className="db-settings-shop-profile__panel rounded-2xl border border-zinc-700/50 bg-zinc-950/50 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <label className={industrialStyles.label}>Shop Logo</label>
                </div>
                {garageProfile?.logo_url && (
                  <a
                    href={garageProfile.logo_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 text-sm text-[var(--accent-400)] hover:text-[var(--accent-300)]"
                  >
                    Open logo
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
              </div>

              <div className="db-settings-shop-profile__logo-canvas mt-4 flex min-h-[160px] items-center justify-center rounded-2xl border border-dashed border-zinc-700/60 bg-zinc-900/50 p-6">
                {garageProfile?.logo_url ? (
                  <img
                    src={garageProfile.logo_url}
                    alt={`${garageProfile.name} logo`}
                    className="max-h-24 w-auto max-w-full object-contain"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <div className="text-center text-sm text-zinc-500">
                    <p>Use the website importer or paste a logo URL in Shop Profile settings.</p>
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              {[
                { label: 'Shop Name', value: garageProfile?.name || '—' },
                { label: 'Shop Slug', value: garageProfile?.slug || '—' },
                { label: 'Shop Email', value: garageProfile?.email || '—' },
                { label: 'Shop Phone', value: garageProfile?.phone ? formatUSPhone(garageProfile.phone) : '—' },
                { label: 'Website', value: garageProfile?.website || '—' },
                { label: 'Address', value: garageProfile?.address || '—' },
                {
                  label: 'Repair Order Prefix',
                  value: garageProfile
                    ? `${garageProfile.effective_order_number_prefix}-000001${garageProfile.order_number_prefix ? '' : ' (auto)'}`
                    : '—',
                },
              ].map((field, index) => (
                <div key={field.label} style={staggeredReveal(index)} className="animate-[fadeIn_0.3s_ease-out_forwards] opacity-0">
                  <label className={industrialStyles.label}>{field.label}</label>
                  <p className="text-lg text-zinc-100 border-b border-zinc-800/50 pb-2 break-words">
                    {field.value}
                  </p>
                </div>
              ))}
            </div>

            <div className="db-settings-shop-profile__panel rounded-2xl border border-zinc-700/50 bg-zinc-950/50 p-5">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <label className={industrialStyles.label}>Landing Page Partner Profile</label>
                  <p className="text-sm text-zinc-500">
                    Approved businesses appear automatically. These fields control the public summary shown on the landing page.
                  </p>
                </div>
                <div className="shrink-0">
                  <IndustrialBadge variant="success">
                    Public profile
                  </IndustrialBadge>
                </div>
              </div>

              <div className="mt-5 grid gap-5 sm:grid-cols-2">
                <div>
                  <label className={industrialStyles.label}>Summary</label>
                  <p className="text-base leading-7 text-zinc-100">
                    {garageProfile?.partner_summary || 'Add a short summary to describe this shop on the landing page.'}
                  </p>
                </div>
                <div>
                  <label className={industrialStyles.label}>Service Focus</label>
                  <p className="text-base leading-7 text-zinc-100">
                    {garageProfile?.partner_services || 'Add specialties, service lanes, or coverage areas.'}
                  </p>
                </div>
              </div>
            </div>

            <button
              onClick={openEditMode}
              className={industrialStyles.btnPrimary}
            >
              <span className="flex items-center gap-2">
                <Settings2 className="w-4 h-4" />
                Edit Shop Profile
              </span>
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            <div>
              <label className={industrialStyles.label}>Shop Name</label>
              <input {...register('name')} className={inputClasses(!!errors.name)} />
              {errors.name && <p className="mt-2 text-xs text-red-400">{errors.name.message}</p>}
            </div>

            <div>
              <label className={industrialStyles.label}>Shop Slug (read-only)</label>
              <input value={garageProfile?.slug || ''} className={`${industrialStyles.input} opacity-70`} disabled />
            </div>

            <div>
              <label className={industrialStyles.label}>Shop Email</label>
              <input {...register('email')} type="email" className={inputClasses(!!errors.email)} placeholder="shop@example.com" />
              {errors.email && <p className="mt-2 text-xs text-red-400">{errors.email.message}</p>}
            </div>

            <div>
              <label className={industrialStyles.label}>Shop Phone</label>
              <input {...register('phone')} className={inputClasses(!!errors.phone)} placeholder="(555) 123-4567" />
              {errors.phone && <p className="mt-2 text-xs text-red-400">{errors.phone.message}</p>}
            </div>

            <div>
              <label className={industrialStyles.label}>Website</label>
              <input {...register('website')} className={inputClasses(!!errors.website)} placeholder="https://example.com" />
              {errors.website && <p className="mt-2 text-xs text-red-400">{errors.website.message}</p>}
            </div>

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
              <div className="space-y-4">
                <div>
                  <label className={industrialStyles.label}>Logo URL</label>
                  <input
                    {...register('logo_url')}
                    className={inputClasses(!!errors.logo_url)}
                    placeholder="https://cdn.example.com/logo.png"
                  />
                  {errors.logo_url && <p className="mt-2 text-xs text-red-400">{errors.logo_url.message}</p>}
                  <p className="mt-2 text-xs text-zinc-500">
                    Paste a logo URL manually or import from the website above.
                  </p>
                </div>

                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={handleImportLogo}
                    disabled={importLogoMutation.isPending || !websiteValue.trim()}
                    className={industrialStyles.btnSecondary}
                  >
                    <span className="flex items-center gap-2">
                      <RefreshCw className={`h-4 w-4 ${importLogoMutation.isPending ? 'animate-spin' : ''}`} />
                      {importLogoMutation.isPending ? 'Importing...' : 'Import from Website'}
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={handleClearLogo}
                    disabled={!logoUrlValue}
                    className={industrialStyles.btnSecondary}
                  >
                    <span className="flex items-center gap-2">
                      <Trash2 className="h-4 w-4" />
                      Clear Logo
                    </span>
                  </button>

                  {logoUrlValue && (
                    <a
                      href={logoUrlValue}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={industrialStyles.btnSecondary}
                    >
                      <span className="flex items-center gap-2">
                        <ExternalLink className="h-4 w-4" />
                        Open Logo
                      </span>
                    </a>
                  )}
                </div>
              </div>

              <div className="db-settings-shop-profile__panel rounded-2xl border border-zinc-700/50 bg-zinc-950/50 p-4">
                <label className={industrialStyles.label}>Logo Preview</label>
                <div className="db-settings-shop-profile__logo-canvas flex min-h-[180px] items-center justify-center rounded-2xl border border-dashed border-zinc-700/60 bg-zinc-900/50 p-5">
                  {logoUrlValue ? (
                    <img
                      src={logoUrlValue}
                      alt="Tenant logo preview"
                      className="max-h-24 w-auto max-w-full object-contain"
                      referrerPolicy="no-referrer"
                    />
                  ) : (
                    <p className="text-center text-sm text-zinc-500">
                      No logo selected yet.
                    </p>
                  )}
                </div>
              </div>
            </div>

            <div>
              <label className={industrialStyles.label}>Address</label>
              <textarea {...register('address')} className={`${inputClasses(!!errors.address)} min-h-[96px]`} />
              {errors.address && <p className="mt-2 text-xs text-red-400">{errors.address.message}</p>}
            </div>

            <div>
              <label className={industrialStyles.label}>Repair Order Prefix</label>
              <input
                {...register('order_number_prefix')}
                className={inputClasses(!!errors.order_number_prefix)}
                placeholder={garageProfile?.effective_order_number_prefix || 'TPS'}
                maxLength={10}
                style={{ textTransform: 'uppercase' }}
              />
              {errors.order_number_prefix && <p className="mt-2 text-xs text-red-400">{errors.order_number_prefix.message}</p>}
              <p className="mt-2 text-xs text-zinc-500">
                New repair orders will be numbered like "{garageProfile?.effective_order_number_prefix || 'TPS'}-000123".
                Leave blank to auto-derive from the shop name.
              </p>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <div>
                <label className={industrialStyles.label}>Landing Page Summary</label>
                <textarea
                  {...register('partner_summary')}
                  className={`${inputClasses(!!errors.partner_summary)} min-h-[112px]`}
                  placeholder="Short description for the public partner section"
                />
                {errors.partner_summary && <p className="mt-2 text-xs text-red-400">{errors.partner_summary.message}</p>}
                <p className="mt-2 text-xs text-zinc-500">
                  Keep this short. It appears in the public partner section for approved businesses.
                </p>
              </div>

              <div>
                <label className={industrialStyles.label}>Service Focus</label>
                <textarea
                  {...register('partner_services')}
                  className={`${inputClasses(!!errors.partner_services)} min-h-[112px]`}
                  placeholder="Roadside repair, diagnostics, fleet PM, mobile service"
                />
                {errors.partner_services && <p className="mt-2 text-xs text-red-400">{errors.partner_services.message}</p>}
                <p className="mt-2 text-xs text-zinc-500">
                  Use this for specialties, lane types, service area, or the work this garage wants highlighted.
                </p>
              </div>
            </div>

            <div className="flex gap-4 pt-4 border-t border-zinc-800/50">
              <button
                type="button"
                onClick={() => {
                  setIsEditing(false)
                  if (garageProfile) {
                    reset({
                      name: garageProfile.name || '',
                      address: garageProfile.address || '',
                      phone: garageProfile.phone || '',
                      email: garageProfile.email || '',
                      website: garageProfile.website || '',
                      logo_url: garageProfile.logo_url || '',
                      partner_summary: garageProfile.partner_summary || '',
                      partner_services: garageProfile.partner_services || '',
                      order_number_prefix: garageProfile.order_number_prefix || '',
                    })
                  }
                }}
                className={industrialStyles.btnSecondary}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={updateMutation.isPending}
                className={industrialStyles.btnPrimary}
              >
                {updateMutation.isPending ? 'Saving...' : 'Save Shop Profile'}
              </button>
            </div>
          </form>
        )}
      </IndustrialCard>
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

  return (
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Shield className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Password Management</span>
        </div>
        
        <p className="text-sm text-zinc-400 mb-6">
          Update your password to maintain account security.
        </p>

        {!showForm ? (
          <button
            onClick={() => setShowForm(true)}
            className={industrialStyles.btnPrimary}
          >
            <span className="flex items-center gap-2">
              <Lock className="w-4 h-4" />
              Change Password
            </span>
          </button>
        ) : (
          <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-6 max-w-md">
            <div>
              <label className={industrialStyles.label}>Current Password</label>
              <input {...register('current_password')} type="password" className={errors.current_password ? `${industrialStyles.input} border-red-500` : industrialStyles.input} />
              {errors.current_password && <p className="mt-2 text-xs text-red-400">{errors.current_password.message}</p>}
            </div>
            <div>
              <label className={industrialStyles.label}>New Password</label>
              <input {...register('new_password')} type="password" className={errors.new_password ? `${industrialStyles.input} border-red-500` : industrialStyles.input} />
              {errors.new_password && <p className="mt-2 text-xs text-red-400">{errors.new_password.message}</p>}
            </div>
            <div>
              <label className={industrialStyles.label}>Confirm New Password</label>
              <input {...register('confirm_password')} type="password" className={errors.confirm_password ? `${industrialStyles.input} border-red-500` : industrialStyles.input} />
              {errors.confirm_password && <p className="mt-2 text-xs text-red-400">{errors.confirm_password.message}</p>}
            </div>
            <div className="flex gap-4">
              <button
                type="button"
                onClick={() => { setShowForm(false); reset() }}
                className={industrialStyles.btnSecondary}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={mutation.isPending}
                className={industrialStyles.btnPrimary}
              >
                {mutation.isPending ? 'Changing...' : 'Update Password'}
              </button>
            </div>
          </form>
        )}
      </IndustrialCard>

      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <AlertCircle className="w-4 h-4 text-red-400" />
          <span>Session Control</span>
        </div>
        
        <p className="text-sm text-zinc-400 mb-6">
          Terminate your current session on this device.
        </p>
        
        <button
          onClick={() => { logout(); navigate('/login') }}
          className={industrialStyles.btnDanger}
        >
          <span className="flex items-center gap-2">
            <Zap className="w-4 h-4" />
            Sign Out
          </span>
        </button>
      </IndustrialCard>
    </div>
  )
}

function PaymentsSection() {
  const [isRedirecting, setIsRedirecting] = useState(false)
  const [disconnectKind, setDisconnectKind] = useState<'current' | 'legacy' | null>(null)
  const [openPaymentPanel, setOpenPaymentPanel] = useState<'stripe' | 'zelle' | 'quickbooks' | null>('stripe')
  const [searchParams, setSearchParams] = useSearchParams()

  const { data: status, isLoading, refetch } = useQuery<ConnectStatus>({
    queryKey: ['stripe-connect-status'],
    queryFn: async () => {
      const response = await api.get('/stripe/connect/status')
      return response.data
    },
    refetchInterval: 30_000,
  })

  useEffect(() => {
    const result = searchParams.get('stripe')
    if (result === 'return') {
      toast.success('Stripe setup saved. We are checking your account status.')
      refetch()
      setSearchParams({}, { replace: true })
    } else if (result === 'refresh') {
      toast('Your Stripe setup session expired. Continue setup to resume.')
      refetch()
      setSearchParams({}, { replace: true })
    } else if (result) {
      const messages: Record<string, string> = {
        error: 'Stripe could not complete setup. Please try again.',
      }
      toast.error(messages[result] || 'Stripe could not complete the connection.')
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, refetch, setSearchParams])

  const connectMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/stripe/connect/connect')
      return response.data
    },
    onSuccess: (data) => {
      setIsRedirecting(true)
      window.location.href = data.url
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to start Stripe connection')
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: async () => (await api.post('/stripe/connect/disconnect')).data,
    onSuccess: () => {
      setDisconnectKind(null)
      toast.success('Stripe connection removed. Your Stripe account was not deleted.')
      refetch()
    },
    onError: (error: unknown) => toast.error(apiErrorDetail(error, 'Unable to disconnect Stripe account')),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="w-8 h-8 border-2 border-zinc-600 border-t-[var(--accent-400)] rounded-full animate-spin" />
      </div>
    )
  }

  const getStatusConfig = () => {
    if (!status?.is_connected) {
      if (!status?.configured) {
        return { led: 'warning' as const, title: 'PLATFORM SETUP REQUIRED', desc: 'DieselBridge must finish its Stripe platform configuration before this shop can connect.' }
      }
      return { led: 'inactive' as const, title: 'NOT SET UP', desc: 'Set up your Stripe merchant account to receive invoice payments.' }
    }
    if (status.connection_type === 'express_legacy') return { led: 'warning' as const, title: 'LEGACY CONNECTION', desc: 'This account still uses the previous Stripe Express setup.' }
    if (status.verification_status === 'under_review') {
      return { led: 'warning' as const, title: 'VERIFICATION IN PROGRESS', desc: 'Stripe is reviewing your submitted business details. No action is needed unless Stripe requests more information.' }
    }
    if (status.verification_status === 'needs_information') {
      return { led: 'warning' as const, title: 'ACTION REQUIRED', desc: 'Stripe needs additional business or payout details before payments can be enabled.' }
    }
    if (status.verification_status === 'restricted') {
      return { led: 'error' as const, title: 'ACCOUNT RESTRICTED', desc: 'Stripe needs updated information before this account can accept payments or receive payouts.' }
    }
    if (status.verification_status === 'unreachable') {
      return { led: 'error' as const, title: 'CONNECTION UNAVAILABLE', desc: 'This Stripe account no longer exists or cannot be accessed. Reset the connection to start again.' }
    }
    if (!status.onboarding_complete) {
      return { led: 'warning' as const, title: 'SETUP INCOMPLETE', desc: 'Please finish the Stripe onboarding process.' }
    }
    return { led: 'active' as const, title: 'CONNECTED & ACTIVE', desc: 'Payments will be deposited to your account.' }
  }

  const statusConfig = getStatusConfig()
  const formatStripeAmount = (value: string | null) => value === null
    ? 'Unavailable'
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value))
  const accountLabel = status?.account_id
    ? `${status.account_id.slice(0, 8)}...${status.account_id.slice(-4)}`
    : 'Not connected'

  return (
    <div className="db-settings-payments space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <h2 className="sr-only">Payments &amp; Accounting</h2>
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 px-4 py-3 text-sm text-zinc-400">
        Manage every invoice settlement method here: Stripe collects online card payments, Zelle is confirmed by shop staff, and QuickBooks synchronizes finalized invoices and Intuit payment settlement.
      </div>
      <PaymentIntegrationPanel
        icon={<CreditCard className="h-5 w-5" />}
        title="Stripe Payments"
        summary={statusConfig.desc}
        status={{
          label: statusConfig.title,
          variant: statusConfig.led === 'active' ? 'success' : statusConfig.led === 'error' ? 'error' : statusConfig.led === 'warning' ? 'warning' : 'default',
          led: statusConfig.led,
        }}
        open={openPaymentPanel === 'stripe'}
        onOpenChange={(nextOpen) => setOpenPaymentPanel(nextOpen ? 'stripe' : null)}
      >

        <div className="flex items-start gap-4 mb-6">
          <div className="p-3 bg-zinc-800/60 border border-zinc-700/50 rounded-xl">
            <StatusLED status={statusConfig.led} />
          </div>
          <div>
            <h4 className="font-semibold text-zinc-100">{statusConfig.title}</h4>
            <p className="text-sm text-zinc-400 mt-1">{statusConfig.desc}</p>
          </div>
        </div>

        {status?.is_connected && status.onboarding_complete && (
          <div className="flex flex-wrap gap-3 mb-6">
            <IndustrialBadge variant={status.charges_enabled ? 'success' : 'error'}>
              <StatusLED status={status.charges_enabled ? 'active' : 'error'} />
              Charges {status.charges_enabled ? 'Enabled' : 'Disabled'}
            </IndustrialBadge>
            <IndustrialBadge variant={status.payouts_enabled ? 'success' : 'error'}>
              <StatusLED status={status.payouts_enabled ? 'active' : 'error'} />
              Payouts {status.payouts_enabled ? 'Enabled' : 'Disabled'}
            </IndustrialBadge>
          </div>
        )}

        {status?.is_connected && status.requirements.length > 0 && status.verification_status !== 'under_review' && (
          <div className="mb-6 rounded-lg border border-amber-800/40 bg-amber-950/20 px-4 py-3">
            <p className="text-sm font-medium text-amber-200">Stripe needs:</p>
            <p className="mt-1 text-sm text-amber-100/80">{status.requirements.join(', ')}</p>
          </div>
        )}

        {status?.is_connected && (
          <div className="mb-6 border-y border-zinc-800/70 py-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-zinc-100">Stripe account activity</p>
                <p className="mt-1 text-xs text-zinc-500">Direct card charges are created in this connected account.</p>
              </div>
              <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${status.mode === 'live' ? 'border-emerald-700/50 bg-emerald-950/30 text-emerald-300' : 'border-sky-700/50 bg-sky-950/30 text-sky-300'}`}>
                {status.mode === 'live' ? 'Live mode' : status.mode === 'test' ? 'Test mode' : 'Stripe mode unavailable'}
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="border border-zinc-800 bg-zinc-950/35 px-3 py-3">
                <p className="text-xs text-zinc-500">Connected account</p>
                <p className="mt-1 font-mono text-sm text-zinc-200">{accountLabel}</p>
              </div>
              <div className="border border-zinc-800 bg-zinc-950/35 px-3 py-3">
                <p className="text-xs text-zinc-500">Available balance</p>
                <p className="mt-1 text-sm font-semibold text-zinc-100">{formatStripeAmount(status.available_balance)}</p>
              </div>
              <div className="border border-zinc-800 bg-zinc-950/35 px-3 py-3">
                <p className="text-xs text-zinc-500">Pending balance</p>
                <p className="mt-1 text-sm font-semibold text-zinc-100">{formatStripeAmount(status.pending_balance)}</p>
              </div>
              <div className="border border-zinc-800 bg-zinc-950/35 px-3 py-3">
                <p className="text-xs text-zinc-500">Latest payout</p>
                <p className="mt-1 text-sm font-semibold text-zinc-100">{status.last_payout_amount ? `${formatStripeAmount(status.last_payout_amount)}${status.last_payout_status ? ` · ${status.last_payout_status}` : ''}` : 'No payout recorded'}</p>
              </div>
            </div>
            <div className="mt-4">
              <p className="mb-2 text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">Recent payments recorded by DieselBridge</p>
              {status.recent_payments.length ? (
                <div className="divide-y divide-zinc-800 border-y border-zinc-800">
                  {status.recent_payments.map((payment) => (
                    <div key={`${payment.invoice_number}-${payment.payment_intent_id || payment.created_at}`} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5 text-sm">
                      <div>
                        <span className="font-medium text-zinc-200">{payment.invoice_number}</span>
                        <span className="ml-2 text-xs capitalize text-zinc-500">{payment.status.replace(/_/g, ' ')}</span>
                      </div>
                      <div className="text-right">
                        <span className="font-medium text-zinc-100">{formatStripeAmount(payment.amount)}</span>
                        <span className="ml-2 text-xs text-zinc-500">{new Date(payment.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-zinc-500">No Stripe payments have been recorded for this shop yet.</p>
              )}
            </div>
          </div>
        )}

        <div className="pt-4 border-t border-zinc-800/50">
          {!status?.is_connected && status?.configured ? (
            <button
              onClick={() => connectMutation.mutate()}
              disabled={connectMutation.isPending || isRedirecting}
              className={industrialStyles.btnPrimary}
            >
              {connectMutation.isPending || isRedirecting ? (
                <span className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-zinc-600 border-t-white rounded-full animate-spin" />
                  Redirecting...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <CreditCard className="w-4 h-4" />
                  Set Up Stripe Payments
                </span>
              )}
            </button>
          ) : !status?.is_connected ? (
            <p className="text-sm text-amber-300">The Stripe platform keys must be configured before this shop can begin setup.</p>
          ) : !status.configured && !status.onboarding_complete ? (
            <div className="space-y-3">
              <p className="text-sm text-amber-300">This account is connected, but DieselBridge platform configuration must be restored before onboarding can continue.</p>
              <button onClick={() => setDisconnectKind('current')} disabled={disconnectMutation.isPending} className={industrialStyles.btnSecondary}>
                {disconnectMutation.isPending ? 'Resetting...' : 'Reset Stripe Connection'}
              </button>
            </div>
          ) : status.verification_status === 'under_review' ? (
            <div className="space-y-3">
              <p className="text-sm text-sky-300">Verification is in progress. This page refreshes automatically while Stripe reviews your account.</p>
              <button onClick={() => setDisconnectKind('current')} disabled={disconnectMutation.isPending} className={industrialStyles.btnSecondary}>
                {disconnectMutation.isPending ? 'Resetting...' : 'Reset Stripe Connection'}
              </button>
            </div>
          ) : !status.onboarding_complete && status.connection_type !== 'express_legacy' ? (
            <div className="flex flex-wrap items-center gap-3">
              <button onClick={() => connectMutation.mutate()} disabled={connectMutation.isPending || isRedirecting} className={industrialStyles.btnPrimary}>
                {connectMutation.isPending || isRedirecting ? 'Redirecting...' : status.verification_status === 'needs_information' || status.verification_status === 'restricted' ? 'Update Stripe Details' : 'Continue Stripe Setup'}
              </button>
              <button onClick={() => setDisconnectKind('current')} disabled={disconnectMutation.isPending} className={industrialStyles.btnSecondary}>
                {disconnectMutation.isPending ? 'Resetting...' : 'Reset Stripe Connection'}
              </button>
            </div>
          ) : status.connection_type !== 'express_legacy' ? (
            <div className="flex flex-wrap items-center gap-3">
              {status.account_dashboard_url && (
                <a href={status.account_dashboard_url} target="_blank" rel="noreferrer" className={`${industrialStyles.btnSecondary} inline-flex items-center justify-center`}>
                  <span className="inline-flex items-center gap-2"><ExternalLink className="w-4 h-4" />View Connected Account Payments</span>
                </a>
              )}
              <button onClick={() => setDisconnectKind('current')} disabled={disconnectMutation.isPending} className={industrialStyles.btnSecondary}>
                {disconnectMutation.isPending ? 'Disconnecting...' : 'Disconnect Stripe'}
              </button>
            </div>
          ) : (
            <button onClick={() => setDisconnectKind('legacy')} disabled={disconnectMutation.isPending} className={industrialStyles.btnSecondary}>
              {disconnectMutation.isPending ? 'Disconnecting...' : 'Disconnect Legacy Connection'}
            </button>
          )}
        </div>
      </PaymentIntegrationPanel>
      {disconnectKind && (
        <DisconnectStripeDialog
          legacy={disconnectKind === 'legacy'}
          pending={disconnectMutation.isPending}
          onCancel={() => setDisconnectKind(null)}
          onConfirm={() => disconnectMutation.mutate()}
        />
      )}
      <ZelleSection
        open={openPaymentPanel === 'zelle'}
        onOpenChange={(nextOpen) => setOpenPaymentPanel(nextOpen ? 'zelle' : null)}
      />
      <QuickBooksIntegrationCard
        open={openPaymentPanel === 'quickbooks'}
        onOpenChange={(nextOpen) => setOpenPaymentPanel(nextOpen ? 'quickbooks' : null)}
      />
    </div>
  )
}

function PlatformIntegrationsSection() {
  const { data: quickBooks, isLoading, isError } = useQuery<QuickBooksPlatformStatus>({
    queryKey: ['quickbooks-platform-status'],
    queryFn: async () => (await api.get('/admin/platform/quickbooks-status')).data,
  })
  const { data: stripe, isLoading: isStripeLoading, isError: isStripeError } = useQuery<StripePlatformStatus>({
    queryKey: ['stripe-platform-status'],
    queryFn: async () => (await api.get('/admin/platform/stripe-status')).data,
  })
  const { data: googleReviews, isLoading: isGoogleReviewsLoading, isError: isGoogleReviewsError } = useQuery<GoogleReviewsPlatformStatus>({
    queryKey: ['google-reviews-platform-status'],
    queryFn: async () => (await api.get('/admin/platform/google-reviews-status')).data,
  })

  return (
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <div className="rounded-xl border border-gold-500/20 bg-gold-500/5 px-4 py-3 text-sm text-gold-100/80">
        These integrations are configured once by DieselBridge. Garages do not receive provider credentials; they authorize only their own connected accounts.
      </div>

      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Landmark className="w-4 h-4 text-gold-400" />
          <span>QuickBooks Online</span>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <div className="w-6 h-6 rounded-full border-2 border-zinc-600 border-t-gold-400 animate-spin" />
          </div>
        ) : isError || !quickBooks ? (
          <div className="rounded-xl border border-red-700/40 bg-red-950/20 p-4 text-sm text-red-200">
            QuickBooks platform readiness could not be loaded. Refresh and try again.
          </div>
        ) : (
          <>
            <div className="flex items-start gap-4 mb-6">
              <div className="p-3 bg-zinc-800/60 border border-zinc-700/50 rounded-xl">
                {quickBooks.platform_ready ? (
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                ) : (
                  <StatusLED status="warning" />
                )}
              </div>
              <div>
                <h4 className="font-semibold text-zinc-100">
                  {quickBooks.platform_ready ? 'TENANT CONNECTIONS ENABLED' : 'PLATFORM SETUP REQUIRED'}
                </h4>
                <p className="mt-1 text-sm text-zinc-400">
                  {quickBooks.platform_ready
                    ? 'Garage owners and admins with Payments access can now connect their own QuickBooks company.'
                    : 'Complete this one-time DieselBridge configuration before any garage can connect.'}
                </p>
              </div>
            </div>

            {quickBooks.platform_ready ? (
              <div className="rounded-xl border border-emerald-700/35 bg-emerald-950/15 p-4 text-sm text-emerald-100/85">
                Tenant flow: from Payments &amp; Accounting, the garage selects <span className="font-medium text-emerald-200">Connect My QuickBooks</span>, signs into Intuit, chooses its company, and grants consent. No DieselBridge credentials are shown to tenants.
              </div>
            ) : (
              <div className="rounded-xl border border-amber-700/40 bg-amber-950/20 p-4">
                <h5 className="text-sm font-semibold text-amber-200">DieselBridge administrator checklist</h5>
                <ol className="mt-3 space-y-2 text-sm leading-6 text-zinc-300">
                  <li><span className="mr-2 font-semibold text-gold-400">1.</span>Create a DieselBridge Intuit Developer app with QuickBooks Online Accounting and Payments enabled.</li>
                  <li className="break-words"><span className="mr-2 font-semibold text-gold-400">2.</span>Register this production callback URL: <code className="text-amber-200">{quickBooks.callback_url}</code></li>
                  <li className="break-words"><span className="mr-2 font-semibold text-gold-400">3.</span>Register this Intuit webhook URL: <code className="text-amber-200">{quickBooks.webhook_url}</code></li>
                  <li><span className="mr-2 font-semibold text-gold-400">4.</span>Store the Intuit client ID, client secret, webhook verifier token, and a dedicated token-encryption key in managed backend secrets, then redeploy.</li>
                </ol>
                <a
                  href="https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0"
                  target="_blank"
                  rel="noreferrer"
                  className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-gold-400 hover:text-gold-300"
                >
                  Open Intuit OAuth setup guide <ExternalLink className="w-4 h-4" />
                </a>
              </div>
            )}
          </>
        )}
      </IndustrialCard>

      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Globe className="w-4 h-4 text-gold-400" />
          <span>Google Reviews</span>
        </div>
        {isGoogleReviewsLoading ? (
          <div className="flex justify-center py-8"><div className="w-6 h-6 rounded-full border-2 border-zinc-600 border-t-gold-400 animate-spin" /></div>
        ) : isGoogleReviewsError || !googleReviews ? (
          <div className="rounded-xl border border-red-700/40 bg-red-950/20 p-4 text-sm text-red-200">Google Reviews platform readiness could not be loaded. Refresh and try again.</div>
        ) : googleReviews.platform_ready ? (
          <div className="rounded-xl border border-emerald-700/35 bg-emerald-950/15 p-4 text-sm text-emerald-100/85">
            <div className="flex items-center gap-2 font-medium text-emerald-200"><ShieldCheck className="w-4 h-4" /> Tenant connections enabled</div>
            <p className="mt-2">Each shop can now open My Shop → Google Reviews → Google connection & settings, sign in with its own Google manager account, and select its own location.</p>
          </div>
        ) : (
          <div className="rounded-xl border border-amber-700/40 bg-amber-950/20 p-4">
            <h5 className="text-sm font-semibold text-amber-200">DieselBridge administrator checklist</h5>
            <ol className="mt-3 space-y-2 text-sm leading-6 text-zinc-300">
              <li><span className="mr-2 font-semibold text-gold-400">1.</span>Request Google Business Profile API access for the DieselBridge Google Cloud project.</li>
              <li className="break-words"><span className="mr-2 font-semibold text-gold-400">2.</span>Register callback URL: <code className="text-amber-200">{googleReviews.callback_url}</code></li>
              <li className="break-words"><span className="mr-2 font-semibold text-gold-400">3.</span>Create a Pub/Sub push subscription to: <code className="text-amber-200">{googleReviews.pubsub_url}</code></li>
              <li><span className="mr-2 font-semibold text-gold-400">4.</span>Store Google client ID, client secret, Pub/Sub audience, and a dedicated Fernet encryption key in managed backend secrets; then redeploy.</li>
            </ol>
            {!googleReviews.pubsub_auth_ready && <p className="mt-3 text-sm text-amber-200">Pub/Sub OIDC audience has not been configured yet.</p>}
            <a href="https://developers.google.com/my-business/content/overview" target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-gold-400 hover:text-gold-300">Open Google Business Profile API guide <ExternalLink className="w-4 h-4" /></a>
          </div>
        )}
      </IndustrialCard>

      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <CreditCard className="w-4 h-4 text-gold-400" />
          <span>Stripe Connect</span>
        </div>

        {isStripeLoading ? (
          <div className="flex justify-center py-8"><div className="w-6 h-6 rounded-full border-2 border-zinc-600 border-t-gold-400 animate-spin" /></div>
        ) : isStripeError || !stripe ? (
          <div className="rounded-xl border border-red-700/40 bg-red-950/20 p-4 text-sm text-red-200">Stripe platform readiness could not be loaded. Refresh and try again.</div>
        ) : stripe.platform_ready ? (
          <div className="rounded-xl border border-emerald-700/35 bg-emerald-950/15 p-4 text-sm text-emerald-100/85">
            <div className="flex items-center gap-2 font-medium text-emerald-200"><ShieldCheck className="w-4 h-4" /> Tenant connections enabled</div>
            <p className="mt-2">Garages can create or resume their connected merchant account from Payments &amp; Accounting. Stripe hosts onboarding and provides each garage with its own full Stripe Dashboard.</p>
          </div>
        ) : (
          <div className="rounded-xl border border-amber-700/40 bg-amber-950/20 p-4">
            <h5 className="text-sm font-semibold text-amber-200">DieselBridge administrator checklist</h5>
            <ol className="mt-3 space-y-2 text-sm leading-6 text-zinc-300">
              <li><span className="mr-2 font-semibold text-gold-400">1.</span>Activate Connect and configure your platform branding and onboarding options in Stripe.</li>
              <li><span className="mr-2 font-semibold text-gold-400">2.</span>Store the Stripe secret and publishable keys in managed backend secrets, then redeploy.</li>
              <li><span className="mr-2 font-semibold text-gold-400">3.</span>Create Connect and platform webhook destinations and store their signing secrets.</li>
            </ol>
            <a href="https://docs.stripe.com/connect/hosted-onboarding" target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-gold-400 hover:text-gold-300">
              Open Stripe-hosted onboarding guide <ExternalLink className="w-4 h-4" />
            </a>
          </div>
        )}
      </IndustrialCard>
    </div>
  )
}

function QuickBooksIntegrationCard({ open, onOpenChange }: { open: boolean; onOpenChange: (nextOpen: boolean) => void }) {
  const queryClient = useQueryClient()
  const [isRedirecting, setIsRedirecting] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const { data: status, isLoading } = useQuery<QuickBooksConnectionStatus>({
    queryKey: ['quickbooks-status'],
    queryFn: async () => (await api.get('/quickbooks/status')).data,
  })

  useEffect(() => {
    const result = searchParams.get('quickbooks')
    if (!result) return
    const messages: Record<string, string> = {
      connected: 'QuickBooks connected successfully.',
      'not-connected': 'QuickBooks connection was cancelled.',
      'realm-in-use': 'That QuickBooks company is already connected to another shop.',
      error: 'QuickBooks could not complete the connection. Please try again.',
    }
    const message = messages[result]
    if (message) {
      result === 'connected' ? toast.success(message) : toast.error(message)
      queryClient.invalidateQueries({ queryKey: ['quickbooks-status'] })
      setSearchParams({}, { replace: true })
    }
  }, [queryClient, searchParams, setSearchParams])

  const connectMutation = useMutation({
    mutationFn: async () => (await api.post('/quickbooks/connect')).data as { url: string },
    onSuccess: (data) => {
      setIsRedirecting(true)
      window.location.href = data.url
    },
    onError: (error: unknown) => {
      toast.error(apiErrorDetail(error, 'Failed to start QuickBooks connection'))
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: async () => (await api.post('/quickbooks/disconnect')).data,
    onSuccess: () => {
      toast.success('QuickBooks disconnected.')
      queryClient.invalidateQueries({ queryKey: ['quickbooks-status'] })
    },
    onError: (error: unknown) => {
      toast.error(apiErrorDetail(error, 'Failed to disconnect QuickBooks'))
    },
  })

  const connectionNeedsAttention = Boolean(
    status?.is_connected
    && (status.token_health === 'reconnect_required' || status.last_token_refresh_error),
  )

  const statusConfig = !status?.configured
    ? { led: 'warning' as const, title: 'NOT AVAILABLE YET', desc: 'DieselBridge is still enabling QuickBooks for its garage network.' }
    : status.is_connected
      ? connectionNeedsAttention
        ? { led: 'warning' as const, title: 'ACTION REQUIRED', desc: 'Reconnect QuickBooks to continue using accounting and payments.' }
        : { led: 'active' as const, title: 'ACTIVE', desc: 'Accounting and payments are authorized.' }
      : { led: 'inactive' as const, title: 'NOT CONNECTED', desc: 'Connect QuickBooks to use accounting and payments.' }

  return (
    <PaymentIntegrationPanel
      icon={<Building2 className="h-5 w-5" />}
      title="QuickBooks Online"
      summary={isLoading ? 'Checking connection status...' : statusConfig.desc}
      status={{
        label: isLoading ? 'CHECKING STATUS' : statusConfig.title,
        variant: isLoading ? 'default' : statusConfig.led === 'active' ? 'success' : statusConfig.led === 'warning' ? 'warning' : 'default',
        led: isLoading ? 'inactive' : statusConfig.led,
      }}
      open={open}
      onOpenChange={onOpenChange}
    >

      {isLoading ? (
        <div className="flex justify-center py-8">
          <div className="w-6 h-6 border-2 border-zinc-600 border-t-[var(--accent-400)] rounded-full animate-spin" />
        </div>
      ) : (
        <>
          {!status?.configured && (
            <p className="text-sm text-amber-300">QuickBooks is not available for this account yet.</p>
          )}

          {status?.is_connected && connectionNeedsAttention && (
            <div className="mb-5 rounded-xl border border-amber-700/40 bg-amber-950/20 p-4 text-sm text-amber-100">
              QuickBooks needs to be reconnected to continue.
            </div>
          )}

          {status?.configured && (
            <div className="flex flex-wrap items-center gap-3">
              {status.is_connected ? (
                <>
                  <IndustrialBadge variant="success">
                    <StatusLED status="active" />
                    Accounting + Payments Authorized
                  </IndustrialBadge>
                  {connectionNeedsAttention && (
                    <button
                      onClick={() => connectMutation.mutate()}
                      disabled={connectMutation.isPending || isRedirecting}
                      className={industrialStyles.btnPrimary}
                    >
                      {connectMutation.isPending || isRedirecting ? 'Redirecting...' : 'Reconnect QuickBooks'}
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (window.confirm('Disconnect QuickBooks? Accounting and payments will stop until you reconnect.')) {
                        disconnectMutation.mutate()
                      }
                    }}
                    disabled={disconnectMutation.isPending}
                    className={industrialStyles.btnSecondary}
                  >
                    {disconnectMutation.isPending ? 'Disconnecting...' : 'Disconnect QuickBooks'}
                  </button>
                </>
              ) : (
                <button
                  onClick={() => connectMutation.mutate()}
                  disabled={connectMutation.isPending || isRedirecting}
                  className={industrialStyles.btnPrimary}
                >
                  <span className="flex items-center gap-2">
                    <Building2 className="w-4 h-4" />
                    {connectMutation.isPending || isRedirecting ? 'Redirecting...' : 'Connect My QuickBooks'}
                  </span>
                </button>
              )}
            </div>
          )}
        </>
      )}
    </PaymentIntegrationPanel>
  )
}

function ZelleSection({ open, onOpenChange }: { open: boolean; onOpenChange: (nextOpen: boolean) => void }) {
  const queryClient = useQueryClient()
  const [zelleQrPreview, setZelleQrPreview] = useState<string | null>(null)
  const [_isUploadingQr, setIsUploadingQr] = useState(false)
  const [zelleEmail, setZelleEmail] = useState('')
  const [zellePhone, setZellePhone] = useState('')
  const [contactEditing, setContactEditing] = useState(false)
  const [isUnlocked, setIsUnlocked] = useState(false)
  const [unlockPassword, setUnlockPassword] = useState('')
  const [unlockError, setUnlockError] = useState<string | null>(null)

  const { data: garageProfile } = useQuery<GarageProfile>({
    queryKey: ['garage-profile'],
    queryFn: async () => {
      const response = await api.get('/admin/garage-profile')
      return response.data
    },
  })

  const { data: zelleSettings } = useQuery<ZelleSettings>({
    queryKey: ['zelle-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/zelle-settings')
      return response.data
    },
  })

  // Sync form fields when data loads (only when not actively editing)
  // Fall back to garage profile email/phone when Zelle-specific values aren't set
  const prevZelleSettings = useRef<ZelleSettings | undefined>(undefined)
  useEffect(() => {
    if (zelleSettings && zelleSettings !== prevZelleSettings.current && !contactEditing) {
      setZelleEmail(zelleSettings.zelle_email || garageProfile?.email || '')
      setZellePhone(zelleSettings.zelle_phone || garageProfile?.phone || '')
      prevZelleSettings.current = zelleSettings
    }
  }, [zelleSettings, garageProfile, contactEditing])

  const hasZellePaymentDetails = Boolean(zelleSettings?.zelle_email || zelleSettings?.zelle_phone)
  const zelleStatus = hasZellePaymentDetails
    ? { label: 'PAYMENT DETAILS READY', variant: 'success' as const, led: 'active' as const }
    : { label: 'PAYMENT DETAILS NEEDED', variant: 'warning' as const, led: 'warning' as const }

  const unlockMutation = useMutation({
    mutationFn: async (password: string) => {
      const response = await api.post('/auth/verify-password', { password })
      return response.data as { valid: boolean }
    },
    onSuccess: (data) => {
      if (data.valid) {
        setIsUnlocked(true)
        setContactEditing(true)
        setUnlockPassword('')
        setUnlockError(null)
      } else {
        setUnlockError('Incorrect password.')
      }
    },
    onError: () => {
      setUnlockError('Incorrect password.')
    },
  })

  const saveContactMutation = useMutation({
    mutationFn: async () => {
      const response = await api.put('/admin/zelle-settings', {
        zelle_email: zelleEmail.trim() || null,
        zelle_phone: zellePhone.trim() || null,
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Zelle contact details saved')
      queryClient.invalidateQueries({ queryKey: ['zelle-settings'] })
      setContactEditing(false)
      setIsUnlocked(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save Zelle settings')
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
    <div className="animate-[fadeIn_0.4s_ease-out]">
      <PaymentIntegrationPanel
        icon={<QrCode className="h-5 w-5" />}
        title="Zelle Payments"
        summary={hasZellePaymentDetails ? 'Customers can use your configured Zelle contact details for manual transfers.' : 'Add an email or phone number before customers can send Zelle transfers.'}
        status={zelleStatus}
        open={open}
        onOpenChange={onOpenChange}
      >

        {!isUnlocked ? (
          /* Lock gate */
          <div className="space-y-4">
            <div className="flex items-start gap-3 bg-amber-950/30 border border-amber-700/40 rounded-xl p-4">
              <Shield className="w-5 h-5 text-amber-400 mt-0.5 shrink-0" />
              <p className="text-sm text-amber-300">
                Zelle payment details are protected. Confirm your password to make changes.
              </p>
            </div>
            {/* Current values read-only preview */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={industrialStyles.label}>Zelle Email</label>
                <div className={`${industrialStyles.input} opacity-50 cursor-not-allowed select-none`}>
                  {zelleEmail || <span className="text-zinc-600">Not set</span>}
                </div>
              </div>
              <div>
                <label className={industrialStyles.label}>Zelle Phone</label>
                <div className={`${industrialStyles.input} opacity-50 cursor-not-allowed select-none`}>
                  {zellePhone || <span className="text-zinc-600">Not set</span>}
                </div>
              </div>
            </div>
            <div className="max-w-sm space-y-2">
              <label className={industrialStyles.label}>Your Password</label>
              <input
                type="password"
                value={unlockPassword}
                onChange={(e) => { setUnlockPassword(e.target.value); setUnlockError(null) }}
                onKeyDown={(e) => e.key === 'Enter' && unlockPassword && unlockMutation.mutate(unlockPassword)}
                placeholder="Enter your password to unlock"
                className={unlockError ? `${industrialStyles.input} border-red-500 focus:border-red-400` : industrialStyles.input}
              />
              {unlockError && <p className="text-xs text-red-400">{unlockError}</p>}
              <button
                onClick={() => unlockMutation.mutate(unlockPassword)}
                disabled={!unlockPassword || unlockMutation.isPending}
                className={industrialStyles.btnPrimary}
              >
                <span className="flex items-center gap-2">
                  <Lock className="w-4 h-4" />
                  {unlockMutation.isPending ? 'Verifying...' : 'Unlock to Edit'}
                </span>
              </button>
            </div>
          </div>
        ) : (
          /* Unlocked — editable */
          <div className="space-y-6">
            <div className="flex items-center justify-between bg-green-950/30 border border-green-700/40 rounded-xl px-4 py-2">
              <span className="text-sm text-green-400 flex items-center gap-2">
                <Shield className="w-4 h-4" /> Editing unlocked
              </span>
              <button
                onClick={() => { setIsUnlocked(false); setContactEditing(false) }}
                className="text-xs text-zinc-400 hover:text-zinc-200 underline"
              >
                Lock
              </button>
            </div>

            {/* Contact fields */}
            {(() => {
              const emailInvalid = zelleEmail.trim() !== '' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(zelleEmail.trim())
              const phoneInvalid = zellePhone.trim() !== '' && !isValidUSPhone(zellePhone)
              const canSave = !emailInvalid && !phoneInvalid
              return (
                <div className="space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className={industrialStyles.label}>Zelle Email</label>
                      <input
                        type="email"
                        value={zelleEmail}
                        onChange={(e) => { setZelleEmail(e.target.value); setContactEditing(true) }}
                        placeholder="zelle@yourshop.com"
                        className={emailInvalid ? `${industrialStyles.input} border-red-500 focus:border-red-400` : industrialStyles.input}
                      />
                      {emailInvalid && <p className="text-xs text-red-400 mt-1">Enter a valid email address</p>}
                    </div>
                    <div>
                      <label className={industrialStyles.label}>Zelle Phone</label>
                      <input
                        type="tel"
                        value={zellePhone}
                        onChange={(e) => { setZellePhone(formatUSPhone(e.target.value)); setContactEditing(true) }}
                        placeholder="(555) 000-0000"
                        className={phoneInvalid ? `${industrialStyles.input} border-red-500 focus:border-red-400` : industrialStyles.input}
                      />
                      {phoneInvalid && <p className="text-xs text-red-400 mt-1">Enter a valid US phone number</p>}
                    </div>
                  </div>
                  {contactEditing && (
                    <div className="flex gap-3">
                      <button
                        onClick={() => saveContactMutation.mutate()}
                        disabled={saveContactMutation.isPending || !canSave}
                        className={industrialStyles.btnPrimary}
                      >
                        <span className="flex items-center gap-2">
                          <Save className="w-4 h-4" />
                          {saveContactMutation.isPending ? 'Saving...' : 'Save'}
                        </span>
                      </button>
                      <button
                        onClick={() => {
                          setZelleEmail(zelleSettings?.zelle_email || garageProfile?.email || '')
                          setZellePhone(zelleSettings?.zelle_phone || garageProfile?.phone || '')
                          setContactEditing(false)
                        }}
                        className={industrialStyles.btnSecondary}
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
              )
            })()}

            {/* QR code */}
            <div className="flex flex-col sm:flex-row items-start gap-6">
              <div className="w-32 h-32 bg-zinc-800/60 border border-zinc-600/50 rounded-2xl flex items-center justify-center overflow-hidden flex-shrink-0">
                {zelleQrPreview || zelleSettings?.zelle_qr_image ? (
                  <img src={zelleQrPreview || zelleSettings?.zelle_qr_image || ''} alt="Zelle QR" className="w-full h-full object-contain" />
                ) : (
                  <QrCode className="w-12 h-12 text-zinc-600" />
                )}
              </div>
              <div className="flex-1 space-y-4">
                <div>
                  <label className={industrialStyles.label}>Upload QR Code</label>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleQrFileChange}
                    className="block w-full text-sm text-zinc-400
                      file:mr-4 file:py-2.5 file:px-4 file:rounded-lg
                      file:border file:border-zinc-600/50 file:bg-zinc-800/80
                      file:text-xs file:font-medium file:text-zinc-300
                      hover:file:bg-zinc-700 file:transition-colors file:cursor-pointer"
                  />
                </div>
                <div className="flex gap-3">
                  {zelleQrPreview && (
                    <button
                      onClick={() => uploadQrMutation.mutate(zelleQrPreview)}
                      disabled={uploadQrMutation.isPending}
                      className={industrialStyles.btnPrimary}
                    >
                      <span className="flex items-center gap-2">
                        <Save className="w-4 h-4" />
                        Save
                      </span>
                    </button>
                  )}
                  {(zelleSettings?.zelle_qr_image || zelleQrPreview) && (
                    <button
                      onClick={() => { uploadQrMutation.mutate(null); setZelleQrPreview(null) }}
                      disabled={uploadQrMutation.isPending}
                      className={industrialStyles.btnDanger}
                    >
                      <span className="flex items-center gap-2">
                        <Trash2 className="w-4 h-4" />
                        Remove
                      </span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </PaymentIntegrationPanel>
    </div>
  )
}

function NotificationsSection() {
  const queryClient = useQueryClient()
  const { user, setUser } = useAuthStore()
  const [remindersEnabled, setRemindersEnabled] = useState(true)
  const [reminderFrequency, setReminderFrequency] = useState(3)
  const [maxReminders, setMaxReminders] = useState(3)
  const [isEditing, setIsEditing] = useState(false)

  // Shop-wide Messaging feature toggle.
  const { data: tenantSettings } = useQuery<{ messaging_enabled: boolean }>({
    queryKey: ['tenant-settings'],
    queryFn: async () => (await api.get('/admin/tenant-settings')).data,
  })
  const messagingEnabled = tenantSettings?.messaging_enabled ?? true
  const messagingMutation = useMutation({
    mutationFn: async (next: boolean) =>
      (await api.put('/admin/tenant-settings', { messaging_enabled: next })).data,
    onSuccess: (data: { messaging_enabled: boolean }) => {
      toast.success(data.messaging_enabled ? 'Messaging enabled' : 'Messaging disabled')
      queryClient.invalidateQueries({ queryKey: ['tenant-settings'] })
      // Reflect immediately so the Messages nav link + route hide/show without a reload.
      if (user) setUser({ ...user, messaging_enabled: data.messaging_enabled })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update messaging')
    },
  })

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
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <MessageSquare className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Customer Messaging</span>
        </div>

        <div className="flex items-center justify-between p-4 bg-zinc-800/40 border border-zinc-700/50 rounded-xl">
          <div className="pr-4">
            <h4 className="font-semibold text-zinc-100 text-sm">Enable Messaging</h4>
            <p className="text-xs text-zinc-500 mt-1">
              Shows the Messages inbox and customer conversations. Turn off to hide the feature shop-wide while it's still being built.
            </p>
          </div>
          <button
            onClick={() => messagingMutation.mutate(!messagingEnabled)}
            disabled={messagingMutation.isPending}
            role="switch"
            aria-checked={messagingEnabled}
            aria-label="Enable customer messaging"
            className={`db-settings-switch relative w-14 h-8 rounded-full border transition-colors flex-shrink-0 disabled:opacity-60 ${
              messagingEnabled
                ? 'bg-[var(--accent-600)] border-[var(--accent-400)]/50'
                : 'bg-zinc-800 border-zinc-600/50'
            }`}
          >
            <span aria-hidden="true" className={`absolute top-1 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
              messagingEnabled ? 'left-7' : 'left-1'
            }`} />
          </button>
        </div>
      </IndustrialCard>

      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Bell className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Invoice Reminders</span>
        </div>

        <div className="space-y-6">
          {/* Toggle */}
          <div className="flex items-center justify-between p-4 bg-zinc-800/40 border border-zinc-700/50 rounded-xl">
            <div>
              <h4 className="font-semibold text-zinc-100 text-sm">Enable Reminders</h4>
              <p className="text-xs text-zinc-500 mt-1">Send automatic SMS reminders for overdue invoices</p>
            </div>
            <button
              onClick={() => { setRemindersEnabled(!remindersEnabled); setIsEditing(true) }}
              role="switch"
              aria-checked={remindersEnabled}
              aria-label="Enable invoice reminders"
              className={`db-settings-switch relative w-14 h-8 rounded-full border transition-colors ${
                remindersEnabled 
                  ? 'bg-[var(--accent-600)] border-[var(--accent-400)]/50' 
                  : 'bg-zinc-800 border-zinc-600/50'
              }`}
            >
              <span aria-hidden="true" className={`absolute top-1 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
                remindersEnabled ? 'left-7' : 'left-1'
              }`} />
            </button>
          </div>

          {remindersEnabled && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div>
                <label className={industrialStyles.label}>Reminder Frequency (days)</label>
                <input
                  type="number"
                  min="1"
                  max="30"
                  value={reminderFrequency}
                  onChange={(e) => { setReminderFrequency(parseInt(e.target.value) || 3); setIsEditing(true) }}
                  className={industrialStyles.input}
                />
              </div>
              <div>
                <label className={industrialStyles.label}>Max Reminders</label>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={maxReminders}
                  onChange={(e) => { setMaxReminders(parseInt(e.target.value) || 3); setIsEditing(true) }}
                  className={industrialStyles.input}
                />
              </div>
            </div>
          )}

          {isEditing && (
            <div className="flex gap-4 pt-4 border-t border-zinc-800/50">
              <button onClick={cancelEdit} className={industrialStyles.btnSecondary}>
                Cancel
              </button>
              <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className={industrialStyles.btnPrimary}
              >
                {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          )}
        </div>
      </IndustrialCard>
    </div>
  )
}

function FeesSection() {
  const queryClient = useQueryClient()
  const [salesTaxRate, setSalesTaxRate] = useState('')
  const [shopSuppliesRate, setShopSuppliesRate] = useState('')
  const [serviceFeeRate, setServiceFeeRate] = useState('')
  const [laborRate, setLaborRate] = useState('')
  const [internalLaborRate, setInternalLaborRate] = useState('')
  const [isUnlocked, setIsUnlocked] = useState(false)
  const [password, setPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [isVerifying, setIsVerifying] = useState(false)

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
      setLaborRate(taxFeeSettings.labor_rate?.toString() || '100')
      setInternalLaborRate(taxFeeSettings.internal_labor_rate?.toString() || '0')
    }
  }, [taxFeeSettings])

  const hasChanges = taxFeeSettings && (
    salesTaxRate !== (taxFeeSettings.sales_tax_rate?.toString() || '') ||
    shopSuppliesRate !== (taxFeeSettings.shop_supplies_rate?.toString() || '') ||
    serviceFeeRate !== (taxFeeSettings.service_fee_rate?.toString() || '') ||
    laborRate !== (taxFeeSettings.labor_rate?.toString() || '100') ||
    internalLaborRate !== (taxFeeSettings.internal_labor_rate?.toString() || '0')
  )

  const handleUnlock = async () => {
    if (!password) {
      setPasswordError('Password is required')
      return
    }
    setIsVerifying(true)
    setPasswordError('')
    try {
      const response = await api.post('/auth/verify-password', { password })
      if (response.data.valid) {
        setIsUnlocked(true)
        setPassword('')
      } else {
        setPasswordError('Incorrect password')
      }
    } catch {
      setPasswordError('Failed to verify password')
    } finally {
      setIsVerifying(false)
    }
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const response = await api.put('/admin/tax-fee-settings', {
        sales_tax_rate: parseFloat(salesTaxRate) || 0,
        shop_supplies_rate: parseFloat(shopSuppliesRate) || 0,
        service_fee_rate: parseFloat(serviceFeeRate) || 0,
        labor_rate: laborRate === '' ? 100 : parseFloat(laborRate),
        internal_labor_rate: internalLaborRate === '' ? 0 : parseFloat(internalLaborRate),
        // Preserve the fleet company name (managed in the Fleet section) so
        // saving tax/fees doesn't clear it.
        fleet_company_name: taxFeeSettings?.fleet_company_name ?? null,
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Tax & fee settings saved')
      queryClient.invalidateQueries({ queryKey: ['tax-fee-settings'] })
      setIsUnlocked(false)
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
      setLaborRate(taxFeeSettings.labor_rate?.toString() || '100')
      setInternalLaborRate(taxFeeSettings.internal_labor_rate?.toString() || '0')
    }
    setIsUnlocked(false)
  }

  const handleRateChange = (setter: (val: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    if (value === '' || /^\d*\.?\d*$/.test(value)) {
      setter(value)
    }
  }

  return (
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Percent className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Tax & Fees Configuration</span>
        </div>

        {!isUnlocked ? (
          <div className="space-y-6">
            {/* Read-only display of every field (values always visible, edit requires password) */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
              {[
                { label: 'Sales Tax', value: `${taxFeeSettings?.sales_tax_rate ?? 0}%` },
                { label: 'Supplies', value: `${taxFeeSettings?.shop_supplies_rate ?? 0}%` },
                { label: 'Card Processing Fee', value: `${taxFeeSettings?.service_fee_rate ?? 0}%` },
                { label: 'Labor Rate', value: `$${taxFeeSettings?.labor_rate ?? 100}/hr` },
                { label: 'Internal Fleet Labor', value: `$${taxFeeSettings?.internal_labor_rate ?? 0}/hr` },
              ].map((item, i) => (
                <div key={item.label} style={staggeredReveal(i)} className="animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 p-3 bg-zinc-800/40 border border-zinc-700/50 rounded-xl">
                  <label className={industrialStyles.label}>{item.label}</label>
                  <p className="text-lg text-zinc-100">{item.value}</p>
                </div>
              ))}
            </div>

            {/* Unlock form */}
            <div className="p-4 bg-zinc-800/40 border border-zinc-700/50 rounded-xl">
              <p className="text-xs text-zinc-500 mb-3">
                <Lock className="w-3 h-3 inline mr-2" />
                Enter password to edit
              </p>
              <div className="flex gap-3 items-start">
                <div className="flex-1 max-w-xs">
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => { setPassword(e.target.value); setPasswordError('') }}
                    onKeyDown={(e) => e.key === 'Enter' && handleUnlock()}
                    placeholder="Enter password"
                    className={`${industrialStyles.input} ${passwordError ? 'border-red-500' : ''}`}
                  />
                  {passwordError && <p className="text-xs text-red-400 mt-2">{passwordError}</p>}
                </div>
                <button
                  onClick={handleUnlock}
                  disabled={isVerifying}
                  className={industrialStyles.btnPrimary}
                >
                  {isVerifying ? (
                    <span className="flex items-center gap-2">
                      <div className="w-4 h-4 border-2 border-zinc-600 border-t-white animate-spin" />
                      Verifying
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Lock className="w-4 h-4" />
                      Unlock
                    </span>
                  )}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className={industrialStyles.label}>Sales Tax (%)</label>
                <div className="relative">
                  <input
                    type="text"
                    value={salesTaxRate}
                    onChange={handleRateChange(setSalesTaxRate)}
                    placeholder="0"
                    className={`${industrialStyles.input} pr-10`}
                  />
                  <Percent className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                </div>
              </div>
              <div>
                <label className={industrialStyles.label}>Supplies (%)</label>
                <div className="relative">
                  <input
                    type="text"
                    value={shopSuppliesRate}
                    onChange={handleRateChange(setShopSuppliesRate)}
                    placeholder="0"
                    className={`${industrialStyles.input} pr-10`}
                  />
                  <Percent className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                </div>
              </div>
              <div>
                <label className={industrialStyles.label}>Card Processing Fee (%)</label>
                <div className="relative">
                  <input
                    type="text"
                    value={serviceFeeRate}
                    onChange={handleRateChange(setServiceFeeRate)}
                    placeholder="0"
                    className={`${industrialStyles.input} pr-10`}
                  />
                  <Percent className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                </div>
              </div>
              <div>
                <label className={industrialStyles.label}>Labor Rate ($/hr)</label>
                <input
                  type="text"
                  value={laborRate}
                  onChange={handleRateChange(setLaborRate)}
                  placeholder="100"
                  className={industrialStyles.input}
                />
              </div>
              <div>
                <label className={industrialStyles.label}>Internal Fleet Labor Rate ($/hr)</label>
                <input
                  type="text"
                  value={internalLaborRate}
                  onChange={handleRateChange(setInternalLaborRate)}
                  placeholder="0"
                  className={industrialStyles.input}
                />
                <p className="mt-1 text-xs text-zinc-500">Labor cost rate for repairs on the garage's own fleet (no customer markup).</p>
              </div>
            </div>

            <div className="flex gap-4 pt-4 border-t border-zinc-800/50">
              <button onClick={cancelEdit} className={industrialStyles.btnSecondary}>
                Cancel
              </button>
              {hasChanges && (
                <button
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending}
                  className={industrialStyles.btnPrimary}
                >
                  {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
                </button>
              )}
            </div>
          </div>
        )}
      </IndustrialCard>
    </div>
  )
}

function FleetSection() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [fleetCompanyName, setFleetCompanyName] = useState('')
  const [defaultFleetAuthorityCustomerId, setDefaultFleetAuthorityCustomerId] = useState('')
  const [isUnlocked, setIsUnlocked] = useState(false)
  const [password, setPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [isVerifying, setIsVerifying] = useState(false)

  // The fleet company name is stored on the tax/fee settings endpoint today.
  const { data: taxFeeSettings } = useQuery<TaxFeeSettings>({
    queryKey: ['tax-fee-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/tax-fee-settings')
      return response.data
    },
  })

  // Fleet managers + truck count, derived live from the fleet board.
  const { data: fleetSettings } = useQuery<FleetSettings>({
    queryKey: ['fleet-settings'],
    queryFn: async () => {
      const response = await api.get('/fleet/settings')
      return response.data
    },
  })

  const { data: fleetCompanies = [] } = useQuery<Array<{ id: string; company_name: string; fleet_enabled: boolean; is_internal_fleet: boolean }>>({
    queryKey: ['fleet-companies'],
    queryFn: async () => (await api.get('/fleet/companies')).data,
  })

  // The truck list itself comes from the board (single source of truth).
  const { data: fleetBoard } = useQuery<{ trucks: FleetBoardTruck[] }>({
    queryKey: ['fleet-board-summary'],
    queryFn: async () => {
      const response = await api.get('/fleet/board')
      return response.data
    },
  })
  const trucks = fleetBoard?.trucks || []

  useEffect(() => {
    if (taxFeeSettings) {
      setFleetCompanyName(taxFeeSettings.fleet_company_name || '')
      setDefaultFleetAuthorityCustomerId(taxFeeSettings.default_fleet_authority_customer_id || '')
    }
  }, [taxFeeSettings])

  const hasChanges = !!taxFeeSettings &&
    (fleetCompanyName !== (taxFeeSettings.fleet_company_name || '') ||
      defaultFleetAuthorityCustomerId !== (taxFeeSettings.default_fleet_authority_customer_id || ''))

  const handleUnlock = async () => {
    if (!password) {
      setPasswordError('Password is required')
      return
    }
    setIsVerifying(true)
    setPasswordError('')
    try {
      const response = await api.post('/auth/verify-password', { password })
      if (response.data.valid) {
        setIsUnlocked(true)
        setPassword('')
      } else {
        setPasswordError('Incorrect password')
      }
    } catch {
      setPasswordError('Failed to verify password')
    } finally {
      setIsVerifying(false)
    }
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      // Send the current tax/fee values back unchanged (this endpoint updates
      // all of them); only fleet_company_name is edited here.
      const response = await api.put('/admin/tax-fee-settings', {
        sales_tax_rate: taxFeeSettings?.sales_tax_rate ?? 0,
        shop_supplies_rate: taxFeeSettings?.shop_supplies_rate ?? 0,
        service_fee_rate: taxFeeSettings?.service_fee_rate ?? 0,
        labor_rate: taxFeeSettings?.labor_rate ?? 100,
        internal_labor_rate: taxFeeSettings?.internal_labor_rate ?? 0,
        fleet_company_name: fleetCompanyName.trim() || null,
        default_fleet_authority_customer_id: defaultFleetAuthorityCustomerId || null,
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Fleet settings saved')
      queryClient.invalidateQueries({ queryKey: ['tax-fee-settings'] })
      queryClient.invalidateQueries({ queryKey: ['fleet-settings'] })
      setIsUnlocked(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save settings')
    },
  })

  const cancelEdit = () => {
    if (taxFeeSettings) {
      setFleetCompanyName(taxFeeSettings.fleet_company_name || '')
      setDefaultFleetAuthorityCustomerId(taxFeeSettings.default_fleet_authority_customer_id || '')
    }
    setIsUnlocked(false)
  }

  return (
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <IndustrialCard className="db-settings-fleet-config p-4 sm:p-5">
        <div className={industrialStyles.sectionHeader}>
          <Truck className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Fleet Configuration</span>
        </div>

        {!isUnlocked ? (
          <div className="space-y-4">
            <dl className="grid gap-3 sm:grid-cols-2">
              <div className="db-settings-fleet-config__summary">
                <dt className={industrialStyles.label}>Fleet Company</dt>
                <dd className="text-base font-medium text-zinc-100">{taxFeeSettings?.fleet_company_name || 'Not set'}</dd>
              </div>
              <div className="db-settings-fleet-config__summary">
                <dt className={industrialStyles.label}>Default Operating Authority</dt>
                <dd className="text-base font-medium text-zinc-100">{taxFeeSettings?.default_fleet_authority_company_name || 'Not set'}</dd>
                <p className="mt-1 text-xs text-zinc-500">Used only when a truck has no operating authority assigned yet.</p>
              </div>
            </dl>

            <div className="db-settings-fleet-config__unlock">
              <p className="flex items-center gap-2 text-xs text-zinc-500">
                <Lock className="w-3 h-3 shrink-0" />
                Enter password to edit
              </p>
              <div className="flex gap-3 items-start">
                <div className="flex-1 max-w-xs">
                  <label htmlFor="fleet-configuration-password" className="sr-only">Password</label>
                  <input
                    id="fleet-configuration-password"
                    type="password"
                    value={password}
                    onChange={(e) => { setPassword(e.target.value); setPasswordError('') }}
                    onKeyDown={(e) => e.key === 'Enter' && handleUnlock()}
                    placeholder="Enter password"
                    className={`${industrialStyles.input} ${passwordError ? 'border-red-500' : ''}`}
                  />
                  {passwordError && <p className="text-xs text-red-400 mt-2">{passwordError}</p>}
                </div>
                <button
                  onClick={handleUnlock}
                  disabled={isVerifying}
                  className={industrialStyles.btnPrimary}
                >
                  {isVerifying ? (
                    <span className="flex items-center gap-2">
                      <div className="w-4 h-4 border-2 border-zinc-600 border-t-white animate-spin" />
                      Verifying
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Lock className="w-4 h-4" />
                      Unlock
                    </span>
                  )}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            <div>
              <label className={industrialStyles.label}>Internal Fleet Company Name</label>
              <input
                type="text"
                value={fleetCompanyName}
                onChange={(e) => setFleetCompanyName(e.target.value)}
                placeholder="e.g. 77 Cargo"
                maxLength={255}
                className={`${industrialStyles.input} max-w-md`}
              />
              <p className="mt-1 text-xs text-zinc-500">The company that operates your internal fleet. Shown as the customer on internal fleet work orders and on the owner's board.</p>
            </div>

            <div>
              <label className={industrialStyles.label}>Default Operating Authority</label>
              <select
                value={defaultFleetAuthorityCustomerId}
                onChange={(e) => setDefaultFleetAuthorityCustomerId(e.target.value)}
                className={`${industrialStyles.input} max-w-md`}
              >
                <option value="">No default authority</option>
                {fleetCompanies.filter((company) => company.fleet_enabled).map((company) => (
                  <option key={company.id} value={company.id}>
                    {company.company_name}{company.is_internal_fleet ? ' (internal)' : ''}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-zinc-500">New or relinked trucks with no authority preselect this company. A truck’s explicit authority always wins.</p>
            </div>

            <div className="flex gap-4 pt-4 border-t border-zinc-800/50">
              <button onClick={cancelEdit} className={industrialStyles.btnSecondary}>
                Cancel
              </button>
              {hasChanges && (
                <button
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending}
                  className={industrialStyles.btnPrimary}
                >
                  {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
                </button>
              )}
            </div>
          </div>
        )}
      </IndustrialCard>

      {/* Live fleet summary — managers and trucks, pulled from the fleet board. */}
      <IndustrialCard className="db-settings-fleet-overview p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4">
          <div className={industrialStyles.sectionHeader} style={{ marginBottom: 0 }}>
            <Truck className="w-4 h-4 text-[var(--accent-400)]" />
            <span>Fleet Overview</span>
          </div>
          <button
            onClick={() => navigate('/fleet', {
              state: {
                returnTo: '/dashboard/settings?section=fleet',
                returnLabel: 'Profile Settings',
              },
            })}
            className={industrialStyles.btnSecondary}
          >
            <span className="flex items-center gap-2">
              Manage on Fleet board
              <ChevronRight className="w-4 h-4" />
            </span>
          </button>
        </div>

        <section className="db-settings-fleet-overview__section">
          <h3 className={industrialStyles.label}>Managers ({fleetSettings?.fleet_managers.length ?? 0})</h3>
          {(fleetSettings?.fleet_managers.length ?? 0) === 0 ? (
            <p className="text-sm text-zinc-500 mt-1">No fleet managers assigned yet.</p>
          ) : (
            <div className="db-settings-fleet-overview__manager-list mt-2">
              {fleetSettings?.fleet_managers.map((m) => (
                <div key={m.id} className="db-settings-fleet-overview__manager flex items-center justify-between gap-3">
                  <span className="text-sm text-zinc-100">{m.name}</span>
                  <span className="text-xs text-zinc-500">{m.email}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="db-settings-fleet-overview__section">
          <h3 className={industrialStyles.label}>Trucks ({fleetSettings?.truck_count ?? trucks.length})</h3>
          {trucks.length === 0 ? (
            <p className="text-sm text-zinc-500 mt-1">No trucks on the fleet yet. Add them from the Fleet board.</p>
          ) : (
            <div className="db-settings-fleet-overview__table-wrap mt-2 max-h-72 overflow-y-auto">
              <table className="db-settings-fleet-overview__table w-full text-left">
                <thead>
                  <tr>
                    <th scope="col">Unit</th>
                    <th scope="col">Vehicle</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trucks.map((t) => (
                    <tr key={t.id}>
                      <td className="font-medium text-zinc-100">{t.unit_number || '—'}</td>
                      <td>
                        <p className="text-sm text-zinc-100 truncate">
                          {[t.year, t.make, t.model].filter(Boolean).join(' ') || 'Truck'}
                        </p>
                        <p className="text-xs text-zinc-500 mt-0.5">
                          <span className="font-mono">VIN: {t.vin || '—'}</span>
                          <span className="mx-2">·</span>
                          {t.odometer != null ? `${t.odometer.toLocaleString()} mi` : '— mi'}
                        </p>
                      </td>
                      <td className="text-xs text-zinc-500 capitalize whitespace-nowrap">{t.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </IndustrialCard>
    </div>
  )
}

function WorkforceSection() {
  const queryClient = useQueryClient()
  const [timezone, setTimezone] = useState('America/New_York')
  const [coreMinutes, setCoreMinutes] = useState('480')
  const [shiftStart, setShiftStart] = useState('08:00')
  const [shiftEnd, setShiftEnd] = useState('18:00')
  const [isEditing, setIsEditing] = useState(false)

  const timezoneOptions = (() => {
    const fallback = [
      'America/New_York',
      'America/Chicago',
      'America/Denver',
      'America/Phoenix',
      'America/Los_Angeles',
      'America/Anchorage',
      'Pacific/Honolulu',
      'UTC',
    ]
    try {
      const intlAny = Intl as any
      if (typeof intlAny.supportedValuesOf === 'function') {
        const values = intlAny.supportedValuesOf('timeZone') as string[]
        if (Array.isArray(values) && values.length > 0) return values
      }
    } catch {}
    return fallback
  })()

  const { data: workforceSettings } = useQuery<WorkforceSettings>({
    queryKey: ['workforce-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/workforce-settings')
      return response.data
    },
  })

  useEffect(() => {
    if (workforceSettings) {
      setTimezone(workforceSettings.timezone || 'America/New_York')
      setCoreMinutes((workforceSettings.default_core_hours_minutes || 480).toString())
      setShiftStart(workforceSettings.default_shift_start_local || '08:00')
      setShiftEnd(workforceSettings.default_shift_end_local || '18:00')
      setIsEditing(false)
    }
  }, [workforceSettings])

  const hasChanges = workforceSettings && (
    timezone !== workforceSettings.timezone ||
    coreMinutes !== String(workforceSettings.default_core_hours_minutes) ||
    shiftStart !== workforceSettings.default_shift_start_local ||
    shiftEnd !== workforceSettings.default_shift_end_local
  )

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        timezone,
        default_core_hours_minutes: parseInt(coreMinutes, 10),
        default_shift_start_local: shiftStart,
        default_shift_end_local: shiftEnd,
      }
      const response = await api.put('/admin/workforce-settings', payload)
      return response.data
    },
    onSuccess: () => {
      toast.success('Workforce settings saved')
      queryClient.invalidateQueries({ queryKey: ['workforce-settings'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-team'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-board-detail'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-day-summary'] })
      setIsEditing(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save workforce settings')
    },
  })

  const cancelEdit = () => {
    if (!workforceSettings) return
    setTimezone(workforceSettings.timezone)
    setCoreMinutes(String(workforceSettings.default_core_hours_minutes))
    setShiftStart(workforceSettings.default_shift_start_local)
    setShiftEnd(workforceSettings.default_shift_end_local)
    setIsEditing(false)
  }

  const handleSave = () => {
    const core = parseInt(coreMinutes, 10)
    if (Number.isNaN(core) || core < 1 || core > 1440) {
      toast.error('Core minutes must be between 1 and 1440')
      return
    }
    if (!/^\d{2}:\d{2}$/.test(shiftStart) || !/^\d{2}:\d{2}$/.test(shiftEnd)) {
      toast.error('Shift times must use HH:MM')
      return
    }
    if (shiftStart >= shiftEnd) {
      toast.error('Shift start must be before shift end')
      return
    }
    saveMutation.mutate()
  }

  return (
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Globe className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Workforce Configuration</span>
        </div>

        <div className="space-y-6">
          <div>
            <label className={industrialStyles.label}>Timezone</label>
            <select
              value={timezone}
              onChange={(e) => { setTimezone(e.target.value); setIsEditing(true) }}
              className={`${industrialStyles.input} cursor-pointer`}
            >
              {timezoneOptions.map((tz) => (
                <option key={tz} value={tz} className="bg-zinc-900 text-zinc-100">
                  {tz}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className={industrialStyles.label}>
                Core Minutes
                {coreMinutes && !Number.isNaN(parseInt(coreMinutes, 10)) && (
                  <span className="text-zinc-500 font-normal ml-2">({(parseInt(coreMinutes, 10) / 60).toFixed(1)}h)</span>
                )}
              </label>
              <input
                type="number"
                min={1}
                max={1440}
                value={coreMinutes}
                onChange={(e) => {
                  const newCore = parseInt(e.target.value, 10)
                  setCoreMinutes(e.target.value)
                  setIsEditing(true)
                  if (!Number.isNaN(newCore) && shiftStart) {
                    const [startH, startM] = shiftStart.split(':').map(Number)
                    const [endH, endM] = shiftEnd.split(':').map(Number)
                    if (!Number.isNaN(startH) && !Number.isNaN(startM) && !Number.isNaN(endH) && !Number.isNaN(endM)) {
                      const shiftMinutes = (endH * 60 + endM) - (startH * 60 + startM)
                      if (newCore > shiftMinutes) {
                        const newEndTotal = (startH * 60 + startM) + newCore
                        const newEndH = Math.floor(newEndTotal / 60) % 24
                        const newEndM = newEndTotal % 60
                        setShiftEnd(`${newEndH.toString().padStart(2, '0')}:${newEndM.toString().padStart(2, '0')}`)
                      }
                    }
                  }
                }}
                className={industrialStyles.input}
              />
            </div>
            <div>
              <label className={industrialStyles.label}>Shift Start (HH:MM)</label>
              <input
                type="text"
                value={shiftStart}
                onChange={(e) => { setShiftStart(e.target.value); setIsEditing(true) }}
                className={industrialStyles.input}
                placeholder="08:00"
              />
            </div>
            <div>
              <label className={industrialStyles.label}>Shift End (HH:MM)</label>
              <input
                type="text"
                value={shiftEnd}
                onChange={(e) => { setShiftEnd(e.target.value); setIsEditing(true) }}
                className={industrialStyles.input}
                placeholder="18:00"
              />
            </div>
          </div>

          {isEditing && (
            <div className="flex gap-4 pt-4 border-t border-zinc-800/50">
              <button onClick={cancelEdit} className={industrialStyles.btnSecondary}>
                Cancel
              </button>
              {hasChanges && (
                <button
                  onClick={handleSave}
                  disabled={saveMutation.isPending}
                  className={industrialStyles.btnPrimary}
                >
                  {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
                </button>
              )}
            </div>
          )}
        </div>
      </IndustrialCard>
    </div>
  )
}

export function LegacyAppearanceSection() {
  const {
    accent,
    setAccent,
    fontFamily,
    setFontFamily,
    fontSize,
    setFontSize,
    notificationPosition,
    setNotificationPosition,
    accentColors,
    resetToDefaults,
  } = useTheme()
  const previewNotificationPosition = (position: typeof notificationPosition) => {
    setNotificationPosition(position)
    const toastPosition =
      position === 'center-top' ? 'top-center' :
      position === 'top' ? 'top-right' :
      'bottom-right'
    const label = NOTIFICATION_POSITION_OPTIONS.find(option => option.id === position)?.label || 'selected'

    toast.success(`Notification preview: ${label}`, {
      id: 'notification-position-preview',
      position: toastPosition,
    })
  }

  return (
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      {/* Live Preview */}
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Palette className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Live Preview</span>
          <button
            onClick={resetToDefaults}
            className="ml-auto px-3 py-1.5 text-xs font-medium text-zinc-500 hover:text-zinc-300 border border-zinc-700/50 hover:border-zinc-600 rounded-lg transition-colors flex items-center gap-2"
          >
            <RotateCcw className="w-3 h-3" />
            Reset
          </button>
        </div>

        <div className="p-4 bg-zinc-800/40 border border-zinc-700/50 rounded-xl" style={{ borderColor: accentColors[500] + '40' }}>
          <div className="flex items-center gap-3 mb-4">
            <div 
              className="w-10 h-10 flex items-center justify-center rounded-xl border"
              style={{ backgroundColor: accentColors[500] + '20', borderColor: accentColors[500] + '60' }}
            >
              <Palette className="w-5 h-5" style={{ color: accentColors[500] }} />
            </div>
            <div>
              <h4 className="font-semibold text-zinc-100">Theme Preview</h4>
              <p className="text-xs text-zinc-500">See how your theme looks</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button 
              className="px-4 py-2.5 text-white text-sm font-semibold rounded-xl border transition-all hover:shadow-lg"
              style={{ backgroundColor: accentColors[500], borderColor: accentColors[400] + '60' }}
            >
              Primary Button
            </button>
            <button 
              className="px-4 py-2.5 text-sm font-semibold rounded-xl border bg-transparent transition-all"
              style={{ borderColor: accentColors[500], color: accentColors[500] }}
            >
              Secondary
            </button>
            <span 
              className="px-3 py-1.5 text-xs font-semibold rounded-full border"
              style={{ backgroundColor: accentColors[500] + '20', color: accentColors[400], borderColor: accentColors[500] + '40' }}
            >
              Badge
            </span>
          </div>
        </div>
      </IndustrialCard>

      {/* Accent Color */}
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Zap className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Accent Color</span>
        </div>

        <div className="flex flex-wrap gap-4">
          {ACCENT_OPTIONS.map((option, i) => (
            <button
              key={option.id}
              onClick={() => setAccent(option.id)}
              style={staggeredReveal(i)}
              className={`group flex flex-col items-center gap-2 p-3 rounded-xl border transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
                accent === option.id
                  ? 'border-white/50 bg-zinc-800/80'
                  : 'border-zinc-700/50 hover:border-zinc-600 bg-zinc-800/40'
              }`}
            >
              <div
                className={`w-10 h-10 sm:w-12 sm:h-12 flex items-center justify-center rounded-xl border transition-all ${
                  accent === option.id ? 'scale-110' : 'group-hover:scale-105'
                }`}
                style={{ backgroundColor: option.colors[500], borderColor: option.colors[400] + '60' }}
              >
                {accent === option.id && (
                  <Check className="w-5 h-5 text-white drop-shadow-md" />
                )}
              </div>
              <span className={`text-xs font-medium ${
                accent === option.id ? 'text-white' : 'text-zinc-500 group-hover:text-zinc-400'
              }`}>
                {option.label}
              </span>
            </button>
          ))}
        </div>
      </IndustrialCard>

      {/* Font Family */}
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Type className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Font Family</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {FONT_FAMILY_OPTIONS.map((option, i) => (
            <button
              key={option.id}
              onClick={() => setFontFamily(option.id)}
              style={{ ...staggeredReveal(i), fontFamily: option.stack }}
              className={`p-4 text-left rounded-xl border transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
                fontFamily === option.id
                  ? 'border-white/50 bg-zinc-800/80'
                  : 'border-zinc-700/50 hover:border-zinc-600 bg-zinc-800/40'
              }`}
            >
              <span className={`block text-sm font-semibold ${fontFamily === option.id ? 'text-white' : 'text-zinc-400'}`}>
                {option.label}
              </span>
              <span className="block text-xs text-zinc-600 mt-1">Aa Bb Cc 123</span>
            </button>
          ))}
        </div>
      </IndustrialCard>

      {/* Font Size */}
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Settings2 className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Font Size</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {FONT_SIZE_OPTIONS.map((option, i) => (
            <button
              key={option.id}
              onClick={() => setFontSize(option.id)}
              style={staggeredReveal(i)}
              className={`py-3 px-4 text-center rounded-xl border transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
                fontSize === option.id
                  ? 'border-white/50 bg-zinc-800/80'
                  : 'border-zinc-700/50 hover:border-zinc-600 bg-zinc-800/40'
              }`}
            >
              <span className={`block text-sm font-semibold ${fontSize === option.id ? 'text-white' : 'text-zinc-400'}`}>
                {option.label}
              </span>
              <span className="hidden sm:block text-xs text-zinc-600 mt-1">
                {option.previewPx}px
              </span>
            </button>
          ))}
        </div>
        <p className="mt-4 text-xs text-zinc-600">
          Extra-wide screens automatically compact dashboard spacing.
        </p>
      </IndustrialCard>

      {/* Notification Location */}
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Bell className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Notification Location</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {NOTIFICATION_POSITION_OPTIONS.map((option, i) => (
            <button
              key={option.id}
              type="button"
              onClick={() => previewNotificationPosition(option.id)}
              style={staggeredReveal(i)}
              className={`p-4 text-left rounded-xl border transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
                notificationPosition === option.id
                  ? 'border-white/50 bg-zinc-800/80'
                  : 'border-zinc-700/50 hover:border-zinc-600 bg-zinc-800/40'
              }`}
            >
              <span className={`flex items-center gap-2 text-sm font-semibold ${notificationPosition === option.id ? 'text-white' : 'text-zinc-400'}`}>
                {notificationPosition === option.id && <Check className="w-4 h-4 text-[var(--accent-400)]" />}
                {option.label}
              </span>
              <span className="block text-xs text-zinc-600 mt-2 leading-relaxed">
                {option.description}
              </span>
            </button>
          ))}
        </div>
      </IndustrialCard>

      <p className="text-xs text-zinc-600">
        All preferences are saved automatically and persist across sessions.
      </p>
    </div>
  )
}

function AppearanceSection() {
  const { presentationVariant } = useTheme()
  return presentationVariant === 'new' ? <AppearanceSettingsPanel /> : <LegacyAppearanceSection />
}

// ============ LAYOUT COMPONENTS ============

const PROFILE_SECTIONS = [
  { id: 'profile' as const, label: 'Profile', shortLabel: 'Profile', icon: User },
  { id: 'security' as const, label: 'Security', shortLabel: 'Security', icon: Lock },
  { id: 'appearance' as const, label: 'Appearance', shortLabel: 'Appearance', icon: Palette },
]

const PLATFORM_SECTIONS = [
  { id: 'integrations' as const, label: 'Integrations', shortLabel: 'Integrations', icon: Landmark },
]

// gatedKey: owner-only sections that a garage admin can access only with an
// explicit grant in user.permissions. Hiding here is UX only — the backend
// permission checks are the actual security boundary.
const GARAGE_SECTIONS = [
  { id: 'garageProfile' as const, label: 'Shop Profile', shortLabel: 'Profile', icon: Building2, gatedKey: undefined },
  { id: 'payments' as const, label: 'Payments & Accounting', shortLabel: 'Payments', icon: CreditCard, gatedKey: 'payments' as const },
  { id: 'notifications' as const, label: 'Notifications', shortLabel: 'Alerts', icon: Bell, gatedKey: undefined },
  { id: 'fees' as const, label: 'Tax & Fees', shortLabel: 'Fees', icon: Percent, gatedKey: 'taxes_fees' as const },
  { id: 'workforce' as const, label: 'Workforce', shortLabel: 'Workforce', icon: Globe, gatedKey: 'workforce' as const },
]

const ADDITIONAL_SERVICE_SECTIONS = [
  { id: 'fleet' as const, label: 'Fleet', shortLabel: 'Fleet', icon: Truck, gatedKey: undefined },
  { id: 'googleReviews' as const, label: 'Google Reviews', shortLabel: 'Reviews', icon: Star, gatedKey: undefined },
]

function canSeeSection(user: UserType | null, gatedKey?: string): boolean {
  if (!gatedKey) return true
  if (user?.role === 'garage_owner') return true
  if (user?.role === 'garage_admin') return !!user.permissions?.[gatedKey]
  return false
}

function SidebarLayout({ activeSection, setActiveSection, isGarageUser, isSuperAdmin, user }: { activeSection: SettingsSection, setActiveSection: (s: SettingsSection) => void, isGarageUser: boolean, isSuperAdmin: boolean, user: UserType | null }) {
  const mobileSectionMenuId = useId()
  const mobileSectionSelectorRef = useRef<HTMLDivElement>(null)
  const [isMobileSectionMenuOpen, setIsMobileSectionMenuOpen] = useState(false)
  const garageSections = GARAGE_SECTIONS.filter((s) => canSeeSection(user, s.gatedKey))
  const additionalServiceSections = ADDITIONAL_SERVICE_SECTIONS.filter((s) => canSeeSection(user, s.gatedKey))
  const allSections = [
    ...PROFILE_SECTIONS,
    ...(isSuperAdmin ? PLATFORM_SECTIONS : []),
    ...(isGarageUser ? [...garageSections, ...additionalServiceSections] : []),
  ]
  const activeSectionMeta = allSections.find((section) => section.id === activeSection) ?? allSections[0]
  const ActiveSectionIcon = activeSectionMeta.icon
  const mobileSectionGroups = [
    { label: 'Account', sections: PROFILE_SECTIONS },
    ...(isSuperAdmin ? [{ label: 'Platform', sections: PLATFORM_SECTIONS }] : []),
    ...(isGarageUser ? [{ label: 'Shop', sections: garageSections }] : []),
    ...(isGarageUser && additionalServiceSections.length > 0 ? [{ label: 'Additional services', sections: additionalServiceSections }] : []),
  ]

  const selectMobileSection = (section: SettingsSection) => {
    setActiveSection(section)
    setIsMobileSectionMenuOpen(false)
  }

  useEffect(() => {
    if (!isMobileSectionMenuOpen) return

    const closeWhenPointerLeaves = (event: PointerEvent) => {
      if (!mobileSectionSelectorRef.current?.contains(event.target as Node)) {
        setIsMobileSectionMenuOpen(false)
      }
    }

    document.addEventListener('pointerdown', closeWhenPointerLeaves)
    return () => document.removeEventListener('pointerdown', closeWhenPointerLeaves)
  }, [isMobileSectionMenuOpen])

  return (
    <div className="db-settings-workspace flex flex-col lg:flex-row gap-6 w-full max-w-[1200px] mx-auto">
      {/* New presentation: one compact context selector prevents section tabs
          from becoming an unreadable horizontal scroller on narrow screens. */}
      <div ref={mobileSectionSelectorRef} className="db-settings-mobile-section-selector lg:hidden">
        <button
          type="button"
          aria-label={`Settings section: ${activeSectionMeta.label}`}
          aria-expanded={isMobileSectionMenuOpen}
          aria-controls={mobileSectionMenuId}
          aria-haspopup="true"
          onClick={() => setIsMobileSectionMenuOpen((open) => !open)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') setIsMobileSectionMenuOpen(false)
          }}
          className="db-settings-mobile-section-selector__trigger"
        >
          <ActiveSectionIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate text-left">{activeSectionMeta.label}</span>
          <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${isMobileSectionMenuOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
        </button>
        {isMobileSectionMenuOpen && (
          <div
            id={mobileSectionMenuId}
            role="group"
            aria-label="Settings sections"
            className="db-settings-mobile-section-selector__menu"
            onKeyDown={(event) => {
              if (event.key === 'Escape') setIsMobileSectionMenuOpen(false)
            }}
          >
            {mobileSectionGroups.map((group) => (
              <div key={group.label} className="db-settings-mobile-section-selector__group">
                <p className="db-settings-mobile-section-selector__group-label">{group.label}</p>
                <div className="space-y-1">
                  {group.sections.map((section) => (
                    <button
                      key={section.id}
                      type="button"
                      data-active={activeSection === section.id}
                      aria-current={activeSection === section.id ? 'page' : undefined}
                      onClick={() => selectMobileSection(section.id)}
                      className="db-settings-mobile-section-selector__option"
                    >
                      <section.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span className="min-w-0 flex-1 text-left">{section.label}</span>
                      {activeSection === section.id && <Check className="h-4 w-4 shrink-0" aria-hidden="true" />}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Legacy mobile presentation keeps the existing horizontal navigation
          as the immediate rollback path. */}
      <div className="db-settings-mobile-legacy-nav lg:hidden">
        <div className="bg-zinc-900/80 backdrop-blur-sm border border-zinc-700/50 rounded-2xl p-2">
          <nav className="flex gap-2 overflow-x-auto scrollbar-hide" style={{ WebkitOverflowScrolling: 'touch' }}>
            {allSections.map((section) => (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                data-active={activeSection === section.id}
                className={`db-settings-nav-item flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-medium transition-colors flex-shrink-0 rounded-xl border ${
                  activeSection === section.id
                    ? 'bg-[var(--accent-600)] border-[var(--accent-400)]/50 text-white shadow-lg shadow-[var(--accent-500)]/20'
                    : 'bg-zinc-800/60 border-zinc-700/50 text-zinc-500 hover:text-zinc-300 hover:border-zinc-600'
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
      <div className="db-settings-sidebar hidden lg:block w-72 flex-shrink-0 self-stretch">
        <div className="db-settings-sidebar__panel bg-zinc-900/80 backdrop-blur-sm border border-zinc-700/50 rounded-2xl p-4 sticky top-4">
          {/* Account Group */}
          <div className="db-settings-sidebar__group mb-6">
            <h3 className={industrialStyles.sectionHeader}>
              <User className="w-3 h-3" />
              Account
            </h3>
            <nav className="space-y-1">
              {PROFILE_SECTIONS.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  data-active={activeSection === section.id}
                  className={`db-settings-nav-item w-full flex items-center gap-3 px-3 py-3 text-sm font-medium transition-colors rounded-xl ${
                    activeSection === section.id
                      ? 'bg-[var(--accent-500)]/10 text-[var(--accent-400)] border border-[var(--accent-500)]/30'
                      : 'border border-transparent text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60'
                  }`}
                >
                  <section.icon className="w-4 h-4 flex-shrink-0" />
                  <span className="whitespace-nowrap">{section.label}</span>
                  {activeSection === section.id && (
                    <ChevronRight className="w-4 h-4 ml-auto mr-1 flex-shrink-0" />
                  )}
                </button>
              ))}
            </nav>
          </div>

          {/* Platform Group */}
          {isSuperAdmin && (
            <div className="db-settings-sidebar__group mb-6">
              <h3 className={industrialStyles.sectionHeader}>
                <Settings2 className="w-3 h-3" />
                Platform
              </h3>
              <nav className="space-y-1">
                {PLATFORM_SECTIONS.map((section) => (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    data-active={activeSection === section.id}
                    className={`db-settings-nav-item w-full flex items-center gap-3 px-3 py-3 text-sm font-medium transition-colors rounded-xl ${
                      activeSection === section.id
                        ? 'bg-[var(--accent-500)]/10 text-[var(--accent-400)] border border-[var(--accent-500)]/30'
                        : 'border border-transparent text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60'
                    }`}
                  >
                    <section.icon className="w-4 h-4 flex-shrink-0" />
                    <span className="whitespace-nowrap">{section.label}</span>
                    {activeSection === section.id && (
                      <ChevronRight className="w-4 h-4 ml-auto mr-1 flex-shrink-0" />
                    )}
                  </button>
                ))}
              </nav>
            </div>
          )}

          {/* Garage Group */}
          {isGarageUser && (
            <div className="db-settings-sidebar__group mb-6">
              <h3 className={industrialStyles.sectionHeader}>
                <Settings2 className="w-3 h-3" />
                Shop
              </h3>
              <nav className="space-y-1">
                {garageSections.map((section) => (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    data-active={activeSection === section.id}
                    className={`db-settings-nav-item w-full flex items-center gap-3 px-3 py-3 text-sm font-medium transition-colors rounded-xl ${
                      activeSection === section.id
                        ? 'bg-[var(--accent-500)]/10 text-[var(--accent-400)] border border-[var(--accent-500)]/30'
                        : 'border border-transparent text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60'
                  }`}
                >
                    <section.icon className="w-4 h-4 flex-shrink-0" />
                    <span className="whitespace-nowrap">{section.label}</span>
                    {activeSection === section.id && (
                      <ChevronRight className="w-4 h-4 ml-auto mr-1 flex-shrink-0" />
                    )}
                  </button>
                ))}
              </nav>
            </div>
          )}

          {/* Fleet is an optional tenant capability rather than a second My Shop
              destination. It stays beside configuration, then hands off to the
              existing Fleet Board from its own overview. */}
          {isGarageUser && additionalServiceSections.length > 0 && (
            <div className="db-settings-sidebar__additional pt-6">
              <h3 className={industrialStyles.sectionHeader}>
                <Truck className="w-3 h-3" />
                Additional services
              </h3>
              <nav className="space-y-1" aria-label="Additional services">
                {additionalServiceSections.map((section) => (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    data-active={activeSection === section.id}
                    className={`db-settings-nav-item w-full flex items-center gap-3 px-3 py-3 text-sm font-medium transition-colors rounded-xl ${
                      activeSection === section.id
                        ? 'bg-[var(--accent-500)]/10 text-[var(--accent-400)] border border-[var(--accent-500)]/30'
                        : 'border border-transparent text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60'
                    }`}
                  >
                    <section.icon className="w-4 h-4 flex-shrink-0" />
                    <span className="whitespace-nowrap">{section.label}</span>
                    {activeSection === section.id && (
                      <ChevronRight className="w-4 h-4 ml-auto mr-1 flex-shrink-0" />
                    )}
                  </button>
                ))}
              </nav>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-[400px] lg:min-h-[600px]">
        {activeSection === 'profile' && <ProfileSection />}
        {activeSection === 'security' && <SecuritySection />}
        {activeSection === 'appearance' && <AppearanceSection />}
        {activeSection === 'integrations' && isSuperAdmin && <PlatformIntegrationsSection />}
        {activeSection === 'garageProfile' && <GarageProfileSection />}
        {activeSection === 'payments' && <PaymentsSection />}
        {activeSection === 'notifications' && <NotificationsSection />}
        {activeSection === 'fees' && <FeesSection />}
        {activeSection === 'fleet' && <FleetSection />}
        {activeSection === 'googleReviews' && <GoogleReviewsPage />}
        {activeSection === 'workforce' && <WorkforceSection />}
      </div>
    </div>
  )
}

// ============ MAIN COMPONENT ============

export default function UnifiedSettingsPage() {
  const { user } = useAuthStore()
  const [settingsSearchParams, setSettingsSearchParams] = useSearchParams()
  const requestedSection = settingsSearchParams.get('section')
  const [activeSection, setActiveSection] = useState<SettingsSection>(() => (
    requestedSection === 'fleet' ? 'fleet' : 'profile'
  ))

  const isGarageUser = user?.role === 'garage_owner' || user?.role === 'garage_admin'
  const isSuperAdmin = user?.role === 'super_admin'

  useEffect(() => {
    scrollSurfaceToTop(document.querySelector<HTMLElement>('.db-settings-workspace'))
  }, [activeSection])

  useEffect(() => {
    if (settingsSearchParams.has('quickbooks') && isGarageUser) {
      setActiveSection('payments')
    }
  }, [isGarageUser, settingsSearchParams])

  // Fleet is the only Settings surface that hands off to a separate board.
  // Keep that context in the existing Settings URL so either browser Back or
  // Fleet's return control restores the originating section after remounting.
  useEffect(() => {
    if (activeSection === 'fleet' && requestedSection !== 'fleet') {
      const nextSearchParams = new URLSearchParams(settingsSearchParams)
      nextSearchParams.set('section', 'fleet')
      setSettingsSearchParams(nextSearchParams, { replace: true })
    }
    if (activeSection !== 'fleet' && requestedSection === 'fleet') {
      const nextSearchParams = new URLSearchParams(settingsSearchParams)
      nextSearchParams.delete('section')
      setSettingsSearchParams(nextSearchParams, { replace: true })
    }
  }, [activeSection, requestedSection, setSettingsSearchParams, settingsSearchParams])

  // If the active section becomes inaccessible (e.g. the owner revoked a
  // grant), fall back to the profile section instead of a blank pane.
  useEffect(() => {
    const gated = [...GARAGE_SECTIONS, ...ADDITIONAL_SERVICE_SECTIONS].find((s) => s.id === activeSection)
    if (gated && !canSeeSection(user ?? null, gated.gatedKey)) {
      setActiveSection('profile')
    }
    if (activeSection === 'integrations' && !isSuperAdmin) {
      setActiveSection('profile')
    }
  }, [activeSection, isSuperAdmin, user])

  return (
    <SidebarLayout activeSection={activeSection} setActiveSection={setActiveSection} isGarageUser={isGarageUser} isSuperAdmin={isSuperAdmin} user={user ?? null} />
  )
}

// Add keyframes for animations
const style = document.createElement('style')
style.textContent = `
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
`
if (typeof document !== 'undefined' && !document.querySelector('[data-industrial-styles]')) {
  style.setAttribute('data-industrial-styles', '')
  document.head.appendChild(style)
}
