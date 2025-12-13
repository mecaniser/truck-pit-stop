import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../../stores/authStore'
import api from '../../lib/api'

const profileSchema = z.object({
  first_name: z.string().min(1, 'First name is required').min(2, 'Min 2 characters'),
  last_name: z.string().min(1, 'Last name is required').min(2, 'Min 2 characters'),
  phone: z.string().optional().refine((val) => !val || /^[\d\s\-\(\)\+]{10,}$/.test(val), {
    message: 'Invalid phone number',
  }),
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

function CollapsiblePasswordChange() {
  const [isOpen, setIsOpen] = useState(false)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

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
      setSuccessMessage('Password changed successfully!')
      setTimeout(() => setSuccessMessage(null), 3000)
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

export default function AdminProfilePage() {
  const { user, logout, setUser } = useAuthStore()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
  })

  useEffect(() => {
    if (user) {
      reset({
        first_name: user.first_name || '',
        last_name: user.last_name || '',
        phone: user.phone || '',
      })
    }
  }, [user, reset])

  const updateMutation = useMutation({
    mutationFn: async (data: ProfileFormData) => {
      const response = await api.put('/auth/me', data)
      return response.data
    },
    onSuccess: (data) => {
      setUser(data)
      queryClient.invalidateQueries({ queryKey: ['user'] })
      setSuccessMessage('Profile updated successfully!')
      setTimeout(() => setSuccessMessage(null), 3000)
    },
  })

  const onSubmit = (data: ProfileFormData) => {
    updateMutation.mutate(data)
  }

  const inputClasses = (fieldName: keyof ProfileFormData) => {
    const base = "w-full px-4 py-3 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors"
    return errors[fieldName]
      ? `${base} border-red-500 focus:ring-red-500`
      : `${base} border-white/20 focus:ring-amber-500 focus:border-amber-500`
  }

  const getRoleBadge = () => {
    switch (user?.role) {
      case 'super_admin':
        return { label: 'Super Admin', color: 'bg-purple-500/20 text-purple-400 border-purple-500/30' }
      case 'garage_admin':
        return { label: 'Garage Admin', color: 'bg-amber-500/20 text-amber-400 border-amber-500/30' }
      case 'mechanic':
        return { label: 'Mechanic', color: 'bg-blue-500/20 text-blue-400 border-blue-500/30' }
      case 'receptionist':
        return { label: 'Receptionist', color: 'bg-green-500/20 text-green-400 border-green-500/30' }
      default:
        return { label: 'Staff', color: 'bg-gray-500/20 text-gray-400 border-gray-500/30' }
    }
  }

  const roleBadge = getRoleBadge()

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        {/* Header with avatar, name, email, role, status */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-amber-500/20 flex items-center justify-center">
              <svg className="w-7 h-7 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">
                {user?.first_name} {user?.last_name}
              </h1>
              <p className="text-sm text-gray-400">{user?.email}</p>
            </div>
          </div>
          <span className={`text-xs px-2.5 py-1 rounded-full border flex items-center gap-1.5 ${roleBadge.color}`}>
            {roleBadge.label}
            <span className={`w-1.5 h-1.5 rounded-full ${user?.is_active ? 'bg-green-400' : 'bg-red-400'}`} />
          </span>
        </div>

        {successMessage && (
          <div className="mb-6 flex items-center gap-3 bg-green-500/20 border border-green-500/30 text-green-400 px-4 py-3 rounded-lg">
            <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <span className="text-sm">{successMessage}</span>
          </div>
        )}

        {updateMutation.isError && (
          <div className="mb-6 flex items-center gap-3 bg-red-500/20 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg">
            <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <span className="text-sm">Failed to update profile. Please try again.</span>
          </div>
        )}

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
              Phone Number
            </label>
            <input
              {...register('phone')}
              type="tel"
              className={inputClasses('phone')}
              placeholder="(555) 123-4567"
            />
            {errors.phone && (
              <p className="mt-1 text-sm text-red-400">{errors.phone.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={!isDirty || updateMutation.isPending}
            className="w-full sm:w-auto px-6 py-3 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
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
        </form>

        {/* Collapsible Password Change */}
        <CollapsiblePasswordChange />

        {/* Sign Out */}
        <div className="border-t border-white/10 pt-5 mt-5 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-gray-300">Sign Out</h3>
            <p className="text-xs text-gray-500">End your session on this device</p>
          </div>
          <button
            onClick={handleLogout}
            className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 border border-red-500/30 text-red-400 text-sm font-medium rounded-lg transition-colors"
          >
            Logout
          </button>
        </div>
      </div>
    </div>
  )
}
