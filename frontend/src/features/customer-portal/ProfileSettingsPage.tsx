import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../../stores/authStore'
import api from '../../lib/api'
import { Customer } from '../../types'
import PaymentMethodsCard from './PaymentMethodsCard'
import VehiclesCard from './VehiclesCard'

const profileSchema = z.object({
  first_name: z.string().min(1, 'First name is required').min(2, 'Min 2 characters'),
  last_name: z.string().min(1, 'Last name is required').min(2, 'Min 2 characters'),
  email: z.string().min(1, 'Email is required').email('Invalid email'),
  phone: z.string().optional().refine((val) => !val || /^[\d\s\-\(\)\+]{10,}$/.test(val), {
    message: 'Invalid phone number',
  }),
})

type ProfileFormData = z.infer<typeof profileSchema>

export default function ProfileSettingsPage() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

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
    formState: { errors, isDirty },
  } = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
  })

  useEffect(() => {
    if (customer) {
      reset({
        first_name: customer.first_name,
        last_name: customer.last_name,
        email: customer.email,
        phone: customer.phone || '',
      })
    }
  }, [customer, reset])

  const updateMutation = useMutation({
    mutationFn: async (data: ProfileFormData) => {
      const response = await api.put(`/customers/${user?.customer_id}`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customer'] })
      setSuccessMessage('Profile updated successfully!')
      setTimeout(() => setSuccessMessage(null), 3000)
    },
  })

  const onSubmit = (data: ProfileFormData) => {
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

      {/* Two column layout on desktop */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Personal Information */}
        <div className="bg-white/5 rounded-xl p-6 border border-white/10">
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
            <p className="mt-1 text-xs text-gray-500">
              Note: This updates your contact email. Login email remains unchanged.
            </p>
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
