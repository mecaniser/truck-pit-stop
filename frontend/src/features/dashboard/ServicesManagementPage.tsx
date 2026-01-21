import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import api from '../../lib/api'
import { CheckCircle, Plus, Wrench, LayoutGrid, Rows } from 'lucide-react'

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
  const [viewMode, setViewMode] = useState<'list' | 'cards'>('list')
  const [searchQuery, setSearchQuery] = useState('')

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

  const inputClasses = (hasError: boolean) => {
    const base = "w-full px-3 py-2 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 text-sm"
    return hasError
      ? `${base} border-red-500 focus:ring-red-500`
      : `${base} border-white/20 focus:ring-amber-500`
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  const filteredServices = services?.filter((svc) => {
    if (!searchQuery.trim()) return true
    const q = searchQuery.toLowerCase()
    return (
      svc.name.toLowerCase().includes(q) ||
      (svc.description || '').toLowerCase().includes(q)
    )
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex flex-wrap items-center gap-2 flex-1 min-w-[240px]">
          <div className="relative flex-1 min-w-[200px] sm:min-w-[260px] md:max-w-lg order-none">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search services..."
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/10 border border-white/15 text-sm text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M10.5 18a7.5 7.5 0 100-15 7.5 7.5 0 000 15z" />
            </svg>
          </div>
        </div>

        {!isAddingNew && !editingService && (
          <button
            onClick={startAdd}
            className="px-3 sm:px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white font-medium rounded-lg transition-colors flex items-center gap-2 shrink-0"
            aria-label="Add Service"
          >
            <Plus className="w-5 h-5" />
            <span className="hidden sm:inline">Add Service</span>
          </button>
        )}
      </div>

      {successMessage && (
        <div className="flex items-center gap-2 bg-green-500/20 border border-green-500/30 text-green-400 px-4 py-3 rounded-lg">
          <CheckCircle className="w-5 h-5 flex-shrink-0" />
          {successMessage}
        </div>
      )}

      {/* Add/Edit Form */}
      {(isAddingNew || editingService) && (
        <div className="bg-white/5 rounded-xl p-6 border border-white/10">
          <h2 className="text-lg font-semibold text-white mb-4">
            {editingService ? 'Edit Service' : 'Add New Service'}
          </h2>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Name</label>
                <input
                  {...register('name')}
                  className={inputClasses(!!errors.name)}
                  placeholder="Oil Change"
                />
                {errors.name && <p className="mt-1 text-xs text-red-400">{errors.name.message}</p>}
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Category</label>
                <select
                  {...register('category_id')}
                  className={inputClasses(false)}
                >
                  <option value="">No Category</option>
                  {categories?.map((cat) => (
                    <option key={cat.id} value={cat.id}>{cat.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Base Price ($)</label>
                <input
                  {...register('base_price')}
                  type="number"
                  step="0.01"
                  min="0"
                  className={inputClasses(!!errors.base_price)}
                  placeholder="99.00"
                />
                {errors.base_price && <p className="mt-1 text-xs text-red-400">{errors.base_price.message}</p>}
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Duration (minutes)</label>
                <input
                  {...register('duration_minutes')}
                  type="number"
                  min="5"
                  className={inputClasses(!!errors.duration_minutes)}
                  placeholder="60"
                />
                {errors.duration_minutes && <p className="mt-1 text-xs text-red-400">{errors.duration_minutes.message}</p>}
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Icon (emoji)</label>
                <input
                  {...register('icon')}
                  className={inputClasses(false)}
                  placeholder="Optional icon"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Description</label>
              <textarea
                {...register('description')}
                rows={2}
                className={inputClasses(false)}
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
                <span className="text-sm text-gray-300">Requires vehicle</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  {...register('is_active')}
                  type="checkbox"
                  className="w-4 h-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                />
                <span className="text-sm text-gray-300">Active</span>
              </label>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="submit"
                disabled={createMutation.isPending || updateMutation.isPending}
                className="px-5 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors"
              >
                {createMutation.isPending || updateMutation.isPending ? 'Saving...' : editingService ? 'Update' : 'Create'}
              </button>
              <button
                type="button"
                onClick={cancelEdit}
                className="px-5 py-2 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Services Table / Cards */}
      <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
        <div className="flex items-center justify-start gap-1 px-3 py-2 border-b border-white/10">
          <div className="flex w-full sm:w-auto items-center gap-1 bg-white/10 border border-white/15 rounded-md p-0.5">
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={`flex-1 sm:flex-none flex items-center justify-center gap-1 px-2.5 py-1 rounded-md text-sm font-medium transition ${viewMode === 'list' ? 'bg-amber-500 text-white' : 'text-white hover:bg-white/20'}`}
            >
              <Rows className="w-4 h-4" /> List
            </button>
            <button
              type="button"
              onClick={() => setViewMode('cards')}
              className={`flex-1 sm:flex-none flex items-center justify-center gap-1 px-2.5 py-1 rounded-md text-sm font-medium transition ${viewMode === 'cards' ? 'bg-amber-500 text-white' : 'text-white hover:bg-white/20'}`}
            >
              <LayoutGrid className="w-4 h-4" /> Cards
            </button>
          </div>
        </div>
        <div className="overflow-y-auto max-h-[calc(100vh-240px)]">
        {viewMode === 'list' ? (
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
    </div>
  )
}
