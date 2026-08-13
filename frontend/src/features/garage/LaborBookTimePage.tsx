import { useMemo, useRef, useState } from 'react'
import { Spinner, LoadingLine } from '@/components/ui'
import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Check, Clock3, Pencil, Plus, Search, Trash2, X } from 'lucide-react'
import { isAxiosError } from 'axios'
import api from '@/lib/api'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'

interface LaborBookTimeEntry {
  id: string
  operation_name: string
  operation_description: string | null
  normalized_hours: string
  vehicle_year: number | null
  vehicle_make: string | null
  vehicle_model: string | null
  vehicle_type: string | null
  body_class: string | null
  engine: string | null
  fuel_type: string | null
  engine_cylinders: number | null
  engine_displacement_l: number | null
  gvwr: string | null
  vin_sample: string | null
  vehicle_signature: string
  component_signature: string | null
  operation_key: string
  provider_operation_id: string | null
  source_provider: string
  usage_count: number
  last_used_at: string
  created_at: string
  updated_at: string
}

interface EditState {
  operation_name: string
  operation_description: string
  normalized_hours: string
}

interface CreateState extends EditState {
  vehicle_year: string
  vehicle_make: string
  vehicle_model: string
  vehicle_type: string
  body_class: string
  engine: string
  fuel_type: string
  engine_cylinders: string
  engine_displacement_l: string
  gvwr: string
  vin_sample: string
}

interface VinDecodeResult {
  vin: string
  make?: string | null
  model?: string | null
  year?: number | null
  vehicle_type?: string | null
  body_class?: string | null
  fuel_type?: string | null
  engine_cylinders?: number | null
  engine_displacement_l?: number | null
  gvwr?: string | null
  error_text?: string | null
}

const emptyCreateState: CreateState = {
  operation_name: '',
  operation_description: '',
  normalized_hours: '',
  vehicle_year: '',
  vehicle_make: '',
  vehicle_model: '',
  vehicle_type: '',
  body_class: '',
  engine: '',
  fuel_type: '',
  engine_cylinders: '',
  engine_displacement_l: '',
  gvwr: '',
  vin_sample: '',
}

