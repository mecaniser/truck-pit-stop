import { useState, useEffect } from 'react'
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
import { formatUSPhone } from '@/utils/phone'
import { isValidUSPhone } from '@/utils/phone'
import toast from 'react-hot-toast'

function CollapsiblePasswordChange() {
  const [isOpen, setIsOpen] = useState(false)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const { logout } = useAuthStore()
  const navigate = useNavigate()

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PasswordFormData>({
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
      setSuccessMessage('Password changed! Redirecting to login...')
      // All tokens are invalidated on password change - redirect to login
      setTimeout(() => {
        logout()
        navigate('/login')
      }, 2000)
    },
    onError: (err: any) => {
      setErrorMessage(err.response?.data?.detail || 'Failed to change password')
      setTimeout(() => setErrorMessage(null), 5000)
    },
  })

  const inputClasses = (hasError: boolean) => {
    const base = "w-full px-3 py-2.5 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 text-sm"
    return hasError
      ? `${base} border-red-500 focus:ring-red-500`
      : `${base} border-white/20 focus:ring-amber-500`
  }

  return (
    <div className="border-t border-white/10 pt-5 mt-5">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between text-left group"
      >
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">
            Change Password
          </span>
        </div>
        <svg 
          className={`w-4 h-4 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} 
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="mt-4 space-y-4">
          {successMessage && (
            <div className="flex items-center gap-2 bg-green-500/20 border border-green-500/30 text-green-400 px-3 py-2 rounded-lg text-sm">
              <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              {successMessage}
            </div>
          )}

          {errorMessage && (
            <div className="flex items-center gap-2 bg-red-500/20 border border-red-500/30 text-red-400 px-3 py-2 rounded-lg text-sm">
              <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              {errorMessage}
            </div>
          )}

          <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Current Password</label>
              <input
                {...register('current_password')}
                type="password"
                className={inputClasses(!!errors.current_password)}
                placeholder="••••••••"
              />
              {errors.current_password && (
                <p className="mt-1 text-xs text-red-400">{errors.current_password.message}</p>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">New Password</label>
              <input
                {...register('new_password')}
                type="password"
                className={inputClasses(!!errors.new_password)}
                placeholder="••••••••"
              />
              {errors.new_password && (
                <p className="mt-1 text-xs text-red-400">{errors.new_password.message}</p>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Confirm New Password</label>
              <input
                {...register('confirm_password')}
                type="password"
                className={inputClasses(!!errors.confirm_password)}
                placeholder="••••••••"
              />
              {errors.confirm_password && (
                <p className="mt-1 text-xs text-red-400">{errors.confirm_password.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={mutation.isPending}
              className="w-full px-4 py-2.5 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {mutation.isPending ? 'Changing...' : 'Change Password'}
            </button>
          </form>
        </div>
      )}
    </div>
  )
}

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

export default function ProfileSettingsPage() {
  const { user, logout, setUser } = useAuthStore()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [isEditingProfile, setIsEditingProfile] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [originalEmail, setOriginalEmail] = useState('')

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const { data: customer, isLoading } = useQuery<Customer>({
    queryKey: ['customer', user?.customer_id],
    queryFn: async () => {
      if (!user?.customer_id) throw new Error('No customer ID')
      const response = await api.get(`/customers/${user.customer_id}`)
      return response.data
    },
    enabled: !!user?.customer_id,
  })

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors, isDirty },
  } = useForm<ProfileFormData>({
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
      // Use /auth/me endpoint for proper email verification flow
      const response = await api.put('/auth/me', data)
      return response.data
    },
    onSuccess: (data) => {
      // Handle new response format with user object wrapped
      const responseUser = data.user || data
      const isVerificationPending = data.email_verification_pending || false
      
      // Always update auth store and invalidate queries - other fields may have been updated
      setUser(responseUser)
      queryClient.invalidateQueries({ queryKey: ['customer'] })
      queryClient.invalidateQueries({ queryKey: ['user'] })
      
      if (isVerificationPending) {
        toast.success('Verification email sent! Check your new email to confirm.')
        setSuccessMessage(data.message || 'Profile updated. Please check your new email to confirm the email change.')
        setIsEditingProfile(false)
        setValue('password', '')
        setTimeout(() => setSuccessMessage(null), 8000)
      } else {
        toast.success('Profile updated successfully!')
        setSuccessMessage('Profile updated successfully!')
        setIsEditingProfile(false)
        setTimeout(() => setSuccessMessage(null), 3000)
      }
    },
    onError: (error: any) => {
      const errorMsg = error.response?.data?.detail || 'Failed to update profile'
      toast.error(errorMsg)
    },
  })

  const onSubmit = (data: ProfileFormData) => {
    const isEmailChanging = data.email !== originalEmail
    
    // If email is changing, password is required
    if (isEmailChanging && !data.password) {
      toast.error('Password is required to change your email address')
      return
    }
    
    updateMutation.mutate(data)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
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

  const inputClasses = (fieldName: keyof ProfileFormData) => {
    const base = "w-full px-4 py-3 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors"
    return errors[fieldName]
      ? `${base} border-red-500 focus:ring-red-500`
      : `${base} border-white/20 focus:ring-amber-500 focus:border-amber-500`
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Profile Settings</h1>
        <p className="text-gray-400 mt-1">Update your personal information</p>
      </div>

      {successMessage && (
        <div className="mb-6 flex items-center gap-3 bg-green-500/20 border border-green-500/30 text-green-400 px-4 py-3 rounded-lg">
          <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          <span className="text-sm">{successMessage}</span>
        </div>
      )}

      {/* Two column layout on desktop */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Personal Information */}
        <div className="bg-white/5 rounded-xl p-6 border border-white/10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Personal Information</h2>
            {!isEditingProfile && (
              <button
                onClick={() => setIsEditingProfile(true)}
                className="px-4 py-2 text-sm bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition-colors flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536M9 11l6.232-6.232a2 2 0 112.828 2.828L11.828 13.828A4 4 0 019 15H7v-2a4 4 0 011.172-2.828z" />
                </svg>
                Edit
              </button>
            )}
          </div>

        {updateMutation.isError && (
          <div className="mb-4 flex items-center gap-3 bg-red-500/20 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg">
            <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <span className="text-sm">{(updateMutation.error as any)?.response?.data?.detail || 'Failed to update profile'}</span>
          </div>
        )}

        {!isEditingProfile ? (
          <div className="space-y-4">
            <div>
              <div className="text-xs text-gray-400 mb-1">Name</div>
              <div className="text-white font-medium">{customer.first_name} {customer.last_name}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">Email</div>
              <div className="text-white font-medium">{customer.email}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">Phone</div>
              <div className="text-white font-medium">{customer.phone || 'Not provided'}</div>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">
                First Name
              </label>
              <input
                {...register('first_name')}
                type="text"
                className={inputClasses('first_name')}
                placeholder="John"
              />
              {errors.first_name && (
                <p className="mt-1 text-sm text-red-400">{errors.first_name.message}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">
                Last Name
              </label>
              <input
                {...register('last_name')}
                type="text"
                className={inputClasses('last_name')}
                placeholder="Doe"
              />
              {errors.last_name && (
                <p className="mt-1 text-sm text-red-400">{errors.last_name.message}</p>
              )}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Email Address
            </label>
            <input
              {...register('email')}
              type="email"
              className={inputClasses('email')}
              placeholder="you@example.com"
            />
            {errors.email && (
              <p className="mt-1 text-sm text-red-400">{errors.email.message}</p>
            )}
            <p className="mt-1 text-xs text-gray-500">This is your login email</p>
            {currentEmailValue !== originalEmail && (
              <div className="mt-2 bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
                <p className="text-blue-400 text-xs">
                  📧 Changing email requires verification. You'll receive a confirmation link at the new address.
                </p>
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Phone Number
            </label>
            <input
              {...register('phone')}
              type="tel"
              className={inputClasses('phone')}
              placeholder="(555) 123-4567"
              onChange={(e) => setValue('phone', formatUSPhone(e.target.value))}
            />
            {errors.phone && (
              <p className="mt-1 text-sm text-red-400">{errors.phone.message}</p>
            )}
          </div>

          {/* Password field - required when changing email */}
          {currentEmailValue !== originalEmail && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">
                Confirm Password
              </label>
              <div className="relative">
                <input
                  {...register('password')}
                  type={showPassword ? 'text' : 'password'}
                  className={inputClasses('password')}
                  placeholder="Enter your current password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                >
                  {showPassword ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
              {errors.password && (
                <p className="mt-1 text-sm text-red-400">{errors.password.message}</p>
              )}
              <p className="mt-1 text-xs text-amber-400">
                🔒 Password required to confirm email change
              </p>
            </div>
          )}

          <div className="pt-4 flex gap-3">
            <button
              type="button"
              onClick={() => {
                setIsEditingProfile(false)
                reset({
                  first_name: customer.first_name,
                  last_name: customer.last_name,
                  email: customer.email,
                  phone: customer.phone || '',
                  password: '',
                })
              }}
              className="flex-1 sm:flex-none px-6 py-3 bg-gray-700 hover:bg-gray-600 text-white font-medium rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!isDirty || updateMutation.isPending}
              className="flex-1 sm:flex-none px-6 py-3 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {updateMutation.isPending ? (
                <>
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </button>
          </div>
        </form>
        )}

        {/* Collapsible Password Change */}
        <CollapsiblePasswordChange />
        </div>

        {/* Right column: Payment Methods + Vehicles stacked */}
        <div className="space-y-6">
          <PaymentMethodsCard />
          <VehiclesCard />
        </div>
      </div>

      {/* Logout Section */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10 max-w-md">
        <h2 className="text-lg font-semibold text-white mb-2">Sign Out</h2>
        <p className="text-gray-400 text-sm mb-4">
          Sign out of your account on this device.
        </p>
        <button
          onClick={handleLogout}
          className="px-6 py-2.5 bg-red-600/20 hover:bg-red-600/30 border border-red-500/30 text-red-400 font-medium rounded-lg transition-colors"
        >
          Logout
        </button>
      </div>
    </div>
  )
}
