import React, { useMemo, useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { User, MechanicWorkItem, RepairOrderStatus, RepairOrder } from '@/types'
import { useAuthStore } from '@/stores/authStore'
import { formatUSPhone, isValidUSPhone } from '@/utils/phone'
import { generateMechanicPassword } from '@/utils/password'
import MapboxAddressInput from '@/components/MapboxAddressInput'
import { Eye, EyeOff } from 'lucide-react'
import SlidePanel from '@/components/SlidePanel'
import ViewToggle from '@/components/ViewToggle'
import SearchAddBar from '@/components/SearchAddBar'
import { useViewPreference } from '@/hooks/useViewPreference'

const mechanicSchema = z.object({
  first_name: z.string().min(1, 'First name is required'),
  last_name: z.string().min(1, 'Last name is required'),
  email: z.string().email('Valid email required'),
  address: z.string().optional(),
  phone: z.string().optional().refine((val) => isValidUSPhone(val), {
    message: 'Invalid phone number',
  }),
  password: z
    .string()
    .optional()
    .refine(
      (val) => {
        if (!val) return true
        return (
          val.length >= 8 &&
          /[A-Z]/.test(val) &&
          /[a-z]/.test(val) &&
          /[0-9]/.test(val)
        )
      },
      {
        message: 'Must be 8+ chars with upper, lower, number',
      }
    ),
})

type MechanicFormData = z.infer<typeof mechanicSchema>
type MechanicWithCounts = User & { assigned_count?: number; in_progress_count?: number }

const formatStatus = (status?: RepairOrderStatus | string | null) =>
  status ? status.replace(/_/g, ' ') : ''

export default function MechanicsPage() {
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const [isAdding, setIsAdding] = useState(false)
  const [expandedMechanicId, setExpandedMechanicId] = useState<string | null>(null)
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
  const [selectedWorkItem, setSelectedWorkItem] = useState<MechanicWorkItem | null>(null)
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const [viewMode, setViewMode] = useViewPreference('mechanics')
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 640 : false
  )
  const [search, setSearch] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [editingMechanic, setEditingMechanic] = useState<MechanicWithCounts | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const { data: mechanics, isLoading } = useQuery<MechanicWithCounts[]>({
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
    setError,
    watch,
    formState: { errors },
  } = useForm<MechanicFormData>({
    resolver: zodResolver(mechanicSchema),
    defaultValues: {
      first_name: '',
      last_name: '',
      email: '',
      address: '',
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
      setFormError(null)
      reset()
      setIsAdding(false)
      queryClient.invalidateQueries({ queryKey: ['mechanic-users'] })
      queryClient.invalidateQueries({ queryKey: ['mechanics'] }) // refresh assignment dropdowns that use dashboard stats
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || 'Failed to add mechanic'
      setFormError(Array.isArray(detail) ? detail.join(', ') : detail)
    },
  })

  const updateMechanicMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<MechanicFormData> }) => {
      const response = await api.put(`/mechanics/${id}`, data)
      return response.data
    },
    onSuccess: () => {
      setFormError(null)
      reset()
      setIsAdding(false)
      setEditingMechanic(null)
      queryClient.invalidateQueries({ queryKey: ['mechanic-users'] })
      queryClient.invalidateQueries({ queryKey: ['mechanics'] })
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || 'Failed to update mechanic'
      setFormError(Array.isArray(detail) ? detail.join(', ') : detail)
    },
  })

  const mechanicRows = useMemo(() => mechanics || [], [mechanics])
  const filteredMechanics = useMemo(() => {
    if (!search.trim()) return mechanicRows
    const query = search.toLowerCase().trim()
    return mechanicRows.filter((mechanic) => {
      const fullName = `${mechanic.first_name} ${mechanic.last_name}`.toLowerCase()
      return (
        fullName.includes(query) ||
        (mechanic.email || '').toLowerCase().includes(query) ||
        (mechanic.phone || '').toLowerCase().includes(query) ||
        (mechanic.address || '').toLowerCase().includes(query)
      )
    })
  }, [mechanicRows, search])

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

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handleResize = () => setIsMobile(window.innerWidth < 640)
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const activeViewMode = isMobile ? 'cards' : viewMode

  useEffect(() => {
    if (expandedMechanicId && !filteredMechanics.some((m) => m.id === expandedMechanicId)) {
      setExpandedMechanicId(null)
    }
  }, [expandedMechanicId, filteredMechanics])

  const statusBadge = (isActive: boolean) =>
    isActive
      ? 'bg-green-500/15 text-green-400 border border-green-500/30'
      : 'bg-gray-500/15 text-gray-300 border border-gray-500/30'

  const handleStartAdd = () => {
    setIsAdding(true)
    setEditingMechanic(null)
    setFormError(null)
    reset({
      first_name: '',
      last_name: '',
      email: '',
      address: '',
      phone: '',
      password: '',
    })
  }
  const handleCloseDrawer = () => {
    setIsAdding(false)
    setEditingMechanic(null)
    setFormError(null)
    reset()
  }

  const watchedFirstName = watch('first_name')
  const watchedPhone = watch('phone')
  const suggestedPassword = useMemo(() => {
    const digits = (watchedPhone || '').replace(/\D/g, '')
    if (!watchedFirstName.trim() || digits.length < 4) return ''
    return generateMechanicPassword(watchedFirstName, watchedPhone || '')
  }, [watchedFirstName, watchedPhone])

  useEffect(() => {
    if (editingMechanic) {
      setIsAdding(true)
      setFormError(null)
      reset({
        first_name: editingMechanic.first_name || '',
        last_name: editingMechanic.last_name || '',
        email: editingMechanic.email || '',
        address: editingMechanic.address || '',
        phone: editingMechanic.phone || '',
        password: '',
      })
      setShowPassword(false)
    }
  }, [editingMechanic, reset])

  const onSubmit = (data: MechanicFormData) => {
    setFormError(null)
    const normalizedAddress = data.address?.trim() || undefined
    if (editingMechanic) {
      const payload: Partial<MechanicFormData> = {
        first_name: data.first_name,
        last_name: data.last_name,
        email: data.email,
        phone: data.phone || '',
        address: normalizedAddress,
      }
      if (data.password) {
        payload.password = data.password
      }
      updateMechanicMutation.mutate({ id: editingMechanic.id, data: payload })
    } else {
      if (!data.password) {
        setError('password', { type: 'manual', message: 'Password is required' })
        return
      }
      createMechanicMutation.mutate({ ...data, address: normalizedAddress, password: data.password })
    }
  }

  useEffect(() => {
    if (editingMechanic) {
      setIsAdding(true)
      reset({
        first_name: editingMechanic.first_name || '',
        last_name: editingMechanic.last_name || '',
        email: editingMechanic.email || '',
        phone: editingMechanic.phone || '',
        address: '',
        password: '',
      })
      setShowPassword(false)
    }
  }, [editingMechanic, reset])

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
      <SearchAddBar
        value={search}
        onChange={setSearch}
        placeholder="Search mechanics by name, email, phone, or address..."
        onAdd={handleStartAdd}
        addLabel="Add mechanic"
        addLabelMobile="Add"
        className="mb-4"
        inputWidthClass="sm:min-w-[320px] md:max-w-xl"
      />
      <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
        {isLoading ? (
          <div className="text-gray-400 text-sm p-6">Loading mechanics...</div>
        ) : mechanicRows.length === 0 ? (
          <div className="text-gray-400 text-sm p-6">No mechanics yet. Use Add mechanic to get started.</div>
        ) : filteredMechanics.length === 0 ? (
          <div className="text-gray-400 text-sm p-6">No mechanics match your search.</div>
        ) : activeViewMode === 'list' ? (
          <>
            <div className="hidden sm:flex items-center justify-start px-4 py-3 border-b border-white/10">
              <ViewToggle value={activeViewMode} onChange={setViewMode} />
            </div>
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
                {filteredMechanics.map((mechanic) => (
                  <React.Fragment key={mechanic.id}>
                    <tr className="hover:bg-white/5 transition-colors">
                      <td className="px-4 py-3 font-medium">
                        <div className="flex flex-col gap-1">
                          <span>{mechanic.first_name} {mechanic.last_name}</span>
                          <button
                            type="button"
                            onClick={() => setEditingMechanic(mechanic)}
                            className="text-xs font-semibold text-amber-200 hover:text-white text-left"
                          >
                            Edit
                          </button>
                        </div>
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
                                          {formatStatus(item.status)}
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
          </>
        ) : (
          <>
            <div className="hidden sm:flex items-center justify-start px-4 py-3 border-b border-white/10">
              <ViewToggle value={activeViewMode} onChange={setViewMode} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
              {filteredMechanics.map((mechanic) => {
                const inProgress = mechanic.assigned_count ? Math.min(mechanic.in_progress_count || 0, mechanic.assigned_count) : mechanic.in_progress_count || 0
                const assigned = mechanic.assigned_count || 0
                const load = assigned > 0 ? Math.min((inProgress / assigned) * 100, 100) : 0
                return (
                  <div key={mechanic.id} className="bg-white/10 border border-white/15 rounded-xl p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs uppercase text-gray-400">{mechanic.email}</p>
                        <h3 className="text-lg font-semibold text-white">{mechanic.first_name} {mechanic.last_name}</h3>
                        <p className="text-xs text-gray-400">{mechanic.phone || 'No phone'}</p>
                      </div>
                      <span className={`px-2 py-1 rounded-full text-xs font-semibold ${statusBadge(mechanic.is_active)}`}>
                        {mechanic.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <div className="text-sm text-gray-200">In progress: {inProgress}/{assigned || '—'}</div>
                    <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                      <div className="h-full bg-amber-500" style={{ width: `${load}%` }} />
                    </div>
                    <div className="flex items-center justify-between text-xs text-gray-400 flex-wrap gap-2">
                      <span>Work: {assigned} assigned</span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setEditingMechanic(mechanic)}
                          className="font-semibold text-white hover:text-amber-200"
                        >
                          Edit
                        </button>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setExpandedMechanicId(mechanic.id)
                          setIsDetailOpen(false)
                        }}
                        className="px-3 py-2 text-sm font-medium text-amber-200 bg-amber-500/10 border border-amber-400/40 rounded-lg hover:bg-amber-500/20 transition"
                      >
                        View work
                      </button>
                      <button
                        type="button"
                        onClick={() => setExpandedMechanicId((prev) => (prev === mechanic.id ? null : mechanic.id))}
                        className="px-3 py-2 text-sm font-medium text-white bg-white/10 border border-white/20 rounded-lg hover:bg-white/20 transition"
                      >
                        {expandedMechanicId === mechanic.id ? 'Hide' : 'Select'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
            {expandedMechanicId && (
              <div className="border-t border-white/10 bg-white/5 p-4">
                <h3 className="text-sm font-semibold text-white mb-2">
                  Work for {filteredMechanics.find((m) => m.id === expandedMechanicId)?.first_name}{' '}
                  {filteredMechanics.find((m) => m.id === expandedMechanicId)?.last_name}
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
                              {formatStatus(item.status)}
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
            )}
          </>
        )}
      </div>

      {isAdding && (
        <div
          className={`fixed inset-0 z-50 transition ${isAdding ? 'pointer-events-auto' : 'pointer-events-none'}`}
          aria-hidden={!isAdding}
        >
          <div
            className={`absolute inset-0 bg-black/50 transition-opacity ${isAdding ? 'opacity-100' : 'opacity-0'}`}
            onClick={handleCloseDrawer}
          />
          <aside
            className={`absolute top-0 right-0 h-full w-full sm:w-[520px] bg-white/95 backdrop-blur border-l border-gray-200 shadow-xl transform transition-transform ${
              isAdding ? 'translate-x-0' : 'translate-x-full'
            }`}
            role="dialog"
            aria-label={editingMechanic ? 'Edit mechanic' : 'Add mechanic'}
          >
            <form onSubmit={handleSubmit(onSubmit)} className="h-full flex flex-col">
              <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase text-gray-500 font-semibold">
                    {editingMechanic ? 'Edit mechanic' : 'Add mechanic'}
                  </p>
                  <p className="text-lg font-semibold text-slate-800">
                    {editingMechanic ? `${editingMechanic.first_name} ${editingMechanic.last_name}` : 'Onboard a mechanic'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleCloseDrawer}
                  className="p-2 text-gray-500 hover:text-amber-600 rounded-full hover:bg-amber-50"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="p-5 space-y-4 overflow-y-auto flex-1">
                {formError && <p className="text-sm text-red-600">{formError}</p>}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">First Name</label>
                    <input
                      {...register('first_name')}
                      type="text"
                      className={`w-full px-4 py-3 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                        errors.first_name ? 'border-red-500 focus:ring-red-500' : 'border-gray-200 focus:ring-amber-500'
                      }`}
                      placeholder="Alex"
                    />
                    {errors.first_name && (
                      <p className="mt-1 text-sm text-red-600">{errors.first_name.message}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Last Name</label>
                    <input
                      {...register('last_name')}
                      type="text"
                      className={`w-full px-4 py-3 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                        errors.last_name ? 'border-red-500 focus:ring-red-500' : 'border-gray-200 focus:ring-amber-500'
                      }`}
                      placeholder="Rivera"
                    />
                    {errors.last_name && (
                      <p className="mt-1 text-sm text-red-600">{errors.last_name.message}</p>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Email</label>
                    <input
                      {...register('email')}
                      type="email"
                      className={`w-full px-4 py-3 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                        errors.email ? 'border-red-500 focus:ring-red-500' : 'border-gray-200 focus:ring-amber-500'
                      }`}
                      placeholder="mechanic@truckpitstop.com"
                    />
                    {errors.email && (
                      <p className="mt-1 text-sm text-red-600">{errors.email.message}</p>
                    )}
                  </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Phone</label>
                  <input
                  {...register('phone', {
                    onChange: (e) => setValue('phone', formatUSPhone(e.target.value)),
                    })}
                    type="tel"
                      className={`w-full px-4 py-3 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                        errors.phone ? 'border-red-500 focus:ring-red-500' : 'border-gray-200 focus:ring-amber-500'
                      }`}
                      placeholder="(555) 222-1111"
                    />
                    {errors.phone && (
                      <p className="mt-1 text-sm text-red-600">{errors.phone.message}</p>
                    )}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Address (optional)</label>
                  <MapboxAddressInput
                    {...register('address')}
                    onAddressSelect={({ formatted }) => setValue('address', formatted || '')}
                    className={`w-full px-4 py-3 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                      errors.address ? 'border-red-500 focus:ring-red-500' : 'border-gray-200 focus:ring-amber-500'
                    }`}
                    placeholder="123 Main St, City"
                  />
                  {errors.address && <p className="mt-1 text-sm text-red-600">{errors.address.message}</p>}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Temporary Password</label>
                  <div className="relative">
                    <input
                      {...register('password')}
                      type={showPassword ? 'text' : 'password'}
                      className={`w-full pr-11 pl-4 py-3 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                        errors.password ? 'border-red-500 focus:ring-red-500' : 'border-gray-200 focus:ring-amber-500'
                      }`}
                      placeholder="At least 8 chars, 1 upper, 1 number"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((prev) => !prev)}
                      className="absolute inset-y-0 right-2 px-2 flex items-center text-gray-500 hover:text-amber-600"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  {editingMechanic ? (
                    <div className="flex flex-wrap items-center gap-2 mt-2">
                      <p className="text-xs text-gray-500 mb-0">Leave blank to keep current password</p>
                      <button
                        type="button"
                        onClick={() =>
                          setValue(
                            'password',
                            suggestedPassword || generateMechanicPassword(editingMechanic.first_name || '', editingMechanic.phone || ''),
                            { shouldValidate: true }
                          )
                        }
                        disabled={!suggestedPassword && !(editingMechanic.first_name || editingMechanic.phone)}
                        className="text-xs font-semibold text-amber-700 hover:text-amber-900 disabled:text-gray-400 disabled:hover:text-gray-400"
                      >
                        {suggestedPassword ? `or reset to ${suggestedPassword}` : 'Reset to suggested'}
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mt-2">
                      <p className="text-xs text-gray-500">First name + last 4 of phone.</p>
                      <div className="flex items-center gap-3">
                        {suggestedPassword ? (
                          <button
                            type="button"
                            onClick={() => setValue('password', suggestedPassword, { shouldValidate: true })}
                            className="text-xs font-semibold text-amber-700 hover:text-amber-900"
                          >
                            Use {suggestedPassword}
                          </button>
                        ) : (
                          <span className="text-xs text-gray-400">Add name & phone</span>
                        )}
                        <button
                          type="button"
                          onClick={() => setValue('password', '', { shouldValidate: true })}
                          className="text-xs font-semibold text-gray-600 hover:text-gray-800"
                        >
                          Clear / custom
                        </button>
                      </div>
                    </div>
                  )}
                  {errors.password && (
                    <p className="mt-1 text-sm text-red-600">{errors.password.message}</p>
                  )}
                </div>
              </div>

              <div className="px-5 py-4 border-t border-gray-200 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={handleCloseDrawer}
                  className="px-4 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMechanicMutation.isPending || updateMechanicMutation.isPending}
                  className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-70"
                >
                  {(createMechanicMutation.isPending || updateMechanicMutation.isPending) && (
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                  )}
                  {createMechanicMutation.isPending || updateMechanicMutation.isPending
                    ? 'Saving...'
                    : editingMechanic
                    ? 'Update mechanic'
                    : 'Add mechanic'}
                </button>
              </div>
            </form>
          </aside>
        </div>
      )}
        </>
      )}
    </div>

      {/* Slide-in detail drawer */}
      <SlidePanel
        isOpen={isDetailOpen}
        onClose={() => setIsDetailOpen(false)}
        title={orderDetail?.order_number || selectedWorkItem?.order_number || 'Loading...'}
        subtitle="Repair Order"
        headerVariant="minimal"
        width="max-w-md"
      >
        <div className="p-4 space-y-3 text-sm text-gray-700">
          {!orderDetail && !selectedWorkItem ? (
            <p className="text-gray-500">Loading...</p>
          ) : (
            <>
              {orderDetail ? (
                <>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-gray-800">Status</span>
                    <span className="px-2 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700 capitalize">
                      {formatStatus(orderDetail.status)}
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
                      {formatStatus(selectedWorkItem?.status) || 'Unknown'}
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
      </SlidePanel>
    </>
  )
}
