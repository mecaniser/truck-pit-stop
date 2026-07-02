import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../../stores/authStore'
import api from '../../lib/api'
import { tenantBrandingQueryKey } from '@/hooks/useTenantBranding'
import { formatUSPhone, isValidUSPhone } from '@/utils/phone'
import toast from 'react-hot-toast'
import { 
  User, Lock, CreditCard, Bell, Percent, QrCode, Globe, Building2,
  AlertCircle, ExternalLink, RefreshCw, Save, Trash2, Palette, Check, RotateCcw, Type,
  ChevronRight, Zap, Shield, Settings2, Truck
} from 'lucide-react'
import { useTheme, ACCENT_OPTIONS, FONT_FAMILY_OPTIONS, FONT_SIZE_OPTIONS } from '../../contexts/ThemeContext'

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
  name: z.string().min(1, 'Garage name is required').max(255, 'Maximum 255 characters'),
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
})

type ProfileFormData = z.infer<typeof profileSchema>
type PasswordFormData = z.infer<typeof passwordSchema>
type GarageProfileFormData = z.infer<typeof garageProfileSchema>

// ============ TYPES ============
type SettingsSection = 'profile' | 'security' | 'appearance' | 'garageProfile' | 'payments' | 'zelle' | 'notifications' | 'fees' | 'fleet' | 'workforce'

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
  labor_rate: number
  internal_labor_rate: number
  fleet_company_name: string | null
}

interface FleetManager {
  id: string
  name: string
  email: string
}

interface FleetSettings {
  internal_labor_rate: number
  fleet_company_name: string | null
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
}

// ============ INDUSTRIAL COMPONENTS ============

function IndustrialCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`${industrialStyles.card} ${className}`}>
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
    <span className={`inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold rounded-full border ${variants[variant]}`}>
      {children}
    </span>
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
      case 'garage_owner': return { label: 'GARAGE OWNER', variant: 'success' as const }
      case 'garage_admin': return { label: 'GARAGE ADMIN', variant: 'default' as const }
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
      }
      const response = await api.put('/admin/garage-profile', payload)
      return response.data as GarageProfile
    },
    onSuccess: (updated) => {
      syncTenantBranding(updated)
      setIsEditing(false)
      toast.success('Garage profile updated')
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
            <span>Garage Profile</span>
          </div>
          <p className="text-sm text-zinc-400">Loading garage profile...</p>
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
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Building2 className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Garage Profile</span>
        </div>

        {!isEditing ? (
          <div className="space-y-6">
            <div className="rounded-2xl border border-zinc-700/50 bg-zinc-950/50 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <label className={industrialStyles.label}>Garage Logo</label>
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

              <div className="mt-4 flex min-h-[160px] items-center justify-center rounded-2xl border border-dashed border-zinc-700/60 bg-zinc-900/50 p-6">
                {garageProfile?.logo_url ? (
                  <img
                    src={garageProfile.logo_url}
                    alt={`${garageProfile.name} logo`}
                    className="max-h-24 w-auto max-w-full object-contain"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <div className="text-center text-sm text-zinc-500">
                    <p>Use the website importer or paste a logo URL in Garage Profile settings.</p>
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              {[
                { label: 'Garage Name', value: garageProfile?.name || '—' },
                { label: 'Garage Slug', value: garageProfile?.slug || '—' },
                { label: 'Garage Email', value: garageProfile?.email || '—' },
                { label: 'Garage Phone', value: garageProfile?.phone ? formatUSPhone(garageProfile.phone) : '—' },
                { label: 'Website', value: garageProfile?.website || '—' },
                { label: 'Address', value: garageProfile?.address || '—' },
              ].map((field, index) => (
                <div key={field.label} style={staggeredReveal(index)} className="animate-[fadeIn_0.3s_ease-out_forwards] opacity-0">
                  <label className={industrialStyles.label}>{field.label}</label>
                  <p className="text-lg text-zinc-100 border-b border-zinc-800/50 pb-2 break-words">
                    {field.value}
                  </p>
                </div>
              ))}
            </div>

            <div className="rounded-2xl border border-zinc-700/50 bg-zinc-950/50 p-5">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <label className={industrialStyles.label}>Landing Page Partner Profile</label>
                  <p className="text-sm text-zinc-500">
                    Approved businesses appear automatically. These fields control the public summary shown on the landing page.
                  </p>
                </div>
                <IndustrialBadge variant="success">
                  Public profile
                </IndustrialBadge>
              </div>

              <div className="mt-5 grid gap-5 sm:grid-cols-2">
                <div>
                  <label className={industrialStyles.label}>Summary</label>
                  <p className="text-base leading-7 text-zinc-100">
                    {garageProfile?.partner_summary || 'Add a short summary to describe this garage on the landing page.'}
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
                Edit Garage Profile
              </span>
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            <div>
              <label className={industrialStyles.label}>Garage Name</label>
              <input {...register('name')} className={inputClasses(!!errors.name)} />
              {errors.name && <p className="mt-2 text-xs text-red-400">{errors.name.message}</p>}
            </div>

            <div>
              <label className={industrialStyles.label}>Garage Slug (read-only)</label>
              <input value={garageProfile?.slug || ''} className={`${industrialStyles.input} opacity-70`} disabled />
            </div>

            <div>
              <label className={industrialStyles.label}>Garage Email</label>
              <input {...register('email')} type="email" className={inputClasses(!!errors.email)} placeholder="garage@example.com" />
              {errors.email && <p className="mt-2 text-xs text-red-400">{errors.email.message}</p>}
            </div>

            <div>
              <label className={industrialStyles.label}>Garage Phone</label>
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

              <div className="rounded-2xl border border-zinc-700/50 bg-zinc-950/50 p-4">
                <label className={industrialStyles.label}>Logo Preview</label>
                <div className="flex min-h-[180px] items-center justify-center rounded-2xl border border-dashed border-zinc-700/60 bg-zinc-900/50 p-5">
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
                {updateMutation.isPending ? 'Saving...' : 'Save Garage Profile'}
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
    return (
      <div className="flex justify-center py-12">
        <div className="w-8 h-8 border-2 border-zinc-600 border-t-[var(--accent-400)] rounded-full animate-spin" />
      </div>
    )
  }

  const getStatusConfig = () => {
    if (!status?.is_connected) {
      return { led: 'inactive' as const, title: 'NOT CONNECTED', desc: 'Connect your Stripe account to receive payments.' }
    }
    if (!status.onboarding_complete) {
      return { led: 'warning' as const, title: 'SETUP INCOMPLETE', desc: 'Please finish the Stripe onboarding process.' }
    }
    return { led: 'active' as const, title: 'CONNECTED & ACTIVE', desc: 'Payments will be deposited to your account.' }
  }

  const statusConfig = getStatusConfig()

  return (
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <CreditCard className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Stripe Payments</span>
        </div>

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

        <div className="pt-4 border-t border-zinc-800/50">
          {!status?.is_connected ? (
            <button
              onClick={() => onboardMutation.mutate()}
              disabled={onboardMutation.isPending || isRedirecting}
              className={industrialStyles.btnPrimary}
            >
              {onboardMutation.isPending || isRedirecting ? (
                <span className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-zinc-600 border-t-white rounded-full animate-spin" />
                  Redirecting...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <CreditCard className="w-4 h-4" />
                  Connect Stripe
                </span>
              )}
            </button>
          ) : !status.onboarding_complete ? (
            <button
              onClick={() => refreshMutation.mutate()}
              disabled={refreshMutation.isPending || isRedirecting}
              className={`${industrialStyles.btnPrimary} bg-amber-600 hover:bg-amber-500 border-amber-400`}
            >
              {refreshMutation.isPending || isRedirecting ? (
                <span className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-zinc-600 border-t-white rounded-full animate-spin" />
                  Redirecting...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <RefreshCw className="w-4 h-4" />
                  Continue Setup
                </span>
              )}
            </button>
          ) : (
            <button
              onClick={() => dashboardMutation.mutate()}
              disabled={dashboardMutation.isPending}
              className={industrialStyles.btnSecondary}
            >
              <span className="flex items-center gap-2">
                <ExternalLink className="w-4 h-4" />
                Open Stripe Dashboard
              </span>
            </button>
          )}
        </div>
      </IndustrialCard>
    </div>
  )
}

function ZelleSection() {
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
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <QrCode className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Zelle Payments</span>
        </div>

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
      </IndustrialCard>
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
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
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
              className={`relative w-14 h-8 rounded-full border transition-colors ${
                remindersEnabled 
                  ? 'bg-[var(--accent-600)] border-[var(--accent-400)]/50' 
                  : 'bg-zinc-800 border-zinc-600/50'
              }`}
            >
              <span className={`absolute top-1 w-5 h-5 bg-white rounded-full transition-transform shadow-md ${
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
                { label: 'Service Fee', value: `${taxFeeSettings?.service_fee_rate ?? 0}%` },
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
                <label className={industrialStyles.label}>Service Fee (%)</label>
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
    }
  }, [taxFeeSettings])

  const hasChanges = !!taxFeeSettings &&
    fleetCompanyName !== (taxFeeSettings.fleet_company_name || '')

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
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Fleet settings saved')
      queryClient.invalidateQueries({ queryKey: ['tax-fee-settings'] })
      setIsUnlocked(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save settings')
    },
  })

  const cancelEdit = () => {
    if (taxFeeSettings) {
      setFleetCompanyName(taxFeeSettings.fleet_company_name || '')
    }
    setIsUnlocked(false)
  }

  return (
    <div className="space-y-8 animate-[fadeIn_0.4s_ease-out]">
      <IndustrialCard className="p-6 sm:p-8">
        <div className={industrialStyles.sectionHeader}>
          <Truck className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Fleet Configuration</span>
        </div>

        {!isUnlocked ? (
          <div className="space-y-6">
            {/* Locked display */}
            <div className="p-3 bg-zinc-800/40 border border-zinc-700/50 rounded-xl">
              <label className={industrialStyles.label}>Fleet Company</label>
              <p className="text-lg text-zinc-100">{taxFeeSettings?.fleet_company_name || 'Not set'}</p>
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
      <IndustrialCard className="p-6 sm:p-8">
        <div className="flex items-center justify-between mb-4">
          <div className={industrialStyles.sectionHeader} style={{ marginBottom: 0 }}>
            <Truck className="w-4 h-4 text-[var(--accent-400)]" />
            <span>Fleet Overview</span>
          </div>
          <button onClick={() => navigate('/fleet')} className={industrialStyles.btnSecondary}>
            <span className="flex items-center gap-2">
              Manage on Fleet board
              <ChevronRight className="w-4 h-4" />
            </span>
          </button>
        </div>

        {/* Fleet managers list */}
        <div className="mb-6">
          <label className={industrialStyles.label}>Managers ({fleetSettings?.fleet_managers.length ?? 0})</label>
          {(fleetSettings?.fleet_managers.length ?? 0) === 0 ? (
            <p className="text-sm text-zinc-500 mt-1">No fleet managers assigned yet.</p>
          ) : (
            <div className="mt-2 space-y-1">
              {fleetSettings?.fleet_managers.map((m) => (
                <div key={m.id} className="flex items-center justify-between p-2 bg-zinc-800/30 border border-zinc-700/40 rounded-lg">
                  <span className="text-sm text-zinc-100">{m.name}</span>
                  <span className="text-xs text-zinc-500">{m.email}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Trucks list */}
        <div>
          <label className={industrialStyles.label}>Trucks ({fleetSettings?.truck_count ?? trucks.length})</label>
          {trucks.length === 0 ? (
            <p className="text-sm text-zinc-500 mt-1">No trucks on the fleet yet. Add them from the Fleet board.</p>
          ) : (
            <div className="mt-2 max-h-72 overflow-y-auto space-y-1">
              {trucks.map((t) => (
                <div key={t.id} className="flex items-start justify-between gap-3 p-2 bg-zinc-800/30 border border-zinc-700/40 rounded-lg">
                  <div className="min-w-0">
                    <p className="text-sm text-zinc-100 truncate">
                      {t.unit_number ? `${t.unit_number} · ` : ''}
                      {[t.year, t.make, t.model].filter(Boolean).join(' ') || 'Truck'}
                    </p>
                    <p className="text-xs text-zinc-500 mt-0.5">
                      <span className="font-mono">VIN: {t.vin || '—'}</span>
                      <span className="mx-2">·</span>
                      {t.odometer != null ? `${t.odometer.toLocaleString()} mi` : '— mi'}
                    </p>
                  </div>
                  <span className="text-xs text-zinc-500 capitalize shrink-0">{t.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
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

function AppearanceSection() {
  const { accent, setAccent, fontFamily, setFontFamily, fontSize, setFontSize, accentColors, resetToDefaults } = useTheme()

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

      <p className="text-xs text-zinc-600">
        All preferences are saved automatically and persist across sessions.
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
  { id: 'garageProfile' as const, label: 'Garage Profile', shortLabel: 'Profile', icon: Building2 },
  { id: 'payments' as const, label: 'Stripe Payments', shortLabel: 'Stripe', icon: CreditCard },
  { id: 'zelle' as const, label: 'Zelle', shortLabel: 'Zelle', icon: QrCode },
  { id: 'notifications' as const, label: 'Notifications', shortLabel: 'Alerts', icon: Bell },
  { id: 'fees' as const, label: 'Tax & Fees', shortLabel: 'Fees', icon: Percent },
  { id: 'fleet' as const, label: 'Fleet', shortLabel: 'Fleet', icon: Truck },
  { id: 'workforce' as const, label: 'Workforce', shortLabel: 'Workforce', icon: Globe },
]

function SidebarLayout({ activeSection, setActiveSection, isGarageUser }: { activeSection: SettingsSection, setActiveSection: (s: SettingsSection) => void, isGarageUser: boolean }) {
  const allSections = isGarageUser 
    ? [...PROFILE_SECTIONS, ...GARAGE_SECTIONS]
    : PROFILE_SECTIONS

  return (
    <div className="flex flex-col lg:flex-row gap-6 w-full max-w-[1200px] mx-auto">
      {/* Mobile: Horizontal scrolling nav */}
      <div className="lg:hidden">
        <div className="bg-zinc-900/80 backdrop-blur-sm border border-zinc-700/50 rounded-2xl p-2">
          <nav className="flex gap-2 overflow-x-auto scrollbar-hide" style={{ WebkitOverflowScrolling: 'touch' }}>
            {allSections.map((section, i) => (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                style={staggeredReveal(i)}
                className={`flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-medium transition-all flex-shrink-0 rounded-xl border animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
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
      <div className="hidden lg:block w-64 flex-shrink-0">
        <div className="bg-zinc-900/80 backdrop-blur-sm border border-zinc-700/50 rounded-2xl p-4 sticky top-4">
          {/* Account Group */}
          <div className="mb-6">
            <h3 className={industrialStyles.sectionHeader}>
              <User className="w-3 h-3" />
              Account
            </h3>
            <nav className="space-y-1">
              {PROFILE_SECTIONS.map((section, i) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  style={staggeredReveal(i)}
                  className={`w-full flex items-center gap-3 px-3 py-3 text-sm font-medium transition-all rounded-xl animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
                    activeSection === section.id
                      ? 'bg-[var(--accent-500)]/10 text-[var(--accent-400)] border border-[var(--accent-500)]/30'
                      : 'border border-transparent text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60'
                  }`}
                >
                  <section.icon className="w-4 h-4" />
                  {section.label}
                  {activeSection === section.id && (
                    <ChevronRight className="w-4 h-4 ml-auto" />
                  )}
                </button>
              ))}
            </nav>
          </div>

          {/* Garage Group */}
          {isGarageUser && (
            <div>
              <h3 className={industrialStyles.sectionHeader}>
                <Settings2 className="w-3 h-3" />
                Garage
              </h3>
              <nav className="space-y-1">
                {GARAGE_SECTIONS.map((section, i) => (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    style={staggeredReveal(i + PROFILE_SECTIONS.length)}
                    className={`w-full flex items-center gap-3 px-3 py-3 text-sm font-medium transition-all rounded-xl animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
                      activeSection === section.id
                        ? 'bg-[var(--accent-500)]/10 text-[var(--accent-400)] border border-[var(--accent-500)]/30'
                        : 'border border-transparent text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60'
                    }`}
                  >
                    <section.icon className="w-4 h-4" />
                    {section.label}
                    {activeSection === section.id && (
                      <ChevronRight className="w-4 h-4 ml-auto" />
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
        {activeSection === 'garageProfile' && <GarageProfileSection />}
        {activeSection === 'payments' && <PaymentsSection />}
        {activeSection === 'zelle' && <ZelleSection />}
        {activeSection === 'notifications' && <NotificationsSection />}
        {activeSection === 'fees' && <FeesSection />}
        {activeSection === 'fleet' && <FleetSection />}
        {activeSection === 'workforce' && <WorkforceSection />}
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