const formatVehicleSignature = (value: string) =>
  value
    .split('-')
    .filter(Boolean)
    .map((part) => (part.length <= 3 ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ')

const formatDate = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(value))

const errorMessage = (err: unknown, fallback: string) => {
  if (isAxiosError<{ detail?: string }>(err)) {
    return err.response?.data?.detail || fallback
  }
  return fallback
}

const nullableText = (value: string) => value.trim() || null

const nullableNumber = (value: string) => {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

const vehicleScopeLabel = (entry: LaborBookTimeEntry) => {
  const primary = [entry.vehicle_year, entry.vehicle_make, entry.vehicle_model].filter(Boolean).join(' ')
  const secondary = [entry.engine, entry.fuel_type, entry.engine_displacement_l ? `${entry.engine_displacement_l}L` : null]
    .filter(Boolean)
    .join(' · ')
  return {
    primary: primary || formatVehicleSignature(entry.vehicle_signature),
    secondary: secondary || entry.component_signature || 'Vehicle application',
  }
}

export default function LaborBookTimePage() {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [createState, setCreateState] = useState<CreateState>(emptyCreateState)
  const lastDecodedVin = useRef('')
  const [editState, setEditState] = useState<EditState>({
    operation_name: '',
    operation_description: '',
    normalized_hours: '',
  })

  const debouncedSearch = useDebouncedValue(searchQuery.trim(), 300)
  const { data: entries = [], isLoading } = useQuery<LaborBookTimeEntry[]>({
    queryKey: ['labor-book-time', debouncedSearch],
    queryFn: async () => {
      const response = await api.get('/labor-book-time', {
        params: debouncedSearch ? { q: debouncedSearch } : undefined,
      })
      return response.data
    },
    placeholderData: keepPreviousData,
  })

  const stats = useMemo(() => {
    const totalHours = entries.reduce((sum, entry) => sum + Number(entry.normalized_hours || 0), 0)
    const totalUses = entries.reduce((sum, entry) => sum + Number(entry.usage_count || 0), 0)
    return {
      count: entries.length,
      totalHours,
      totalUses,
    }
  }, [entries])

  const createMutation = useMutation({
    mutationFn: async (data: CreateState) => {
      const response = await api.post('/labor-book-time', {
        operation_name: data.operation_name.trim(),
        operation_description: nullableText(data.operation_description),
        normalized_hours: Number(data.normalized_hours),
        vehicle_year: Number(data.vehicle_year),
        vehicle_make: data.vehicle_make.trim(),
        vehicle_model: data.vehicle_model.trim(),
        vehicle_type: nullableText(data.vehicle_type),
        body_class: nullableText(data.body_class),
        engine: nullableText(data.engine),
        fuel_type: nullableText(data.fuel_type),
        engine_cylinders: nullableNumber(data.engine_cylinders),
        engine_displacement_l: nullableNumber(data.engine_displacement_l),
        gvwr: nullableText(data.gvwr),
        vin_sample: nullableText(data.vin_sample.toUpperCase()),
      })
      return response.data as LaborBookTimeEntry
    },
    onSuccess: (entry) => {
      queryClient.invalidateQueries({ queryKey: ['labor-book-time'] })
      setCreateState(emptyCreateState)
      lastDecodedVin.current = ''
      setIsCreating(false)
      toast.success(`${entry.operation_name} book time created`)
    },
    onError: (err: unknown) => {
      toast.error(errorMessage(err, 'Failed to create labor book time'))
    },
  })

  const decodeVinMutation = useMutation({
    mutationFn: async (vin: string) => {
      const response = await api.get(`/customers/vin/decode/${encodeURIComponent(vin.trim().toUpperCase())}`, {
        params: createState.vehicle_year.trim() ? { model_year: createState.vehicle_year.trim() } : undefined,
      })
      return response.data as VinDecodeResult
    },
    onSuccess: (decoded) => {
      if (decoded.error_text && !decoded.make && !decoded.model) {
        toast.error(decoded.error_text)
        return
      }
      setCreateState((prev) => ({
        ...prev,
        vin_sample: decoded.vin || prev.vin_sample,
        vehicle_year: decoded.year ? String(decoded.year) : prev.vehicle_year,
        vehicle_make: decoded.make || prev.vehicle_make,
        vehicle_model: decoded.model || prev.vehicle_model,
        vehicle_type: decoded.vehicle_type || prev.vehicle_type,
        body_class: decoded.body_class || prev.body_class,
        fuel_type: decoded.fuel_type || prev.fuel_type,
        engine_cylinders: decoded.engine_cylinders ? String(decoded.engine_cylinders) : prev.engine_cylinders,
        engine_displacement_l: decoded.engine_displacement_l ? String(decoded.engine_displacement_l) : prev.engine_displacement_l,
        gvwr: decoded.gvwr || prev.gvwr,
      }))
      lastDecodedVin.current = (decoded.vin || '').trim().toUpperCase()
      toast.success('VIN decoded into truck scope')
    },
    onError: (err: unknown) => {
      toast.error(errorMessage(err, 'Failed to decode VIN'))
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: EditState }) => {
      const response = await api.patch(`/labor-book-time/${id}`, {
        operation_name: data.operation_name.trim(),
        operation_description: data.operation_description.trim() || null,
        normalized_hours: Number(data.normalized_hours),
      })
      return response.data as LaborBookTimeEntry
    },
    onSuccess: (entry) => {
      queryClient.invalidateQueries({ queryKey: ['labor-book-time'] })
      setEditingId(null)
      toast.success(`${entry.operation_name} book time updated`)
    },
    onError: (err: unknown) => {
      toast.error(errorMessage(err, 'Failed to update labor book time'))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/labor-book-time/${id}`)
      return id
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['labor-book-time'] })
      toast.success('Labor book time removed')
    },
    onError: (err: unknown) => {
      toast.error(errorMessage(err, 'Failed to remove labor book time'))
    },
  })

  const startEdit = (entry: LaborBookTimeEntry) => {
    setEditingId(entry.id)
    setEditState({
      operation_name: entry.operation_name,
      operation_description: entry.operation_description || '',
      normalized_hours: entry.normalized_hours,
    })
  }

  const saveEdit = () => {
    if (!editingId) return
    const hours = Number(editState.normalized_hours)
    if (!editState.operation_name.trim()) {
      toast.error('Operation name is required')
      return
    }
    if (!Number.isFinite(hours) || hours <= 0) {
      toast.error('Book hours must be greater than zero')
      return
    }
    updateMutation.mutate({ id: editingId, data: editState })
  }

  const removeEntry = (entry: LaborBookTimeEntry) => {
    if (!window.confirm(`Remove "${entry.operation_name}" from Labor Book Time?`)) return
    deleteMutation.mutate(entry.id)
  }

  const saveCreate = () => {
    const hours = Number(createState.normalized_hours)
    const year = Number(createState.vehicle_year)
    if (!createState.operation_name.trim()) {
      toast.error('Service name is required')
      return
    }
    if (!Number.isFinite(hours) || hours <= 0) {
      toast.error('Book hours must be greater than zero')
      return
    }
    if (!Number.isInteger(year) || year < 1900 || !createState.vehicle_make.trim() || !createState.vehicle_model.trim()) {
      toast.error('Year, make, and model are required')
      return
    }
    createMutation.mutate(createState)
  }

  const decodeVin = () => {
    const vin = createState.vin_sample.trim()
    if (vin.length < 11) {
      toast.error('Enter at least 11 VIN characters to decode')
      return
    }
    decodeVinMutation.mutate(vin)
  }

  const handleVinSampleChange = (value: string) => {
    const vin = value.toUpperCase()
    setCreateState((prev) => ({ ...prev, vin_sample: vin }))
    const trimmedVin = vin.trim()
    if (trimmedVin.length === 17 && trimmedVin !== lastDecodedVin.current) {
      decodeVinMutation.mutate(trimmedVin)
    }
  }

  return (
    <div className="db-labor-book-time flex min-h-full flex-col gap-5 text-zinc-100">
      <div className="db-labor-book-time__summary rounded-2xl border border-zinc-700/50 bg-zinc-900/80 p-5 shadow-xl shadow-black/20">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.22em] text-[var(--accent-400)]">
              <Clock3 className="h-4 w-4" />
              Labor Book Time
            </div>
            <h1 className="text-2xl font-bold text-white">Shop labor library</h1>
            <p className="mt-2 max-w-2xl text-sm text-zinc-400">
              Manage reusable labor names and book hours learned from the price builder. These entries feed future repair-order labor searches; they do not appear in customer services.
            </p>
          </div>

          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-950/50 px-4 py-3">
                <div className="text-xl font-black text-white">{stats.count}</div>
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-zinc-500">Entries</div>
              </div>
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-950/50 px-4 py-3">
                <div className="text-xl font-black text-white">{stats.totalHours.toFixed(1)}</div>
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-zinc-500">Book hrs</div>
              </div>
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-950/50 px-4 py-3">
                <div className="text-xl font-black text-white">{stats.totalUses}</div>
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-zinc-500">Uses</div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsCreating((value) => !value)}
              className="db-labor-book-time__primary-action flex w-full items-center justify-center gap-2 rounded-xl border border-[var(--accent-500)]/40 bg-[var(--accent-500)] px-4 py-3 text-sm font-bold text-white transition hover:bg-[var(--accent-600)]"
            >
              {isCreating ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
              {isCreating ? 'Close form' : 'New book time'}
            </button>
          </div>
        </div>

        <div className="db-labor-book-time__search mt-5 flex items-center gap-3 rounded-xl border border-zinc-700/70 bg-zinc-950/60 px-3 py-2">
          <Search className="h-4 w-4 text-zinc-500" />
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search labor, vehicle, or operation key..."
            className="h-10 flex-1 bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
          />
          {searchQuery ? (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="rounded-lg p-2 text-zinc-500 transition hover:bg-zinc-800 hover:text-zinc-200"
              aria-label="Clear search"
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      </div>

      {isCreating ? (
        <div className="rounded-2xl border border-[var(--accent-500)]/30 bg-zinc-900/90 p-5 shadow-xl shadow-black/20">
          <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.22em] text-[var(--accent-400)]">New Labor Book Time</div>
              <h2 className="mt-1 text-lg font-bold text-white">Create truck-specific book time</h2>
            </div>
            <div className="rounded-full border border-zinc-700 bg-zinc-950/70 px-3 py-1 text-xs font-semibold text-zinc-400">
              Not a customer vehicle
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_1.3fr]">
            <div className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-950/50 p-4">
              <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-zinc-500">Service</div>
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-zinc-400">Service / labor name</span>
                <input
                  value={createState.operation_name}
                  onChange={(event) => setCreateState((prev) => ({ ...prev, operation_name: event.target.value }))}
                  placeholder="Water Pump Replacement"
                  className="h-11 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-zinc-400">Book hours</span>
                <input
                  value={createState.normalized_hours}
                  onChange={(event) => setCreateState((prev) => ({ ...prev, normalized_hours: event.target.value }))}
                  type="number"
                  min="0.01"
                  step="0.25"
                  placeholder="8.00"
                  className="h-11 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-zinc-400">Source notes</span>
                <textarea
                  value={createState.operation_description}
                  onChange={(event) => setCreateState((prev) => ({ ...prev, operation_description: event.target.value }))}
                  placeholder="Verified from motor information system or historical shop data"
                  rows={4}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                />
              </label>
            </div>

            <div className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-950/50 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                <label className="block flex-1">
                  <span className="mb-1 block text-xs font-semibold text-zinc-400">VIN helper</span>
                  <input
                    value={createState.vin_sample}
                    onChange={(event) => handleVinSampleChange(event.target.value)}
                    placeholder="Optional VIN or partial VIN"
                    className="h-11 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm uppercase text-white outline-none focus:border-[var(--accent-400)]"
                  />
                </label>
                <button
                  type="button"
                  onClick={decodeVin}
                  disabled={decodeVinMutation.isPending}
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-zinc-700 px-4 text-sm font-semibold text-zinc-200 transition hover:border-[var(--accent-400)] hover:text-white disabled:opacity-50"
                >
                  {decodeVinMutation.isPending ? <Spinner size="xs" /> : <Search className="h-4 w-4" />}
                  Decode
                </button>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-zinc-400">Year</span>
                  <input
                    value={createState.vehicle_year}
                    onChange={(event) => setCreateState((prev) => ({ ...prev, vehicle_year: event.target.value }))}
                    placeholder="2020"
                    className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-zinc-400">Make</span>
                  <input
                    value={createState.vehicle_make}
                    onChange={(event) => setCreateState((prev) => ({ ...prev, vehicle_make: event.target.value }))}
                    placeholder="Freightliner"
                    className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-zinc-400">Model</span>
                  <input
                    value={createState.vehicle_model}
                    onChange={(event) => setCreateState((prev) => ({ ...prev, vehicle_model: event.target.value }))}
                    placeholder="Cascadia"
                    className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                  />
                </label>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-zinc-400">Engine</span>
                  <input
                    value={createState.engine}
                    onChange={(event) => setCreateState((prev) => ({ ...prev, engine: event.target.value }))}
                    placeholder="Detroit DD15"
                    className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-zinc-400">Fuel</span>
                  <input
                    value={createState.fuel_type}
                    onChange={(event) => setCreateState((prev) => ({ ...prev, fuel_type: event.target.value }))}
                    placeholder="Diesel"
                    className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-zinc-400">Displacement</span>
                  <input
                    value={createState.engine_displacement_l}
                    onChange={(event) => setCreateState((prev) => ({ ...prev, engine_displacement_l: event.target.value }))}
                    placeholder="14.8"
                    className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                  />
                </label>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-zinc-400">Vehicle type</span>
                  <input
                    value={createState.vehicle_type}
                    onChange={(event) => setCreateState((prev) => ({ ...prev, vehicle_type: event.target.value }))}
                    placeholder="Truck"
                    className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-zinc-400">Body class</span>
                  <input
                    value={createState.body_class}
                    onChange={(event) => setCreateState((prev) => ({ ...prev, body_class: event.target.value }))}
                    placeholder="Truck-Tractor"
                    className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-zinc-400">GVWR</span>
                  <input
                    value={createState.gvwr}
                    onChange={(event) => setCreateState((prev) => ({ ...prev, gvwr: event.target.value }))}
                    placeholder="Class 8"
                    className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm text-white outline-none focus:border-[var(--accent-400)]"
                  />
                </label>
              </div>

              <div className="flex justify-end gap-2 border-t border-zinc-800 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setCreateState(emptyCreateState)
                    lastDecodedVin.current = ''
                    setIsCreating(false)
                  }}
                  className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-300 transition hover:border-zinc-500 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={saveCreate}
                  disabled={createMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-lg bg-[var(--accent-500)] px-4 py-2 text-sm font-bold text-white transition hover:bg-[var(--accent-600)] disabled:opacity-50"
                >
                  {createMutation.isPending ? <Spinner size="xs" /> : <Plus className="h-4 w-4" />}
                  Save book time
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="db-labor-book-time__ledger overflow-hidden rounded-2xl border border-zinc-700/50 bg-zinc-900/80 shadow-xl shadow-black/20">
        <div className="grid grid-cols-[minmax(0,1.5fr)_120px_minmax(140px,0.8fr)_120px_112px] gap-3 border-b border-zinc-800 bg-zinc-950/60 px-5 py-3 text-[11px] font-bold uppercase tracking-[0.18em] text-zinc-500 max-lg:hidden">
          <span>Labor</span>
          <span>Book hours</span>
          <span>Vehicle scope</span>
          <span>Last used</span>
          <span className="text-right">Actions</span>
        </div>

        {isLoading ? (
          <div className="p-8 flex justify-center"><LoadingLine className="text-zinc-500">Loading labor book time…</LoadingLine></div>
        ) : entries.length === 0 ? (
          <div className="p-8 text-center">
            <Clock3 className="mx-auto mb-3 h-8 w-8 text-zinc-600" />
            <p className="text-sm font-semibold text-zinc-300">No labor book time entries yet</p>
            <p className="mt-1 text-sm text-zinc-500">
              Add labor from the price builder and enter book hours once. It will appear here for management.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800/80">
            {entries.map((entry) => {
              const isEditing = editingId === entry.id
              const scope = vehicleScopeLabel(entry)
              return (
                <div
                  key={entry.id}
                  className="db-labor-book-time__ledger-row grid gap-3 px-5 py-4 transition hover:bg-zinc-800/30 lg:grid-cols-[minmax(0,1.5fr)_120px_minmax(140px,0.8fr)_120px_112px] lg:items-center"
                >
                  <div className="min-w-0">
                    {isEditing ? (
                      <div className="space-y-2">
                        <input
                          value={editState.operation_name}
                          onChange={(event) => setEditState((prev) => ({ ...prev, operation_name: event.target.value }))}
                          className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-sm font-semibold text-white outline-none focus:border-[var(--accent-400)]"
                        />
                        <input
                          value={editState.operation_description}
                          onChange={(event) => setEditState((prev) => ({ ...prev, operation_description: event.target.value }))}
                          placeholder="Optional description"
                          className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950/80 px-3 text-xs text-zinc-300 outline-none focus:border-[var(--accent-400)]"
                        />
                      </div>
                    ) : (
                      <>
                        <div className="truncate text-sm font-semibold text-white">{entry.operation_name}</div>
                        <div className="mt-1 truncate text-xs text-zinc-500">
                          {entry.operation_description || entry.operation_key}
                        </div>
                      </>
                    )}
                  </div>

                  <div>
                    {isEditing ? (
                      <input
                        value={editState.normalized_hours}
                        onChange={(event) => setEditState((prev) => ({ ...prev, normalized_hours: event.target.value }))}
                        type="number"
                        min="0.01"
                        step="0.25"
                        className="h-10 w-28 rounded-lg border border-zinc-700 bg-zinc-950 px-3 text-right text-sm font-semibold text-white outline-none focus:border-[var(--accent-400)]"
                      />
                    ) : (
                      <div className="inline-flex rounded-full bg-[var(--accent-500)]/10 px-3 py-1 text-sm font-bold text-[var(--accent-300)]">
                        {Number(entry.normalized_hours).toFixed(2)} hr
                      </div>
                    )}
                  </div>

                  <div className="min-w-0 text-xs text-zinc-400">
                    <div className="truncate font-medium text-zinc-300">{scope.primary}</div>
                    <div className="mt-1 truncate text-zinc-600">{scope.secondary}</div>
                  </div>

                  <div className="text-xs text-zinc-500">
                    <div>{formatDate(entry.last_used_at)}</div>
                    <div className="mt-1">{entry.usage_count} use{entry.usage_count === 1 ? '' : 's'}</div>
                  </div>

                  <div className="flex items-center justify-end gap-2">
                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="rounded-lg border border-zinc-700 p-2 text-zinc-400 transition hover:border-zinc-500 hover:text-white"
                          aria-label="Cancel edit"
                        >
                          <X className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={saveEdit}
                          disabled={updateMutation.isPending}
                          className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-2 text-emerald-300 transition hover:bg-emerald-500/20 disabled:opacity-50"
                          aria-label="Save labor book time"
                        >
                          <Check className="h-4 w-4" />
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => startEdit(entry)}
                          className="rounded-lg border border-zinc-700 p-2 text-zinc-400 transition hover:border-[var(--accent-400)]/60 hover:text-[var(--accent-300)]"
                          aria-label={`Edit ${entry.operation_name}`}
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => removeEntry(entry)}
                          disabled={deleteMutation.isPending}
                          className="rounded-lg border border-red-500/30 p-2 text-red-300 transition hover:bg-red-500/10 disabled:opacity-50"
                          aria-label={`Remove ${entry.operation_name}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
