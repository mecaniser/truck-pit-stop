import React, { useMemo, useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { User, MechanicWorkItem, RepairOrderStatus, RepairOrder } from '@/types'
import { useAuthStore } from '@/stores/authStore'
import { useTheme } from '@/contexts/ThemeContext'
import { formatUSPhone, isValidUSPhone } from '@/utils/phone'
import { generateMechanicPassword } from '@/utils/password'
import { getPasswordValidationError } from '@/lib/passwordPolicy'
import MapboxAddressInput from '@/components/MapboxAddressInput'
import { Eye, EyeOff, Calendar, DollarSign, Check, X, Wrench, Clock } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import SlidePanel from '@/components/SlidePanel'
import ViewToggle from '@/components/ViewToggle'
import SearchAddBar from '@/components/SearchAddBar'
import { useViewPreference } from '@/hooks/useViewPreference'

// Parse selected services from internal_notes JSON
const parseServiceNotes = (notes?: string | null) => {
  if (!notes) return null
  try {
    const parsed = JSON.parse(notes)
    if (Array.isArray(parsed?.selected_services)) {
      return parsed.selected_services as { id: string; name: string; base_price: string }[]
    }
  } catch {
    // Not JSON or invalid format - return null (it's a regular note)
  }
  return null
}

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
    .superRefine((value, ctx) => {
      if (!value) return
      const validationError = getPasswordValidationError(value)
      if (validationError) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: validationError,
        })
      }
    }),
  core_hours_target_minutes_override: z
    .string()
    .optional()
    .refine((val) => {
      if (!val || !val.trim()) return true
      const n = Number(val)
      return Number.isInteger(n) && n >= 1 && n <= 1440
    }, { message: 'Core hours must be 1-1440 minutes' }),
  shift_start_local_override: z
    .string()
    .optional()
    .refine((val) => !val || !val.trim() || /^\d{2}:\d{2}$/.test(val), { message: 'Use HH:MM format' }),
  shift_end_local_override: z
    .string()
    .optional()
    .refine((val) => !val || !val.trim() || /^\d{2}:\d{2}$/.test(val), { message: 'Use HH:MM format' }),
})

type MechanicFormData = z.infer<typeof mechanicSchema>
type MechanicApiPayload = {
  first_name: string
  last_name: string
  email: string
  phone?: string
  address?: string
  password?: string
  core_hours_target_minutes_override?: number | null
  shift_start_local_override?: string | null
  shift_end_local_override?: string | null
}
type MechanicWithCounts = User & { 
  assigned_count?: number
  in_progress_count?: number
  available_points?: number
  total_earned?: number
  streak_days?: number
  pending_requests?: number
}

const formatStatus = (status?: RepairOrderStatus | string | null) =>
  status ? status.replace(/_/g, ' ') : ''

