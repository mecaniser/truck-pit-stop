import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import api from '../../lib/api'
import { CheckCircle, Download, Settings, Trash2, Wrench } from 'lucide-react'
import SearchAddBar from '@/components/SearchAddBar'
import ViewToggle from '@/components/ViewToggle'
import { useViewPreference } from '@/hooks/useViewPreference'

interface Service {
  id: string
  category_id: string | null
  name: string
  description: string | null
  duration_minutes: number
  base_price: string
  icon: string | null
  sort_order: number
  is_active: boolean
  requires_vehicle: boolean
}

interface ServiceCategory {
  id: string
  name: string
  description: string | null
  icon: string | null
  sort_order: number
  is_active: boolean
}

const serviceSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  duration_minutes: z.coerce.number().min(5, 'Min 5 minutes'),
  base_price: z.coerce.number().min(0, 'Price must be positive'),
  icon: z.string().optional(),
  category_id: z.string().optional(),
  requires_vehicle: z.boolean(),
  is_active: z.boolean(),
})

type ServiceFormData = z.infer<typeof serviceSchema>

export default function ServicesManagementPage() {
  const queryClient = useQueryClient()
  const [editingService, setEditingService] = useState<Service | null>(null)
  const [isAddingNew, setIsAddingNew] = useState(false)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showMenu) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false)
        setShowClearConfirm(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showMenu])
  const [viewMode, setViewMode] = useViewPreference('services')
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 640 : false
  )
  const [searchQuery, setSearchQuery] = useState('')

  const formOpen = isAddingNew || !!editingService
  const iconOptions = ['🛠️', '🔧', '🧽', '🛢️', '🚗', '🚚', '🔋', '🧰', '⚙️', '✅']

  const { data: services, isLoading } = useQuery<Service[]>({
    queryKey: ['admin-services'],
    queryFn: async () => {
      const response = await api.get('/services?active_only=false')
      return response.data
    },
  })

  const { data: categories } = useQuery<ServiceCategory[]>({
    queryKey: ['service-categories'],
    queryFn: async () => {
      const response = await api.get('/services/categories')
      return response.data
    },
  })

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<ServiceFormData>({
    resolver: zodResolver(serviceSchema),
    defaultValues: {
      duration_minutes: 60,
      base_price: 0,
      requires_vehicle: true,
      is_active: true,
    },
  })
  const selectedIcon = watch('icon')

  const createMutation = useMutation({
    mutationFn: async (data: ServiceFormData) => {
      await api.post('/services', {
        ...data,
        category_id: data.category_id || null,
        description: data.description || null,
        icon: data.icon || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      setIsAddingNew(false)
      reset()
      setSuccessMessage('Service created successfully')
      setTimeout(() => setSuccessMessage(null), 3000)
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: ServiceFormData }) => {
      await api.put(`/services/${id}`, {
        ...data,
        category_id: data.category_id || null,
        description: data.description || null,
        icon: data.icon || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      setEditingService(null)
      reset()
      setSuccessMessage('Service updated successfully')
      setTimeout(() => setSuccessMessage(null), 3000)
    },
  })

  const preloadMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/services/preload')
      return response.data as { categories_added: number; services_added: number }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      queryClient.invalidateQueries({ queryKey: ['service-categories'] })
      const msg = data.services_added === 0
        ? 'Already up to date — no new services added'
        : `Loaded ${data.services_added} service${data.services_added !== 1 ? 's' : ''} across ${data.categories_added} categor${data.categories_added !== 1 ? 'ies' : 'y'}`
      setSuccessMessage(msg)
      setTimeout(() => setSuccessMessage(null), 4000)
    },
  })

  const clearMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/services/clear')
      return response.data as { categories_deleted: number; services_deleted: number }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      queryClient.invalidateQueries({ queryKey: ['service-categories'] })
      setShowClearConfirm(false)
      setSuccessMessage(`Cleared ${data.services_deleted} service${data.services_deleted !== 1 ? 's' : ''}`)
      setTimeout(() => setSuccessMessage(null), 4000)
    },
  })

  const startEdit = (service: Service) => {
    setEditingService(service)
    setIsAddingNew(false)
    reset({
      name: service.name,
      description: service.description || '',
      duration_minutes: service.duration_minutes,
      base_price: parseFloat(service.base_price),
      icon: service.icon || '',
      category_id: service.category_id || '',
      requires_vehicle: service.requires_vehicle,
      is_active: service.is_active,
    })
  }

  const startAdd = () => {
    setIsAddingNew(true)
    setEditingService(null)
    reset({
      name: '',
      description: '',
      duration_minutes: 60,
      base_price: 0,
      icon: '',
      category_id: '',
      requires_vehicle: true,
      is_active: true,
    })
  }

  const cancelEdit = () => {
    setEditingService(null)
    setIsAddingNew(false)
    reset()
  }

  const onSubmit = (data: ServiceFormData) => {
    if (editingService) {
      updateMutation.mutate({ id: editingService.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handleResize = () => setIsMobile(window.innerWidth < 640)
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const drawerInputClasses = (hasError: boolean) => {
    const base = "w-full px-3 py-2 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 text-sm"
    return hasError
      ? `${base} border-red-500 focus:ring-red-500`
      : `${base} border-gray-200 focus:ring-amber-500`
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  const activeViewMode = isMobile ? 'cards' : viewMode

  const filteredServices = services?.filter((svc) => {
    if (!searchQuery.trim()) return true
    const q = searchQuery.toLowerCase()
    return (
      svc.name.toLowerCase().includes(q) ||
      (svc.description || '').toLowerCase().includes(q)
    )
  })

  return (
    <div className="space-y-6 lg:flex lg:h-full lg:min-h-0 lg:flex-col lg:gap-4 lg:space-y-0">
      {/* Header */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center lg:mb-0 lg:flex-shrink-0">
        <div className="flex-1">
          <SearchAddBar
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search services..."
            onAdd={startAdd}
            addLabel="Add Service"
            addLabelMobile="Add"
            className=""
            inputWidthClass="sm:min-w-[260px] md:max-w-lg"
            showAddButton={!isAddingNew && !editingService}
          />
        </div>
        <div className="relative shrink-0" ref={menuRef}>
          <button
            onClick={() => setShowMenu(v => !v)}
            className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-gray-400 hover:text-gray-200 border border-white/15 transition-colors"
            title="Catalog options"
          >
            <Settings className="w-4 h-4" />
          </button>
          {showMenu && (
            <div className="absolute right-0 top-full mt-1 w-44 bg-[#1a2030] border border-white/15 rounded-lg shadow-xl z-50 overflow-hidden">
              {showClearConfirm ? (
                <div className="p-2 space-y-1">
                  <p className="text-xs text-gray-400 px-2 py-1">Clear all services?</p>
                  <button
                    onClick={() => clearMutation.mutate()}
                    disabled={clearMutation.isPending}
                    className="w-full text-left px-3 py-2 text-sm text-red-400 hover:bg-white/10 rounded-md disabled:opacity-50"
                  >
                    {clearMutation.isPending ? 'Clearing…' : 'Yes, clear all'}
                  </button>
                  <button
                    onClick={() => setShowClearConfirm(false)}
                    className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/10 rounded-md"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <>
                  <button
                    onClick={() => { preloadMutation.mutate(); setShowMenu(false) }}
                    disabled={preloadMutation.isPending}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 disabled:opacity-50"
                  >
                    <Download className="w-3.5 h-3.5 shrink-0" />
                    {preloadMutation.isPending ? 'Loading…' : 'Load defaults'}
                  </button>
                  <button
                    onClick={() => setShowClearConfirm(true)}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-red-400 hover:bg-white/10"
                  >
                    <Trash2 className="w-3.5 h-3.5 shrink-0" />
                    Clear all
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {successMessage && (
        <div className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/20 px-4 py-3 text-green-400 lg:flex-shrink-0">
          <CheckCircle className="w-5 h-5 flex-shrink-0" />
          {successMessage}
        </div>
      )}

      {/* Services Table / Cards */}
      <div className="overflow-hidden rounded-xl border border-white/10 bg-white/5 lg:flex lg:min-h-0 lg:flex-1 lg:flex-col">
        <div className="hidden items-center justify-start border-b border-white/10 px-4 py-3 sm:flex lg:flex-shrink-0">
          <ViewToggle value={activeViewMode} onChange={setViewMode} disabled={isMobile} />
        </div>
        <div className="max-h-[calc(100vh-240px)] overflow-y-auto lg:min-h-0 lg:flex-1 lg:max-h-none">
        {activeViewMode === 'list' ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-white/5 border-b border-white/10">
                <tr>
                  <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Service</th>
                  <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3 hidden sm:table-cell">Category</th>
                  <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Price</th>
                  <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3 hidden md:table-cell">Duration</th>
                  <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Status</th>
                  <th className="text-right text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filteredServices?.map((service) => {
                  const category = categories?.find((c) => c.id === service.category_id)
                  return (
                    <tr key={service.id} className="hover:bg-white/5">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="text-xl text-amber-200">
                            {service.icon ? <span>{service.icon}</span> : <Wrench className="w-5 h-5" />}
                          </span>
                          <div>
                            <div className="text-sm font-medium text-white">{service.name}</div>
                            {service.description && (
                              <div className="text-xs text-gray-500 line-clamp-1">{service.description}</div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <span className="text-sm text-gray-400">{category?.name || '—'}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm font-medium text-amber-400">
                          ${parseFloat(service.base_price).toFixed(2)}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        <span className="text-sm text-gray-400">{service.duration_minutes} min</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full ${
                          service.is_active
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-gray-500/20 text-gray-400'
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${service.is_active ? 'bg-green-400' : 'bg-gray-400'}`} />
                          {service.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => startEdit(service)}
                          className="text-amber-400 hover:text-amber-300 text-sm font-medium"
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  )
                })}
              {(!filteredServices || filteredServices.length === 0) && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                      No services found. Add your first service above.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
            {filteredServices?.map((service) => {
              const category = categories?.find((c) => c.id === service.category_id)
              return (
                <div key={service.id} className="bg-white/10 border border-white/15 rounded-xl p-4 space-y-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-xs uppercase text-gray-400">{category?.name || 'Uncategorized'}</div>
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <span className="text-xl">{service.icon || '🛠️'}</span>
                        {service.name}
                      </h3>
                      <p className="text-xs text-gray-400 mt-1">{service.description || 'No description'}</p>
                    </div>
                    <span className={`px-2 py-1 rounded-full text-xs font-semibold ${
                      service.is_active ? 'bg-green-500/20 text-green-300' : 'bg-gray-500/20 text-gray-300'
                    }`}>
                      {service.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm text-gray-200">
                    <div>
                      <p className="text-gray-400 text-xs">Duration</p>
                      <p className="font-semibold">{service.duration_minutes} min</p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-xs">Price</p>
                      <p className="font-semibold">${service.base_price}</p>
                    </div>
                    <div className="col-span-2 flex items-center justify-between">
                      <span className="text-xs text-gray-400">Requires vehicle</span>
                      <span className="text-xs font-semibold text-gray-100">
                        {service.requires_vehicle ? 'Yes' : 'No'}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => startEdit(service)}
                    className="w-full px-3 py-2 text-sm font-medium text-amber-200 bg-amber-500/10 border border-amber-400/40 rounded-lg hover:bg-amber-500/20 transition"
                  >
                    Edit
                  </button>
                </div>
              )
            })}
            {(!filteredServices || filteredServices.length === 0) && (
              <div className="text-gray-400 text-sm col-span-full text-center">No services found. Add your first service above.</div>
            )}
          </div>
        )}
        </div>
      </div>

      {/* Slide-out Add/Edit Form */}
      {formOpen && (
        <div
          className={`fixed inset-0 z-[60] transition ${formOpen ? 'pointer-events-auto' : 'pointer-events-none'}`}
          aria-hidden={!formOpen}
        >
          <div
            className={`absolute inset-0 bg-black/50 transition-opacity ${formOpen ? 'opacity-100' : 'opacity-0'}`}
            onClick={cancelEdit}
          />
          <aside
            className={`absolute top-0 right-0 h-full w-full sm:w-[520px] bg-white/95 backdrop-blur border-l border-gray-200 shadow-xl transform transition-transform ${
              formOpen ? 'translate-x-0' : 'translate-x-full'
            }`}
            role="dialog"
            aria-label={editingService ? 'Edit Service' : 'Add Service'}
          >
            <form onSubmit={handleSubmit(onSubmit)} className="h-full flex flex-col">
              <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase text-gray-500 font-semibold">
                    {editingService ? 'Edit Service' : 'Add Service'}
                  </p>
                  <p className="text-lg font-semibold text-slate-800">
                    {editingService ? editingService.name : 'Create a new service'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={cancelEdit}
                  className="p-2 text-gray-500 hover:text-amber-600 rounded-full hover:bg-amber-50"
                  aria-label="Close service form"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="p-5 space-y-4 overflow-y-auto flex-1">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
                    <input
                      {...register('name')}
                      className={drawerInputClasses(!!errors.name)}
                      placeholder="Oil Change"
                    />
                    {errors.name && <p className="mt-1 text-xs text-red-500">{errors.name.message}</p>}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Category</label>
                    <select
                      {...register('category_id')}
                      className={drawerInputClasses(false)}
                    >
                      <option value="">No Category</option>
                      {categories?.map((cat) => (
                        <option key={cat.id} value={cat.id}>{cat.name}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Base Price ($)</label>
                    <input
                      {...register('base_price')}
                      type="number"
                      step="0.01"
                      min="0"
                      className={drawerInputClasses(!!errors.base_price)}
                      placeholder="99.00"
                    />
                    {errors.base_price && <p className="mt-1 text-xs text-red-500">{errors.base_price.message}</p>}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Duration (minutes)</label>
                    <input
                      {...register('duration_minutes')}
                      type="number"
                      min="5"
                      className={drawerInputClasses(!!errors.duration_minutes)}
                      placeholder="60"
                    />
                    {errors.duration_minutes && <p className="mt-1 text-xs text-red-500">{errors.duration_minutes.message}</p>}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Icon (emoji)</label>
                    <input type="hidden" {...register('icon')} />
                    <div className="grid grid-cols-5 gap-2">
                      <button
                        type="button"
                        onClick={() => setValue('icon', '', { shouldValidate: true })}
                        className={`py-2 text-sm font-semibold rounded-lg border transition ${
                          !selectedIcon ? 'border-amber-400 bg-amber-50 text-amber-700' : 'border-gray-200 hover:border-amber-300'
                        }`}
                      >
                        None
                      </button>
                      {iconOptions.map((opt) => (
                        <button
                          key={opt}
                          type="button"
                          onClick={() => setValue('icon', opt, { shouldValidate: true })}
                          className={`py-2 text-lg rounded-lg border transition ${
                            selectedIcon === opt
                              ? 'border-amber-500 bg-amber-50 shadow-sm'
                              : 'border-gray-200 hover:border-amber-300'
                          }`}
                          aria-pressed={selectedIcon === opt}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Description</label>
                  <textarea
                    {...register('description')}
                    rows={2}
                    className={drawerInputClasses(false)}
                    placeholder="Service description..."
                  />
                </div>

                <div className="flex items-center gap-6">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      {...register('requires_vehicle')}
                      type="checkbox"
                      className="w-4 h-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                    />
                    <span className="text-sm text-gray-600">Requires vehicle</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      {...register('is_active')}
                      type="checkbox"
                      className="w-4 h-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                    />
                    <span className="text-sm text-gray-600">Active</span>
                  </label>
                </div>
              </div>

              <div className="px-5 py-4 border-t border-gray-200 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={cancelEdit}
                  className="px-5 py-2 bg-white/10 hover:bg-white/20 text-gray-700 rounded-lg text-sm font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                  className="px-5 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-400 text-white font-semibold rounded-lg text-sm"
                >
                  {createMutation.isPending || updateMutation.isPending ? 'Saving...' : editingService ? 'Update' : 'Create'}
                </button>
              </div>
            </form>
          </aside>
        </div>
      )}
    </div>
  )
}
