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

type ProfileFormData = z.infer<typeof profileSchema>

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
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Profile Settings</h1>
        <p className="text-gray-400 mt-1">Manage your account settings</p>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Profile Information */}
        <div className="bg-white/5 rounded-xl p-6 border border-white/10">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-full bg-amber-500/20 flex items-center justify-center">
              <svg className="w-6 h-6 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">
                {user?.first_name} {user?.last_name}
              </h2>
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-400">{user?.email}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${roleBadge.color}`}>
                  {roleBadge.label}
                </span>
              </div>
            </div>
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

            <div className="pt-4">
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
            </div>
          </form>
        </div>

        {/* Account Actions */}
        <div className="space-y-6">
          {/* Account Info */}
          <div className="bg-white/5 rounded-xl p-6 border border-white/10">
            <h3 className="text-lg font-semibold text-white mb-4">Account Information</h3>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">Email</span>
                <span className="text-white">{user?.email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Role</span>
                <span className="text-white">{roleBadge.label}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Status</span>
                <span className={user?.is_active ? 'text-green-400' : 'text-red-400'}>
                  {user?.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
            </div>
          </div>

          {/* Sign Out */}
          <div className="bg-white/5 rounded-xl p-6 border border-white/10">
            <h3 className="text-lg font-semibold text-white mb-2">Sign Out</h3>
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
      </div>
    </div>
  )
}
