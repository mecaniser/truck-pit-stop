import { useEffect, useMemo, useState, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { LayoutGrid, Rows, Phone, MapPin, FileText, Loader2, Pencil, Trash2, UserRound } from 'lucide-react'
import api from '@/lib/api'
import { Supplier } from '@/types'
import { useAuthStore } from '@/stores/authStore'
import { formatUSPhone } from '@/utils/phone'
import MapboxAddressInput from '@/components/MapboxAddressInput'

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

  const [viewMode, setViewMode] = useState<'list' | 'cards'>(window.innerWidth < 640 ? 'cards' : 'list')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<Supplier | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)

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
      setFormOpen(true)
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

  const startAddSupplier = () => {
    setEditing(null)
    reset({ name: '', address: '', phone: '', contact_name: '', notes: '' })
    setFormOpen(true)
  }

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
      setFormOpen(false)
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
      setFormOpen(false)
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
      setConfirmingDeleteId(null)
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
    deleteMutation.mutate(supplier.id)
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

  const closeForm = () => {
    setFormOpen(false)
    setEditing(null)
    reset({ name: '', address: '', phone: '', contact_name: '', notes: '' })
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="space-y-5">
      <div className="bg-white/5 border border-white/10 rounded-xl p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <p className="text-xs uppercase text-amber-200/80 font-semibold tracking-wide">Inventory partners</p>
          <div className={`px-3 py-1 rounded-full border text-xs font-semibold ${isAdmin ? 'border-amber-500/40 text-amber-200 bg-amber-500/10' : 'border-gray-400/40 text-gray-200 bg-gray-500/10'}`}>
            {isAdmin ? 'Admin access' : 'Read-only'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex w-full sm:w-auto items-center gap-1 bg-white/10 border border-white/15 rounded-lg p-1">
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={`flex-1 flex items-center justify-center gap-1 px-3 py-1 rounded-md text-sm font-medium transition ${
                viewMode === 'list' ? 'bg-amber-500 text-white' : 'text-white hover:bg-white/20'
              }`}
            >
              <Rows className="w-4 h-4" /> Rows
            </button>
            <button
              type="button"
              onClick={() => setViewMode('cards')}
              className={`flex-1 flex items-center justify-center gap-1 px-3 py-1 rounded-md text-sm font-medium transition ${
                viewMode === 'cards' ? 'bg-amber-500 text-white' : 'text-white hover:bg-white/20'
              }`}
            >
              <LayoutGrid className="w-4 h-4" /> Cards
            </button>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px] sm:min-w-[280px] md:max-w-lg lg:max-w-xl">
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
          <div className="flex items-center gap-2 flex-wrap justify-end sm:ml-auto">
            {statusMessage && (
              <span className="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/30 px-3 py-1 rounded-full">
                {statusMessage}
              </span>
            )}
            <button
              type="button"
              onClick={startAddSupplier}
              className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-amber-500 hover:bg-amber-600"
            >
              <span className="sm:hidden">+ Add</span>
              <span className="hidden sm:inline">+ Add supplier</span>
            </button>
          </div>
        </div>

          <div className="bg-white/5 border border-white/10 rounded-xl">
            {isLoading ? (
              <div className="p-6 text-sm text-gray-300">Loading suppliers...</div>
            ) : filteredSuppliers.length === 0 ? (
              <div className="p-6 text-sm text-gray-300">
                No suppliers match your search. {suppliers && suppliers.length === 0 ? 'Add your first supplier with the button above.' : 'Try a different filter.'}
              </div>
            ) : viewMode === 'list' ? (
              <>
                <div className="sm:hidden space-y-3 p-4">
                  {filteredSuppliers.map((supplier) => (
                    <div key={supplier.id} className="rounded-lg border border-white/10 bg-white/5 p-4 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-xs uppercase text-gray-400 font-semibold">Supplier</p>
                          <p className="text-base font-semibold text-white">{supplier.name}</p>
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
                      <div className="space-y-1 text-xs text-gray-200">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="inline-flex items-center gap-1">
                            <UserRound className="w-4 h-4 text-amber-300" />
                            {supplier.contact_name || 'Contact not set'}
                          </span>
                          {supplier.phone && (
                            <span className="inline-flex items-center gap-1 border-l border-white/10 pl-2">
                              <Phone className="w-4 h-4 text-amber-300" />
                              {supplier.phone}
                            </span>
                          )}
                        </div>
                        <div className="flex items-start gap-2">
                          <MapPin className="w-4 h-4 text-amber-300 mt-0.5" />
                          <span>{supplier.address || 'Address not set'}</span>
                        </div>
                        <div className="flex items-start gap-2">
                          <FileText className="w-4 h-4 text-amber-300 mt-0.5" />
                          <span>{supplier.notes?.trim() || 'No notes yet'}</span>
                        </div>
                      </div>
                      {isAdmin && (
                        <div className="flex items-center gap-2 text-xs">
                          {confirmingDeleteId === supplier.id ? (
                            <>
                              <button
                                type="button"
                                onClick={() => handleDelete(supplier)}
                                className="inline-flex items-center gap-1 font-semibold text-red-200 hover:text-red-100"
                                disabled={deleteMutation.isPending}
                              >
                                <Trash2 className="w-4 h-4" />
                                Confirm
                              </button>
                              <button
                                type="button"
                                onClick={() => setConfirmingDeleteId(null)}
                                className="inline-flex items-center gap-1 font-semibold text-gray-300 hover:text-white"
                                disabled={deleteMutation.isPending}
                              >
                                Cancel
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                type="button"
                                onClick={() => {
                                  setEditing(supplier)
                                  setConfirmingDeleteId(null)
                                }}
                                className="inline-flex items-center gap-1 font-semibold text-amber-200 hover:text-white"
                              >
                                <Pencil className="w-4 h-4" />
                                Edit
                              </button>
                              <button
                                type="button"
                                onClick={() => setConfirmingDeleteId(supplier.id)}
                                className="inline-flex items-center gap-1 font-semibold text-red-200 hover:text-red-100"
                                disabled={deleteMutation.isPending}
                              >
                                <Trash2 className="w-4 h-4" />
                                Delete
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                <div className="hidden sm:block overflow-hidden">
                  <table className="min-w-full divide-y divide-white/10">
                    <thead className="bg-white/5 text-left text-xs uppercase tracking-wide text-gray-400">
                      <tr>
                        <th className="px-4 py-3">Supplier</th>
                        <th className="px-4 py-3">Contact</th>
                        {isAdmin && <th className="px-4 py-3 text-right">Actions</th>}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-sm text-gray-100">
                      {filteredSuppliers.map((supplier) => (
                        <Fragment key={supplier.id}>
                          <tr className="hover:bg-white/5 transition-colors">
                            <td className="px-4 py-3 font-semibold text-white">{supplier.name}</td>
                            <td className="px-4 py-3 text-gray-200">
                              {(supplier.contact_name || supplier.phone) ? (
                                <div className="inline-flex flex-wrap items-center gap-2 px-3 py-2 rounded-lg bg-white/10 border border-white/10 text-xs min-w-[150px]">
                                  <span className="inline-flex items-center gap-1">
                                    <UserRound className="w-3.5 h-3.5" />
                                    {supplier.contact_name || 'Contact not set'}
                                  </span>
                                  {supplier.phone && (
                                    <span className="inline-flex items-center gap-1 border-l border-white/15 pl-2">
                                      <Phone className="w-3.5 h-3.5 text-amber-300" />
                                      {supplier.phone}
                                    </span>
                                  )}
                                </div>
                              ) : (
                                <span className="text-gray-500 text-xs">Not set</span>
                              )}
                            </td>
                            {isAdmin && (
                              <td className="px-4 py-3 text-right whitespace-nowrap">
                                <div className="relative inline-flex justify-end min-w-[190px] overflow-hidden">
                                  <div
                                    className={`flex items-center gap-2 transition-all duration-200 ease-in-out ${
                                      confirmingDeleteId === supplier.id
                                        ? '-translate-x-4 opacity-0 pointer-events-none'
                                        : 'translate-x-0 opacity-100'
                                    }`}
                                  >
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setEditing(supplier)
                                        setConfirmingDeleteId(null)
                                      }}
                                      className="inline-flex items-center gap-1 text-xs font-semibold text-amber-200 hover:text-white"
                                    >
                                      <Pencil className="w-4 h-4" />
                                      Edit
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => setConfirmingDeleteId(supplier.id)}
                                      className="inline-flex items-center gap-1 text-xs font-semibold text-red-200 hover:text-red-100"
                                      disabled={deleteMutation.isPending}
                                    >
                                      <Trash2 className="w-4 h-4" />
                                      Delete
                                    </button>
                                  </div>
                                  <div
                                    className={`absolute right-0 top-0 flex items-center gap-2 transition-all duration-200 ease-out ${
                                      confirmingDeleteId === supplier.id
                                        ? 'translate-x-0 opacity-100'
                                        : 'translate-x-full opacity-0 pointer-events-none'
                                    }`}
                                  >
                                    <button
                                      type="button"
                                      onClick={() => handleDelete(supplier)}
                                      className="inline-flex items-center gap-1 text-xs font-semibold text-red-200 hover:text-red-100"
                                      disabled={deleteMutation.isPending}
                                    >
                                      <Trash2 className="w-4 h-4" />
                                      Confirm
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => setConfirmingDeleteId(null)}
                                      className="inline-flex items-center gap-1 text-xs font-semibold text-gray-300 hover:text-white"
                                      disabled={deleteMutation.isPending}
                                    >
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              </td>
                            )}
                          </tr>
                          <tr className="text-xs text-gray-300 bg-white/5">
                            <td className="px-4 py-2" colSpan={isAdmin ? 3 : 2}>
                              <div className="space-y-1 text-gray-200">
                                <div className="flex items-start gap-2">
                                  <MapPin className="w-4 h-4 text-amber-300 mt-0.5" />
                                  <span>{supplier.address || 'Address not set'}</span>
                                </div>
                                <div className="flex items-start gap-2">
                                  <FileText className="w-4 h-4 text-amber-300 mt-0.5" />
                                  <span>{supplier.notes?.trim() || 'No notes yet'}</span>
                                </div>
                              </div>
                            </td>
                          </tr>
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
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
                      <div className="mt-4 flex items-center justify-between text-xs relative overflow-hidden min-h-[30px]">
                        <div
                          className={`flex items-center gap-2 transition-all duration-200 ease-in-out ${
                            confirmingDeleteId === supplier.id
                              ? '-translate-x-4 opacity-0 pointer-events-none'
                              : 'translate-x-0 opacity-100'
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => {
                              setEditing(supplier)
                              setConfirmingDeleteId(null)
                            }}
                            className="inline-flex items-center gap-1 font-semibold text-amber-200 hover:text-white"
                          >
                            <Pencil className="w-4 h-4" />
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmingDeleteId(supplier.id)}
                            className="inline-flex items-center gap-1 font-semibold text-red-200 hover:text-red-100"
                            disabled={deleteMutation.isPending}
                          >
                            <Trash2 className="w-4 h-4" />
                            Delete
                          </button>
                        </div>
                        <div
                          className={`absolute right-0 top-0 flex items-center gap-2 transition-all duration-200 ease-out ${
                            confirmingDeleteId === supplier.id
                              ? 'translate-x-0 opacity-100'
                              : 'translate-x-full opacity-0 pointer-events-none'
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => handleDelete(supplier)}
                            className="inline-flex items-center gap-1 font-semibold text-red-200 hover:text-red-100"
                            disabled={deleteMutation.isPending}
                          >
                            <Trash2 className="w-4 h-4" />
                            Confirm
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmingDeleteId(null)}
                            className="inline-flex items-center gap-1 font-semibold text-gray-200 hover:text-white"
                            disabled={deleteMutation.isPending}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

      {(formOpen || editing) && (
        <div
          className={`fixed inset-0 z-50 transition ${formOpen || editing ? 'pointer-events-auto' : 'pointer-events-none'}`}
          aria-hidden={!(formOpen || editing)}
        >
          <div
            className={`absolute inset-0 bg-black/50 transition-opacity ${formOpen || editing ? 'opacity-100' : 'opacity-0'}`}
            onClick={closeForm}
          />
          <aside
            className={`absolute top-0 right-0 h-full w-full sm:w-[520px] bg-white/95 backdrop-blur border-l border-gray-200 shadow-xl transform transition-transform ${
              formOpen || editing ? 'translate-x-0' : 'translate-x-full'
            }`}
            role="dialog"
            aria-label="Supplier form"
          >
            <div className="h-full flex flex-col">
              <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase text-gray-500 font-semibold">Suppliers</p>
                  <p className="text-lg font-semibold text-slate-800">
                    {editing ? `Edit ${editing.name}` : 'Add supplier'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeForm}
                  className="p-2 text-gray-500 hover:text-amber-600 rounded-full hover:bg-amber-50"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="p-5 space-y-4 overflow-y-auto flex-1">
                {!isAdmin && (
                  <div className="text-xs text-amber-700 bg-amber-100 border border-amber-200 rounded-lg p-3">
                    You can browse suppliers, but only garage admins can add or edit them.
                  </div>
                )}

                <form className="space-y-3" onSubmit={handleSubmit(onSubmit)}>
                  <label className="text-sm text-gray-700 space-y-1 block">
                    <span>Name</span>
                    <input
                      type="text"
                      {...register('name')}
                      disabled={!isAdmin || isSaving}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                      placeholder="Acme Parts Co."
                    />
                    {errors.name && <p className="text-xs text-red-600">{errors.name.message}</p>}
                  </label>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <label className="text-sm text-gray-700 space-y-1 block">
                      <span>Primary contact</span>
                      <input
                        type="text"
                        {...register('contact_name')}
                        disabled={!isAdmin || isSaving}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                        placeholder="Contact name"
                      />
                    </label>

                    <label className="text-sm text-gray-700 space-y-1 block">
                      <span>Phone</span>
                      <input
                        type="tel"
                        {...register('phone')}
                        onChange={(e) => setValue('phone', formatUSPhone(e.target.value), { shouldValidate: true })}
                        disabled={!isAdmin || isSaving}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                        placeholder="(555) 123-4567"
                      />
                    </label>
                  </div>

                  <label className="text-sm text-gray-700 space-y-1 block">
                    <span>Address</span>
                    <MapboxAddressInput
                      {...register('address')}
                      autoComplete="street-address"
                      disabled={!isAdmin || isSaving}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                      placeholder="Start typing address..."
                      options={{ language: 'en', country: 'US' }}
                      onAddressSelect={({ formatted }) => {
                        if (formatted) {
                          setValue('address', formatted, { shouldValidate: true, shouldDirty: true })
                        }
                      }}
                    />
                  </label>

                  <label className="text-sm text-gray-700 space-y-1 block">
                    <span>Notes</span>
                    <textarea
                      {...register('notes')}
                      rows={3}
                      disabled={!isAdmin || isSaving}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none"
                      placeholder="Ordering preferences, payment terms, delivery timing..."
                    />
                  </label>

                  <div className="space-y-2">
                    <p className="text-xs uppercase font-semibold text-gray-500">Actions</p>
                    {statusMessage ? (
                      <span className="block text-xs text-amber-700 bg-amber-100 border border-amber-200 px-3 py-1 rounded-lg text-center">
                      {statusMessage}
                      </span>
                    ) : (
                      <span className="block text-xs text-gray-500 text-center">Fields sync to all admins.</span>
                    )}
                    <div className="space-y-2">
                      {editing && (
                        <button
                          type="button"
                          onClick={() => {
                            setEditing(null)
                            reset({ name: '', address: '', phone: '', contact_name: '', notes: '' })
                          }}
                          className="w-full px-4 py-2 rounded-lg text-sm font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200"
                          disabled={isSaving}
                        >
                          Cancel edit
                        </button>
                      )}
                      <button
                        type="submit"
                        disabled={!isAdmin || isSaving}
                        className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-amber-500 hover:bg-amber-600 disabled:opacity-60"
                      >
                        {(isSaving || deleteMutation.isPending) && <Loader2 className="w-4 h-4 animate-spin" />}
                        {editing ? 'Save changes' : 'Add supplier'}
                      </button>
                    </div>
                  </div>
                </form>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}
