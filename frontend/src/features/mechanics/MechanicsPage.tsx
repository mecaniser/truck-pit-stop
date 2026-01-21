import React, { useMemo, useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { User, MechanicWorkItem, RepairOrderStatus, RepairOrder } from '@/types'
import { useAuthStore } from '@/stores/authStore'
import { formatUSPhone, isValidUSPhone } from '@/utils/phone'

const mechanicSchema = z.object({
  first_name: z.string().min(1, 'First name is required'),
  last_name: z.string().min(1, 'Last name is required'),
  email: z.string().email('Valid email required'),
  phone: z.string().optional().refine((val) => isValidUSPhone(val), {
    message: 'Invalid phone number',
  }),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Must contain uppercase letter')
    .regex(/[a-z]/, 'Must contain lowercase letter')
    .regex(/[0-9]/, 'Must contain a number'),
})

type MechanicFormData = z.infer<typeof mechanicSchema>

export default function MechanicsPage() {
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const [isAdding, setIsAdding] = useState(false)
  const [expandedMechanicId, setExpandedMechanicId] = useState<string | null>(null)
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
  const [selectedWorkItem, setSelectedWorkItem] = useState<MechanicWorkItem | null>(null)
  const [isDetailOpen, setIsDetailOpen] = useState(false)

  const { data: mechanics, isLoading } = useQuery<User[]>({
    queryKey: ['mechanic-users'],
    queryFn: async () => {
      const response = await api.get('/mechanics')
      return response.data
    },
  })

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors },
  } = useForm<MechanicFormData>({
    resolver: zodResolver(mechanicSchema),
    defaultValues: {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      password: '',
    },
  })

  const createMechanicMutation = useMutation({
    mutationFn: async (data: MechanicFormData) => {
      const response = await api.post('/mechanics', data)
      return response.data
    },
    onSuccess: () => {
      reset()
      setIsAdding(false)
      queryClient.invalidateQueries({ queryKey: ['mechanic-users'] })
      queryClient.invalidateQueries({ queryKey: ['mechanics'] }) // refresh assignment dropdowns that use dashboard stats
    },
  })

  const mechanicRows = useMemo(() => mechanics || [], [mechanics])

  const { data: workItems, isLoading: workLoading } = useQuery<MechanicWorkItem[]>({
    queryKey: ['mechanic-work', expandedMechanicId],
    queryFn: async () => {
      const response = await api.get(`/mechanics/${expandedMechanicId}/work`)
      return response.data
    },
    enabled: !!expandedMechanicId,
  })

  const { data: orderDetail } = useQuery<RepairOrder>({
    queryKey: ['repair-order-detail', selectedOrderId],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${selectedOrderId}`)
      return response.data
    },
    enabled: !!selectedOrderId && isDetailOpen,
  })

  useEffect(() => {
    if (!isDetailOpen) {
      setSelectedOrderId(null)
      setSelectedWorkItem(null)
    }
  }, [isDetailOpen])

  const statusBadge = (isActive: boolean) =>
    isActive
      ? 'bg-green-500/15 text-green-400 border border-green-500/30'
      : 'bg-gray-500/15 text-gray-300 border border-gray-500/30'

  return (
    <>
    <div className="space-y-6">
      {user?.role !== 'garage_admin' && user?.role !== 'super_admin' ? (
        <div className="bg-white/5 rounded-xl p-6 border border-white/10">
          <h1 className="text-lg font-semibold text-white mb-2">Mechanics</h1>
          <p className="text-sm text-gray-400">Only garage admins can manage mechanics.</p>
        </div>
      ) : (
        <>
          <div className="bg-white/5 rounded-xl p-6 border border-white/10 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-xl font-semibold text-white">Mechanics</h1>
              <p className="text-sm text-gray-400">Track who can take jobs and onboard new mechanics quickly.</p>
            </div>
            <div className="px-3 py-1 rounded-full border border-amber-500/30 text-amber-300 text-xs font-semibold bg-amber-500/10">
              Admin view
            </div>
          </div>

      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Current Mechanics</h2>
          <span className="text-xs text-gray-400">Active status reflects account availability.</span>
        </div>
        {isLoading ? (
          <div className="text-gray-400 text-sm">Loading mechanics...</div>
        ) : mechanicRows.length === 0 ? (
          <div className="text-gray-400 text-sm">No mechanics yet. Add one below.</div>
        ) : (
          <div className="overflow-hidden border border-white/10 rounded-lg">
            <table className="min-w-full divide-y divide-white/10">
              <thead className="bg-white/5 text-left text-xs uppercase tracking-wide text-gray-400">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Phone</th>
                  <th className="px-4 py-3">Availability</th>
                  <th className="px-4 py-3 text-right">Work</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-sm text-gray-100">
                {mechanicRows.map((mechanic) => (
                  <React.Fragment key={mechanic.id}>
                    <tr className="hover:bg-white/5 transition-colors">
                      <td className="px-4 py-3 font-medium">
                        {mechanic.first_name} {mechanic.last_name}
                      </td>
                      <td className="px-4 py-3 text-gray-300">{mechanic.email}</td>
                      <td className="px-4 py-3 text-gray-300">{mechanic.phone || '—'}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${statusBadge(mechanic.is_active)}`}>
                          {mechanic.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => setExpandedMechanicId((prev) => (prev === mechanic.id ? null : mechanic.id))}
                          className="text-sm font-medium text-amber-300 hover:text-amber-200"
                        >
                          {expandedMechanicId === mechanic.id ? 'Hide work' : 'View work'}
                        </button>
                      </td>
                    </tr>
                    {expandedMechanicId === mechanic.id && (
                      <tr className="bg-white/5">
                        <td className="px-4 py-3" colSpan={5}>
                          <div className="space-y-3">
                            <h3 className="text-sm font-semibold text-white">
                              Work for {mechanic.first_name} {mechanic.last_name}
                            </h3>
                            {workLoading ? (
                              <p className="text-gray-400 text-sm">Loading work...</p>
                            ) : !workItems || workItems.length === 0 ? (
                              <p className="text-gray-400 text-sm">No work found for this mechanic.</p>
                            ) : (
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {workItems.map((item) => {
                                  const statusTone =
                                    item.status === 'in_progress'
                                      ? 'border-blue-400/40 bg-blue-500/10 text-blue-200'
                                      : item.status === 'completed' || item.status === 'paid'
                                      ? 'border-green-400/40 bg-green-500/10 text-green-200'
                                      : item.status === 'cancelled'
                                      ? 'border-gray-400/40 bg-gray-500/10 text-gray-200'
                                      : 'border-amber-400/40 bg-amber-500/10 text-amber-200'
                                  return (
                                <button
                                  key={item.id}
                                  type="button"
                                  onClick={() => {
                                    setSelectedWorkItem(item)
                                    setSelectedOrderId(item.id)
                                    setIsDetailOpen(true)
                                  }}
                                  className="border rounded-lg p-3 border-white/10 bg-white/5 text-left hover:border-amber-400/60 hover:bg-white/10 transition-colors"
                                >
                                  <div className="flex items-center justify-between text-sm font-semibold text-white">
                                    <span>{item.order_number}</span>
                                    <span className={`px-2 py-1 rounded-full text-xs font-bold ${statusTone}`}>
                                      {item.status.replaceAll('_', ' ')}
                                    </span>
                                  </div>
                                  <p className="text-xs text-gray-300 mt-1">{item.customer_name}</p>
                                  <p className="text-xs text-gray-400">{item.vehicle_info}</p>
                                  <p className="text-[11px] text-gray-500 mt-2">Updated: {new Date(item.updated_at).toLocaleString()}</p>
                                </button>
                              )
                            })}
                          </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <div className="flex items-start justify-between gap-3 mb-5">
          <div>
            <h2 className="text-lg font-semibold text-white">Onboard a Mechanic</h2>
            <p className="text-sm text-gray-400">Create a mechanic login so you can assign repair orders right away.</p>
          </div>
        </div>

        {!isAdding ? (
          <button
            type="button"
            onClick={() => setIsAdding(true)}
            className="px-5 py-3 bg-amber-600 hover:bg-amber-700 text-white font-medium rounded-lg transition-colors inline-flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add mechanic
          </button>
        ) : (
          <form onSubmit={handleSubmit((data) => createMechanicMutation.mutate(data))} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">First Name</label>
                <input
                  {...register('first_name')}
                  type="text"
                  className={`w-full px-4 py-3 bg-white/5 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                    errors.first_name ? 'border-red-500 focus:ring-red-500' : 'border-white/10 focus:ring-amber-500 focus:border-amber-500'
                  }`}
                  placeholder="Alex"
                />
                {errors.first_name && (
                  <p className="mt-1 text-sm text-red-400">{errors.first_name.message}</p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">Last Name</label>
                <input
                  {...register('last_name')}
                  type="text"
                  className={`w-full px-4 py-3 bg-white/5 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                    errors.last_name ? 'border-red-500 focus:ring-red-500' : 'border-white/10 focus:ring-amber-500 focus:border-amber-500'
                  }`}
                  placeholder="Rivera"
                />
                {errors.last_name && (
                  <p className="mt-1 text-sm text-red-400">{errors.last_name.message}</p>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">Email</label>
                <input
                  {...register('email')}
                  type="email"
                  className={`w-full px-4 py-3 bg-white/5 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                    errors.email ? 'border-red-500 focus:ring-red-500' : 'border-white/10 focus:ring-amber-500 focus:border-amber-500'
                  }`}
                  placeholder="mechanic@truckpitstop.com"
                />
                {errors.email && (
                  <p className="mt-1 text-sm text-red-400">{errors.email.message}</p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">Phone</label>
                <input
                {...register('phone', {
                  onChange: (e) => setValue('phone', formatUSPhone(e.target.value)),
                })}
                type="tel"
                  className={`w-full px-4 py-3 bg-white/5 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                    errors.phone ? 'border-red-500 focus:ring-red-500' : 'border-white/10 focus:ring-amber-500 focus:border-amber-500'
                  }`}
                  placeholder="(555) 222-1111"
                />
                {errors.phone && (
                  <p className="mt-1 text-sm text-red-400">{errors.phone.message}</p>
                )}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">Temporary Password</label>
              <input
                {...register('password')}
                type="password"
                className={`w-full px-4 py-3 bg-white/5 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                  errors.password ? 'border-red-500 focus:ring-red-500' : 'border-white/10 focus:ring-amber-500 focus:border-amber-500'
                }`}
                placeholder="At least 8 chars, 1 upper, 1 number"
              />
              {errors.password && (
                <p className="mt-1 text-sm text-red-400">{errors.password.message}</p>
              )}
            </div>

            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={createMechanicMutation.isPending}
                className="px-6 py-3 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors flex items-center gap-2"
              >
                {createMechanicMutation.isPending ? (
                  <>
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Creating...
                  </>
                ) : (
                  'Add Mechanic'
                )}
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsAdding(false)
                  reset()
                }}
                className="px-4 py-3 text-sm font-medium rounded-lg border border-white/15 text-gray-200 hover:bg-white/10 transition-colors"
              >
                Cancel
              </button>
            </div>
            <p className="text-xs text-gray-500">Share the login with your mechanic; they can change their password under Settings.</p>
          </form>
        )}
      </div>
        </>
      )}
    </div>

      {/* Slide-in detail drawer */}
      <div
        className={`fixed inset-0 z-40 transition ${isDetailOpen ? 'pointer-events-auto' : 'pointer-events-none'}`}
        aria-hidden={!isDetailOpen}
      >
        <div
          className={`absolute inset-0 bg-black/40 transition-opacity ${isDetailOpen ? 'opacity-100' : 'opacity-0'}`}
          onClick={() => setIsDetailOpen(false)}
        />
        <aside
          className={`absolute top-0 right-0 h-full w-full sm:w-[480px] bg-white/95 backdrop-blur border-l border-gray-200 shadow-xl transform transition-transform ${
            isDetailOpen ? 'translate-x-0' : 'translate-x-full'
          }`}
        >
          <div className="h-full flex flex-col">
            <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
              <div>
                <p className="text-xs uppercase text-gray-500 font-semibold">Repair Order</p>
                <p className="text-lg font-semibold text-slate-800">
                  {orderDetail?.order_number || selectedWorkItem?.order_number || 'Loading...'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsDetailOpen(false)}
                className="p-2 text-gray-500 hover:text-amber-600 rounded-full hover:bg-amber-50"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-4 space-y-3 overflow-y-auto text-sm text-gray-700 flex-1">
              {!orderDetail && !selectedWorkItem ? (
                <p className="text-gray-500">Loading...</p>
              ) : (
                <>
                  {orderDetail ? (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-gray-800">Status</span>
                        <span className="px-2 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700 capitalize">
                          {orderDetail.status.replaceAll('_', ' ')}
                        </span>
                      </div>
                      <div>
                        <p className="font-semibold text-gray-800">Description</p>
                        <p className="text-gray-600 mt-1">{orderDetail.description || 'No description'}</p>
                      </div>
                      <div>
                        <p className="font-semibold text-gray-800">Customer</p>
                        <p className="text-gray-600 mt-1">
                          {selectedWorkItem?.customer_name || 'Customer'}
                        </p>
                      </div>
                      <div>
                        <p className="font-semibold text-gray-800">Vehicle</p>
                        <p className="text-gray-600 mt-1">
                          {selectedWorkItem?.vehicle_info || 'Vehicle'}
                        </p>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <p className="text-xs uppercase text-gray-500">Total Parts</p>
                          <p className="font-semibold text-gray-800">${orderDetail.total_parts_cost}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase text-gray-500">Total Labor</p>
                          <p className="font-semibold text-gray-800">${orderDetail.total_labor_cost}</p>
                        </div>
                        <div className="col-span-2">
                          <p className="text-xs uppercase text-gray-500">Total</p>
                          <p className="font-semibold text-gray-900 text-lg">${orderDetail.total_cost}</p>
                        </div>
                      </div>
                      {orderDetail.internal_notes && (
                        <div>
                          <p className="font-semibold text-gray-800">Internal Notes</p>
                          <p className="text-gray-600 mt-1">{orderDetail.internal_notes}</p>
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-gray-800">Status</span>
                        <span className="px-2 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700 capitalize">
                          {selectedWorkItem?.status.replaceAll('_', ' ') || 'Unknown'}
                        </span>
                      </div>
                      <div>
                        <p className="font-semibold text-gray-800">Customer</p>
                        <p className="text-gray-600 mt-1">
                          {selectedWorkItem?.customer_name || 'Customer'}
                        </p>
                      </div>
                      <div>
                        <p className="font-semibold text-gray-800">Vehicle</p>
                        <p className="text-gray-600 mt-1">
                          {selectedWorkItem?.vehicle_info || 'Vehicle'}
                        </p>
                      </div>
                      <p className="text-gray-500">No additional details available.</p>
                    </>
                  )}
                </>
              )}
            </div>
          </div>
        </aside>
      </div>
    </>
  )
}