export default function MechanicsPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const { accentColors } = useTheme()
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

  // Pending PTO requests
  interface PTORequestItem {
    id: string
    mechanic_id: string
    mechanic_name: string
    request_type: string
    status: string
    pto_start_date: string | null
    pto_end_date: string | null
    pto_days: number | null
    points_requested: number
    cash_value: number | null
    mechanic_notes: string | null
    created_at: string
  }

  const { data: pendingRequests } = useQuery<PTORequestItem[]>({
    queryKey: ['pending-pto-requests'],
    queryFn: async () => {
      const response = await api.get('/mechanics/pto-requests/pending')
      return response.data
    },
  })

  const processRequestMutation = useMutation({
    mutationFn: async ({ requestId, action, notes }: { requestId: string; action: string; notes?: string }) => {
      const response = await api.post(`/mechanics/pto-requests/${requestId}/process`, { action, manager_notes: notes })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-pto-requests'] })
      queryClient.invalidateQueries({ queryKey: ['mechanic-users'] })
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
      core_hours_target_minutes_override: '',
      shift_start_local_override: '',
      shift_end_local_override: '',
    },
  })

  const createMechanicMutation = useMutation({
    mutationFn: async (data: MechanicApiPayload) => {
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
      const detail = err?.response?.data?.detail || 'Failed to add technician'
      setFormError(Array.isArray(detail) ? detail.join(', ') : detail)
    },
  })

  const updateMechanicMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<MechanicApiPayload> }) => {
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
      const detail = err?.response?.data?.detail || 'Failed to update technician'
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
      core_hours_target_minutes_override: '',
      shift_start_local_override: '',
      shift_end_local_override: '',
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
        core_hours_target_minutes_override: editingMechanic.core_hours_target_minutes_override?.toString() || '',
        shift_start_local_override: editingMechanic.shift_start_local_override || '',
        shift_end_local_override: editingMechanic.shift_end_local_override || '',
      })
      setShowPassword(false)
    }
  }, [editingMechanic, reset])

  const onSubmit = (data: MechanicFormData) => {
    setFormError(null)
    const normalizedAddress = data.address?.trim() || undefined
    const coreHoursOverride = data.core_hours_target_minutes_override?.trim()
      ? Number(data.core_hours_target_minutes_override.trim())
      : null
    const shiftStartOverride = data.shift_start_local_override?.trim() || null
    const shiftEndOverride = data.shift_end_local_override?.trim() || null
    if (editingMechanic) {
      const payload: Record<string, unknown> = {
        first_name: data.first_name,
        last_name: data.last_name,
        email: data.email,
        phone: data.phone || '',
        address: normalizedAddress,
        core_hours_target_minutes_override: coreHoursOverride,
        shift_start_local_override: shiftStartOverride,
        shift_end_local_override: shiftEndOverride,
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
      createMechanicMutation.mutate({
        ...data,
        address: normalizedAddress,
        password: data.password,
        core_hours_target_minutes_override: coreHoursOverride,
        shift_start_local_override: shiftStartOverride,
        shift_end_local_override: shiftEndOverride,
      })
    }
  }

  return (
    <>
    <div className="space-y-6">
      {user?.role !== 'garage_owner' && user?.role !== 'garage_admin' ? (
        <div className="bg-white/5 rounded-xl p-6 border border-white/10">
          <h1 className="text-lg font-semibold text-white mb-2">Technicians</h1>
          <p className="text-sm text-gray-400">Only garage admins can manage technicians.</p>
        </div>
      ) : (
        <>
      {/* Pending Requests Section */}
      {pendingRequests && pendingRequests.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 mb-4">
          <h3 className="text-amber-300 font-semibold mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-amber-400 rounded-full animate-pulse" />
            Pending Requests ({pendingRequests.length})
          </h3>
          <div className="space-y-3">
            {pendingRequests.map((req) => (
              <div key={req.id} className="bg-white/5 rounded-lg p-3 flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {req.request_type === 'pto' ? (
                      <Calendar className="w-4 h-4 text-blue-400 shrink-0" />
                    ) : (
                      <DollarSign className="w-4 h-4 text-green-400 shrink-0" />
                    )}
                    <span className="text-white font-medium truncate">{req.mechanic_name}</span>
                  </div>
                  <p className="text-sm text-gray-400 mt-1">
                    {req.request_type === 'pto' 
                      ? `${req.pto_days} day${req.pto_days !== 1 ? 's' : ''} PTO: ${new Date(req.pto_start_date!).toLocaleDateString()} - ${new Date(req.pto_end_date!).toLocaleDateString()}`
                      : `Cash out: $${req.cash_value?.toFixed(2)}`
                    }
                  </p>
                  <p className="text-xs text-gray-500">
                    {req.points_requested.toLocaleString()} points • {new Date(req.created_at).toLocaleDateString()}
                  </p>
                  {req.mechanic_notes && (
                    <p className="text-xs text-gray-400 italic mt-1">"{req.mechanic_notes}"</p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => processRequestMutation.mutate({ requestId: req.id, action: 'approve' })}
                    disabled={processRequestMutation.isPending}
                    className="p-2 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded-lg transition-colors"
                    title="Approve"
                  >
                    <Check className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => {
                      const notes = prompt('Reason for denial (optional):')
                      processRequestMutation.mutate({ requestId: req.id, action: 'deny', notes: notes || undefined })
                    }}
                    disabled={processRequestMutation.isPending}
                    className="p-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-colors"
                    title="Deny"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center gap-3 mb-4">
        <SearchAddBar
          value={search}
          onChange={setSearch}
          placeholder="Search technicians by name, email, phone, or address..."
          onAdd={handleStartAdd}
          addLabel="Add technician"
          addLabelMobile="Add"
          className="flex-1"
          inputWidthClass="sm:min-w-[320px] md:max-w-xl"
        />
        <button
          onClick={() => navigate('/dashboard/mechanics')}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-gray-200 text-sm font-medium transition-colors shrink-0"
        >
          <Clock className="w-4 h-4" />
          <span className="hidden sm:inline">Time Board</span>
        </button>
      </div>
      <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
        {isLoading ? (
          <div className="text-gray-400 text-sm p-6">Loading technicians...</div>
        ) : mechanicRows.length === 0 ? (
          <div className="text-gray-400 text-sm p-6">No technicians yet. Use Add technician to get started.</div>
        ) : filteredMechanics.length === 0 ? (
          <div className="text-gray-400 text-sm p-6">No technicians match your search.</div>
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
                            className="text-xs font-semibold hover:text-white text-left"
                            style={{ color: accentColors[400] }}
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
                          onClick={() => {
                            setIsDetailOpen(false)
                            setExpandedMechanicId((prev) => (prev === mechanic.id ? null : mechanic.id))
                          }}
                          className="text-sm font-medium hover:opacity-80"
                          style={{ color: accentColors[400] }}
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
                              <p className="text-gray-400 text-sm">No work found for this technician.</p>
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
                                      <p className="text-xs text-gray-300 mt-1">{item.vehicle_info}</p>
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
                  <div key={mechanic.id} className="bg-white/10 border border-white/15 rounded-xl p-4 flex flex-col">
                    {/* Card content - grows to fill space */}
                    <div className="flex-1 space-y-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-xs uppercase text-gray-400">{mechanic.email}</p>
                          <h3 className="text-lg font-semibold text-white">{mechanic.first_name} {mechanic.last_name}</h3>
                          <p className="text-xs text-gray-400">{mechanic.phone || 'No phone'}</p>
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          <span className={`px-2 py-1 rounded-full text-xs font-semibold ${statusBadge(mechanic.is_active)}`}>
                            {mechanic.is_active ? 'Active' : 'Inactive'}
                          </span>
                          {(mechanic.pending_requests || 0) > 0 && (
                            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                              {mechanic.pending_requests} request{mechanic.pending_requests !== 1 ? 's' : ''}
                            </span>
                          )}
                        </div>
                      </div>
                      
                      {/* Points Display */}
                      <div className="flex items-center justify-between bg-white/5 rounded-lg px-3 py-2">
                        <div className="flex items-center gap-2">
                          <span className="text-amber-400">⭐</span>
                          <span className="text-sm text-gray-300">Points</span>
                        </div>
                        <div className="text-right">
                          <span className="text-lg font-bold text-amber-400">{(mechanic.available_points || 0).toLocaleString()}</span>
                          <span className="text-xs text-gray-500 ml-1">available</span>
                        </div>
                      </div>
                      {(mechanic.streak_days || 0) > 0 && (
                        <div className="flex items-center gap-1 text-xs text-orange-400">
                          <span>🔥</span>
                          <span>{mechanic.streak_days} day streak</span>
                        </div>
                      )}
                      
                      <div className="text-sm text-gray-200">In progress: {inProgress}/{assigned || '—'}</div>
                      <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                        <div className="h-full" style={{ backgroundColor: accentColors[500], width: `${load}%` }} />
                      </div>
                      <div className="text-xs text-gray-400">
                        Work: {assigned} assigned
                      </div>
                    </div>
                    
                    {/* Action buttons - always at bottom */}
                    <div className="flex gap-2 mt-4 pt-3 border-t border-white/10">
                      <button
                        type="button"
                        onClick={() => {
                          setIsDetailOpen(false)
                          setExpandedMechanicId((prev) => (prev === mechanic.id ? null : mechanic.id))
                        }}
                        className="flex-1 px-3 py-2 text-sm font-medium rounded-lg transition"
                        style={{ 
                          color: accentColors[400], 
                          backgroundColor: `${accentColors[500]}1a`,
                          borderWidth: 1,
                          borderColor: `${accentColors[400]}66`
                        }}
                      >
                        {expandedMechanicId === mechanic.id ? 'Hide work' : 'View work'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingMechanic(mechanic)}
                        className="flex-1 px-3 py-2 text-sm font-medium text-white bg-white/10 border border-white/20 rounded-lg hover:bg-white/20 transition"
                      >
                        Edit
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
                  <p className="text-gray-400 text-sm">No work found for this technician.</p>
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
                          <p className="text-xs text-gray-300 mt-1">{item.vehicle_info}</p>
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
          className={`fixed inset-0 z-[60] transition ${isAdding ? 'pointer-events-auto' : 'pointer-events-none'}`}
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
            aria-label={editingMechanic ? 'Edit technician' : 'Add technician'}
          >
            <form onSubmit={handleSubmit(onSubmit)} className="h-full flex flex-col">
              <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase text-gray-500 font-semibold">
                    {editingMechanic ? 'Edit technician' : 'Add technician'}
                  </p>
                  <p className="text-lg font-semibold text-slate-800">
                    {editingMechanic ? `${editingMechanic.first_name} ${editingMechanic.last_name}` : 'Onboard a technician'}
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
                      placeholder="mechanic@dieselbridge.com"
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

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Core Minutes</label>
                    <input
                      {...register('core_hours_target_minutes_override')}
                      type="number"
                      min={1}
                      max={1440}
                      className={`w-full px-4 py-3 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                        errors.core_hours_target_minutes_override ? 'border-red-500 focus:ring-red-500' : 'border-gray-200 focus:ring-amber-500'
                      }`}
                      placeholder="480"
                    />
                    {errors.core_hours_target_minutes_override && (
                      <p className="mt-1 text-sm text-red-600">{errors.core_hours_target_minutes_override.message}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Shift Start (HH:MM)</label>
                    <input
                      {...register('shift_start_local_override')}
                      type="text"
                      className={`w-full px-4 py-3 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                        errors.shift_start_local_override ? 'border-red-500 focus:ring-red-500' : 'border-gray-200 focus:ring-amber-500'
                      }`}
                      placeholder="08:00"
                    />
                    {errors.shift_start_local_override && (
                      <p className="mt-1 text-sm text-red-600">{errors.shift_start_local_override.message}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Shift End (HH:MM)</label>
                    <input
                      {...register('shift_end_local_override')}
                      type="text"
                      className={`w-full px-4 py-3 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                        errors.shift_end_local_override ? 'border-red-500 focus:ring-red-500' : 'border-gray-200 focus:ring-amber-500'
                      }`}
                      placeholder="18:00"
                    />
                    {errors.shift_end_local_override && (
                      <p className="mt-1 text-sm text-red-600">{errors.shift_end_local_override.message}</p>
                    )}
                  </div>
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
                      placeholder="At least 8 chars, upper/lower, number, special"
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
                      <p className="text-xs text-gray-500">First name + @ + last 4 of phone.</p>
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
                  className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-70"
                  style={{ backgroundColor: accentColors[600] }}
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
                    ? 'Update technician'
                    : 'Add technician'}
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
                    <p className="font-semibold text-gray-800">Vehicle</p>
                    <p className="text-gray-600 mt-1">
                      {selectedWorkItem?.vehicle_info || 'Vehicle'}
                    </p>
                  </div>
                  {(() => {
                    const services = parseServiceNotes(orderDetail.internal_notes)
                    const hasServices = services && services.length > 0
                    const serviceTotal = services?.reduce(
                      (sum, svc) => sum + (parseFloat(svc.base_price || '0') || 0),
                      0
                    ) || 0
                    const backendParts = parseFloat(orderDetail.total_parts_cost) || 0
                    const backendLabor = parseFloat(orderDetail.total_labor_cost) || 0
                    // Services = Labor, Parts = separate
                    const laborVal = hasServices ? serviceTotal : backendLabor
                    const totalVal = backendParts + laborVal

                    return (
                      <>
                        {/* Services (Labor) section */}
                        {hasServices && (
                          <div>
                            <p className="font-semibold text-gray-800 mb-2">Services (Labor)</p>
                            <div className="space-y-2">
                              {services.map((svc, idx) => (
                                <div key={idx} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
                                  <div className="flex items-center gap-2">
                                    <Wrench className="w-4 h-4 text-gray-400" />
                                    <span className="text-gray-700">{svc.name}</span>
                                  </div>
                                  <span className="font-medium text-gray-900">${parseFloat(svc.base_price || '0').toFixed(2)}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {/* Cost breakdown - always show parts + labor/services + total */}
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <p className="text-xs uppercase text-gray-500">Parts</p>
                            <p className="font-semibold text-blue-700">${backendParts.toFixed(2)}</p>
                          </div>
                          <div>
                            <p className="text-xs uppercase text-gray-500">{hasServices ? 'Services' : 'Labor'}</p>
                            <p className="font-semibold text-amber-700">${laborVal.toFixed(2)}</p>
                          </div>
                          <div className="col-span-2">
                            <p className="text-xs uppercase text-gray-500">Total</p>
                            <p className="font-semibold text-gray-900 text-lg">${totalVal.toFixed(2)}</p>
                          </div>
                        </div>
                        {/* Show internal notes if not JSON services */}
                        {!hasServices && orderDetail.internal_notes && (
                          <div>
                            <p className="font-semibold text-gray-800">Internal Notes</p>
                            <p className="text-gray-600 mt-1">{orderDetail.internal_notes}</p>
                          </div>
                        )}
                      </>
                    )
                  })()}
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
