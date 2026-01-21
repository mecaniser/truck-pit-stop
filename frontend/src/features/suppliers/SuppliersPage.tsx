import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { LayoutGrid, Rows, Phone, MapPin, FileText, Loader2, Plus, Pencil, Trash2, UserRound } from 'lucide-react'
import api from '@/lib/api'
import { Supplier } from '@/types'
import { useAuthStore } from '@/stores/authStore'
import { formatUSPhone } from '@/utils/phone'

const supplierSchema = z.object({
  name: z.string().min(1, 'Supplier name is required'),
  address: z.string().optional(),
  phone: z.string().optional(),
  contact_name: z.string().optional(),
  notes: z.string().optional(),
})

type SupplierFormData = z.infer<typeof supplierSchema>

const cleanString = (value?: string | null) => {
  const trimmed = (value || '').trim()
  return trimmed === '' ? undefined : trimmed
}

export default function SuppliersPage() {
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'garage_admin' || user?.role === 'super_admin'

  const [viewMode, setViewMode] = useState<'list' | 'cards'>('list')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<Supplier | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)

  const showMessage = (message: string) => {
    setStatusMessage(message)
    setTimeout(() => setStatusMessage(null), 2800)
  }

  const { data: suppliers, isLoading } = useQuery<Supplier[]>({
    queryKey: ['suppliers'],
    queryFn: async () => {
      const response = await api.get('/suppliers')
      return response.data
    },
  })

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors },
  } = useForm<SupplierFormData>({
    resolver: zodResolver(supplierSchema),
    defaultValues: { name: '', address: '', phone: '', contact_name: '', notes: '' },
  })

  useEffect(() => {
    if (editing) {
      reset({
        name: editing.name,
        address: editing.address || '',
        phone: editing.phone || '',
        contact_name: editing.contact_name || '',
        notes: editing.notes || '',
      })
    } else {
      reset({ name: '', address: '', phone: '', contact_name: '', notes: '' })
    }
  }, [editing, reset])

  const createMutation = useMutation({
    mutationFn: async (data: SupplierFormData) => {
      await api.post('/suppliers', {
        name: data.name.trim(),
        address: cleanString(data.address),
        phone: cleanString(data.phone),
        contact_name: cleanString(data.contact_name),
        notes: cleanString(data.notes),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
      showMessage('Supplier added')
      reset()
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || 'Failed to add supplier'
      showMessage(Array.isArray(detail) ? detail.join(', ') : detail)
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: SupplierFormData }) => {
      await api.put(`/suppliers/${id}`, {
        name: data.name.trim(),
        address: cleanString(data.address),
        phone: cleanString(data.phone),
        contact_name: cleanString(data.contact_name),
        notes: cleanString(data.notes),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
      setEditing(null)
      showMessage('Supplier updated')
      reset()
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || 'Failed to update supplier'
      showMessage(Array.isArray(detail) ? detail.join(', ') : detail)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/suppliers/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
      showMessage('Supplier removed')
      if (editing && editing.id) {
        setEditing(null)
      }
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || 'Failed to delete supplier'
      showMessage(Array.isArray(detail) ? detail.join(', ') : detail)
    },
  })

  const onSubmit = (data: SupplierFormData) => {
    if (!isAdmin) return
    if (editing) {
      updateMutation.mutate({ id: editing.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  const handleDelete = (supplier: Supplier) => {
    if (!isAdmin) return
    const confirmed = window.confirm(`Delete ${supplier.name}? This cannot be undone.`)
    if (confirmed) {
      deleteMutation.mutate(supplier.id)
    }
  }

  const filteredSuppliers = useMemo(() => {
    if (!suppliers) return []
    if (!search.trim()) return suppliers
    const q = search.toLowerCase().trim()
    return suppliers.filter((s) => {
      return (
        s.name.toLowerCase().includes(q) ||
        (s.contact_name || '').toLowerCase().includes(q) ||
        (s.phone || '').toLowerCase().includes(q) ||
        (s.address || '').toLowerCase().includes(q)
      )
    })
  }, [search, suppliers])

  const inputClass = (hasError?: boolean) =>
    `w-full px-3 py-2 rounded-lg bg-white/10 border text-white placeholder-gray-400 focus:outline-none focus:ring-2 text-sm ${
      hasError ? 'border-red-500 focus:ring-red-500' : 'border-white/20 focus:ring-amber-500'
    }`

  const isSaving = createMutation.isLoading || updateMutation.isLoading

  return (
    <div className="space-y-5">
      <div className="bg-white/5 border border-white/10 rounded-xl p-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase text-amber-200/80 font-semibold tracking-wide">Inventory partners</p>
          <h1 className="text-xl sm:text-2xl font-bold text-white">Suppliers</h1>
          <p className="text-sm text-gray-300">
            Keep track of vendors powering your parts shelf. Add contacts, addresses, and notes for quick reorders.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-white/10 border border-white/15 rounded-lg p-1">
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={`flex items-center gap-1 px-3 py-1 rounded-md text-sm font-medium transition ${
                viewMode === 'list' ? 'bg-amber-500 text-white' : 'text-white hover:bg-white/20'
              }`}
            >
              <Rows className="w-4 h-4" /> Rows
            </button>
            <button
              type="button"
              onClick={() => setViewMode('cards')}
              className={`flex items-center gap-1 px-3 py-1 rounded-md text-sm font-medium transition ${
                viewMode === 'cards' ? 'bg-amber-500 text-white' : 'text-white hover:bg-white/20'
              }`}
            >
              <LayoutGrid className="w-4 h-4" /> Cards
            </button>
          </div>
          <div className={`px-3 py-1 rounded-full border text-xs font-semibold ${isAdmin ? 'border-amber-500/40 text-amber-200 bg-amber-500/10' : 'border-gray-400/40 text-gray-200 bg-gray-500/10'}`}>
            {isAdmin ? 'Admin access' : 'Read-only'}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr,1fr]">
        <div className="space-y-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="relative w-full md:max-w-sm">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search suppliers by name, contact, phone, or address..."
                className="w-full pl-10 pr-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            {statusMessage && <span className="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/30 px-3 py-1 rounded-full">{statusMessage}</span>}
          </div>

          <div className="bg-white/5 border border-white/10 rounded-xl">
            {isLoading ? (
              <div className="p-6 text-sm text-gray-300">Loading suppliers...</div>
            ) : filteredSuppliers.length === 0 ? (
              <div className="p-6 text-sm text-gray-300">
                No suppliers match your search. {suppliers && suppliers.length === 0 ? 'Add your first supplier on the right.' : 'Try a different filter.'}
              </div>
            ) : viewMode === 'list' ? (
              <div className="overflow-hidden">
                <table className="min-w-full divide-y divide-white/10">
                  <thead className="bg-white/5 text-left text-xs uppercase tracking-wide text-gray-400">
                    <tr>
                      <th className="px-4 py-3">Supplier</th>
                      <th className="px-4 py-3">Contact</th>
                      <th className="px-4 py-3">Phone</th>
                      <th className="px-4 py-3">Address</th>
                      <th className="px-4 py-3">Notes</th>
                      {isAdmin && <th className="px-4 py-3 text-right">Actions</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 text-sm text-gray-100">
                    {filteredSuppliers.map((supplier) => (
                      <tr key={supplier.id} className="hover:bg-white/5 transition-colors">
                        <td className="px-4 py-3 font-semibold text-white">{supplier.name}</td>
                        <td className="px-4 py-3 text-gray-200">
                          {supplier.contact_name ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-white/10 border border-white/10 px-2.5 py-1 text-xs">
                              <UserRound className="w-3.5 h-3.5" />
                              {supplier.contact_name}
                            </span>
                          ) : (
                            <span className="text-gray-500 text-xs">Not set</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-gray-200">
                          {supplier.phone ? (
                            <span className="inline-flex items-center gap-1">
                              <Phone className="w-4 h-4 text-amber-300" />
                              {supplier.phone}
                            </span>
                          ) : (
                            <span className="text-gray-500 text-xs">Not set</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-gray-200">
                          {supplier.address ? (
                            <span className="inline-flex items-center gap-1">
                              <MapPin className="w-4 h-4 text-amber-300" />
                              <span className="line-clamp-2">{supplier.address}</span>
                            </span>
                          ) : (
                            <span className="text-gray-500 text-xs">Not set</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-gray-300">
                          {supplier.notes ? (
                            <span className="inline-flex items-center gap-1">
                              <FileText className="w-4 h-4 text-amber-300" />
                              <span className="line-clamp-2">{supplier.notes}</span>
                            </span>
                          ) : (
                            <span className="text-gray-500 text-xs">—</span>
                          )}
                        </td>
                        {isAdmin && (
                          <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                            <button
                              type="button"
                              onClick={() => setEditing(supplier)}
                              className="inline-flex items-center gap-1 text-xs font-semibold text-amber-200 hover:text-white"
                            >
                              <Pencil className="w-4 h-4" />
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDelete(supplier)}
                              className="inline-flex items-center gap-1 text-xs font-semibold text-red-200 hover:text-red-100"
                              disabled={deleteMutation.isLoading}
                            >
                              <Trash2 className="w-4 h-4" />
                              Delete
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 p-4">
                {filteredSuppliers.map((supplier) => (
                  <div
                    key={supplier.id}
                    className="rounded-lg border border-white/10 bg-white/5 p-4 shadow-sm hover:border-amber-400/60 hover:bg-white/10 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm uppercase text-gray-400 font-semibold">Supplier</p>
                        <h3 className="text-lg font-bold text-white">{supplier.name}</h3>
                        {supplier.contact_name && (
                          <p className="text-sm text-gray-200 flex items-center gap-2 mt-1">
                            <UserRound className="w-4 h-4 text-amber-300" />
                            {supplier.contact_name}
                          </p>
                        )}
                      </div>
                      {isAdmin && (
                        <button
                          type="button"
                          onClick={() => setEditing(supplier)}
                          className="text-amber-200 hover:text-white text-xs font-semibold"
                        >
                          Edit
                        </button>
                      )}
                    </div>
                    <div className="mt-3 space-y-1 text-sm text-gray-200">
                      <div className="flex items-start gap-2">
                        <Phone className="w-4 h-4 text-amber-300 mt-0.5" />
                        <span>{supplier.phone || 'Phone not set'}</span>
                      </div>
                      <div className="flex items-start gap-2">
                        <MapPin className="w-4 h-4 text-amber-300 mt-0.5" />
                        <span className="line-clamp-2">{supplier.address || 'Address not set'}</span>
                      </div>
                      <div className="flex items-start gap-2">
                        <FileText className="w-4 h-4 text-amber-300 mt-0.5" />
                        <span className="line-clamp-3">{supplier.notes || 'No notes yet'}</span>
                      </div>
                    </div>
                    {isAdmin && (
                      <div className="mt-4 flex items-center justify-between text-xs">
                        <button
                          type="button"
                          onClick={() => setEditing(supplier)}
                          className="inline-flex items-center gap-1 font-semibold text-amber-200 hover:text-white"
                        >
                          <Pencil className="w-4 h-4" />
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(supplier)}
                          className="inline-flex items-center gap-1 font-semibold text-red-200 hover:text-red-100"
                          disabled={deleteMutation.isLoading}
                        >
                          <Trash2 className="w-4 h-4" />
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-xl p-5 space-y-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-xs uppercase text-gray-400 font-semibold">
                {editing ? 'Update supplier' : 'Add supplier'}
              </p>
              <h3 className="text-lg font-bold text-white">
                {editing ? editing.name : 'New supplier'}
              </h3>
              <p className="text-xs text-gray-300">Names help keep purchase orders tidy.</p>
            </div>
            <button
              type="button"
              onClick={() => setEditing(null)}
              className="px-3 py-1 rounded-full text-xs font-semibold bg-white/10 text-gray-200 hover:bg-white/20"
            >
              <Plus className="w-4 h-4 inline-block mr-1" />
              New
            </button>
          </div>

          {!isAdmin && (
            <div className="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
              You can browse suppliers, but only garage admins can add or edit them.
            </div>
          )}

          <form className="space-y-3" onSubmit={handleSubmit(onSubmit)}>
            <label className="text-sm text-gray-200 space-y-1 block">
              <span>Name</span>
              <input
                type="text"
                {...register('name')}
                disabled={!isAdmin || isSaving}
                className={inputClass(!!errors.name)}
                placeholder="Acme Parts Co."
              />
              {errors.name && <p className="text-xs text-red-400">{errors.name.message}</p>}
            </label>

            <label className="text-sm text-gray-200 space-y-1 block">
              <span>Primary contact</span>
              <input
                type="text"
                {...register('contact_name')}
                disabled={!isAdmin || isSaving}
                className={inputClass(!!errors.contact_name)}
                placeholder="Contact name"
              />
            </label>

            <label className="text-sm text-gray-200 space-y-1 block">
              <span>Phone</span>
              <input
                type="tel"
                {...register('phone')}
                onChange={(e) => setValue('phone', formatUSPhone(e.target.value), { shouldValidate: true })}
                disabled={!isAdmin || isSaving}
                className={inputClass(!!errors.phone)}
                placeholder="(555) 123-4567"
              />
            </label>

            <label className="text-sm text-gray-200 space-y-1 block">
              <span>Address</span>
              <textarea
                {...register('address')}
                rows={2}
                disabled={!isAdmin || isSaving}
                className={`${inputClass(!!errors.address)} resize-none`}
                placeholder="Street, City, State"
              />
            </label>

            <label className="text-sm text-gray-200 space-y-1 block">
              <span>Notes</span>
              <textarea
                {...register('notes')}
                rows={3}
                disabled={!isAdmin || isSaving}
                className={`${inputClass(!!errors.notes)} resize-none`}
                placeholder="Ordering preferences, payment terms, delivery timing..."
              />
            </label>

            <div className="flex items-center justify-between">
              {statusMessage ? (
                <span className="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/30 px-3 py-1 rounded-full">
                  {statusMessage}
                </span>
              ) : (
                <span className="text-xs text-gray-400">Fields sync to all admins.</span>
              )}
              <div className="flex items-center gap-2">
                {editing && (
                  <button
                    type="button"
                    onClick={() => setEditing(null)}
                    className="px-3 py-2 rounded-lg text-sm font-medium text-gray-200 bg-white/10 hover:bg-white/20"
                    disabled={isSaving}
                  >
                    Cancel edit
                  </button>
                )}
                <button
                  type="submit"
                  disabled={!isAdmin || isSaving}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-amber-500 hover:bg-amber-600 disabled:opacity-60"
                >
                  {(isSaving || deleteMutation.isLoading) && <Loader2 className="w-4 h-4 animate-spin" />}
                  {editing ? 'Save changes' : 'Add supplier'}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
