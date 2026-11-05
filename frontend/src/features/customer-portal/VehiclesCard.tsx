import { ControlInput, ControlButton } from '@/components/ui/Controls'
import { useRef, useState } from 'react'
import { Spinner } from '@/components/ui'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../../stores/authStore'
import api from '../../lib/api'
import { Vehicle, VINDecodeResult } from '../../types'
import { Truck } from 'lucide-react'
import toast from 'react-hot-toast'
import { isAxiosError } from 'axios'
import CustomerVehicleEditor from './CustomerVehicleEditor'

const addVehicleSchema = z.object({
  make: z.string().min(1, 'Make is required'),
  model: z.string().min(1, 'Model is required'),
  year: z.coerce.number().int().min(1900).max(new Date().getFullYear() + 1).optional().nullable(),
  vin: z.string().optional(),
  license_plate: z.string().optional(),
  color: z.string().optional(),
  mileage: z.coerce.number().int().min(0).optional().nullable(),
  notes: z.string().optional(),
})

type AddVehicleData = z.infer<typeof addVehicleSchema>

function AddVehicleForm({ onClose }: { onClose: () => void }) {
  const { user } = useAuthStore()
  const queryClient = useQueryClient()
  
  const { register, handleSubmit, formState: { errors }, setValue } = useForm<z.input<typeof addVehicleSchema>, unknown, AddVehicleData>({
    resolver: zodResolver(addVehicleSchema),
  })
  const [isDecodingVin, setIsDecodingVin] = useState(false)
  const lastDecodedVin = useRef('')

  const decodeVin = async (rawVin: string) => {
    const vin = rawVin.trim().toUpperCase()
    if (vin.length !== 17 || vin === lastDecodedVin.current) return

    setIsDecodingVin(true)
    try {
      const response = await api.get<VINDecodeResult>(`/customers/vin/decode/${encodeURIComponent(vin)}`)
      const result = response.data
      if (result.error_code && result.error_code !== '0') {
        toast.error(result.error_text || 'Failed to decode VIN')
        return
      }

      setValue('vin', result.vin || vin, { shouldDirty: true })
      if (result.make) setValue('make', result.make, { shouldDirty: true, shouldValidate: true })
      if (result.model) setValue('model', result.model, { shouldDirty: true, shouldValidate: true })
      if (result.year) setValue('year', result.year, { shouldDirty: true, shouldValidate: true })
      lastDecodedVin.current = vin
      const decodedLabel = [result.year, result.make, result.model].filter(Boolean).join(' ')
      toast.success(decodedLabel ? `VIN decoded: ${decodedLabel}` : 'VIN decoded')
    } catch (error: unknown) {
      toast.error(isAxiosError(error) ? error.response?.data?.detail || 'Failed to decode VIN' : 'Failed to decode VIN')
    } finally {
      setIsDecodingVin(false)
    }
  }

  const handleVinChange = (value: string) => {
    const vin = value.toUpperCase()
    setValue('vin', vin, { shouldDirty: true })
    if (vin.trim().length === 17) {
      void decodeVin(vin)
    }
  }

  const mutation = useMutation({
    mutationFn: async (data: AddVehicleData) => {
      // Use nested endpoint under customer
      const response = await api.post(`/customers/${user?.customer_id}/vehicles`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customerVehicles', user?.customer_id, user?.tenant_id, user?.id] })
      onClose()
    },
  })

  const inputClasses = (hasError: boolean) => {
    const base = "w-full px-3 py-2 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 text-base"
    return hasError
      ? `${base} border-red-500 focus:ring-red-500`
      : `${base} border-white/20 focus:ring-amber-500`
  }

  return (
    <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4">
      <p className="text-sm text-gray-400 mb-4">
        Add a new vehicle for future service appointments.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="vehicle-make" className="block text-xs font-medium text-gray-400 mb-1">Make *</label>
          <ControlInput {...register('make')} id="vehicle-make" className={inputClasses(!!errors.make)} placeholder="Peterbilt" />
          {errors.make && <p className="text-xs text-red-400 mt-1">{errors.make.message}</p>}
        </div>
        <div>
          <label htmlFor="vehicle-model" className="block text-xs font-medium text-gray-400 mb-1">Model *</label>
          <ControlInput {...register('model')} id="vehicle-model" className={inputClasses(!!errors.model)} placeholder="579" />
          {errors.model && <p className="text-xs text-red-400 mt-1">{errors.model.message}</p>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="vehicle-year" className="block text-xs font-medium text-gray-400 mb-1">Year</label>
          <ControlInput {...register('year')} id="vehicle-year" type="number" className={inputClasses(!!errors.year)} placeholder="2022" />
        </div>
        <div>
          <label htmlFor="vehicle-vin" className="block text-xs font-medium text-gray-400 mb-1">VIN</label>
          <div className="relative">
            <ControlInput
              {...register('vin', { onChange: (event) => handleVinChange(event.target.value) })} id="vehicle-vin"
              className={`${inputClasses(false)} pr-9 uppercase`}
              placeholder="1HTMMAAM45H123456"
              maxLength={17}
            />
            {isDecodingVin && <Spinner size="xs" className="absolute right-3 top-1/2 -translate-y-1/2" />}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="vehicle-license_plate" className="block text-xs font-medium text-gray-400 mb-1">License Plate</label>
          <ControlInput {...register('license_plate')} id="vehicle-license_plate" className={inputClasses(false)} placeholder="ABC-1234" />
        </div>
        <div>
          <label htmlFor="vehicle-color" className="block text-xs font-medium text-gray-400 mb-1">Color</label>
          <ControlInput {...register('color')} id="vehicle-color" className={inputClasses(false)} placeholder="Red" />
        </div>
      </div>

      <div>
        <label htmlFor="vehicle-mileage" className="block text-xs font-medium text-gray-400 mb-1">Mileage</label>
        <ControlInput {...register('mileage')} id="vehicle-mileage" type="number" className={inputClasses(false)} placeholder="150000" />
      </div>

      {mutation.isError && (
        <p className="text-sm text-red-400">Failed to add vehicle</p>
      )}

      <div className="flex gap-2">
        <ControlButton
          type="submit"
          disabled={mutation.isPending}
          className="flex-1 px-4  bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {mutation.isPending ? 'Adding...' : 'Add Vehicle'}
        </ControlButton>
        <ControlButton
          type="button"
          onClick={onClose}
          className="px-4  bg-white/10 hover:bg-white/20 text-white text-sm font-medium rounded-lg transition-colors"
        >
          Cancel
        </ControlButton>
      </div>
    </form>
  )
}

export default function VehiclesCard({ embedded = false }: { embedded?: boolean }) {
  const { user, authSessionEpoch } = useAuthStore()
  return <VehiclesCardContent embedded={embedded} key={`${user?.id}:${user?.tenant_id}:${user?.customer_id}:${authSessionEpoch}`}/>
}

function VehiclesCardContent({ embedded = false }: { embedded?: boolean }) {
  const { user } = useAuthStore()
  const [editingVehicleId, setEditingVehicleId] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)

  const { data: vehicles, isLoading, isError, refetch, isFetching } = useQuery<Vehicle[]>({
    queryKey: ['customerVehicles', user?.customer_id, user?.tenant_id, user?.id],
    queryFn: async () => {
      if (!user?.customer_id) return []
      // Use nested endpoint under customer
      const response = await api.get(`/customers/${user.customer_id}/vehicles`)
      return response.data
    },
    enabled: !!user?.customer_id,
  })

  const editingVehicle = isError ? undefined : vehicles?.find(vehicle => vehicle.id === editingVehicleId)

  return (
    <div className={embedded ? 'space-y-4' : 'bg-white/5 rounded-xl p-6 border border-white/10 h-fit'}>
      <div className="flex items-center gap-2 mb-4">
        <svg className="w-5 h-5 text-cyan-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
        </svg>
        <h2 className="text-lg font-semibold text-white">Vehicles</h2>
      </div>
      <p className="text-gray-400 text-sm mb-4">
        Vehicles on file for service. You can update unit numbers, license plates, colors, and notes. VIN changes require the shop.
      </p>

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Spinner size="lg" />
        </div>
      ) : isError ? (
        <div role="alert" className="space-y-3 text-sm text-red-300"><p>Unable to load your vehicles.</p><ControlButton type="button" disabled={isFetching} onClick={() => void refetch()} className="underline">Retry loading vehicles</ControlButton></div>
      ) : editingVehicle ? (
        <CustomerVehicleEditor key={`${user?.id}:${user?.tenant_id}:${user?.customer_id}:${editingVehicle.id}`} vehicle={editingVehicle} onClose={() => setEditingVehicleId(null)} />
      ) : showAddForm ? (
        <AddVehicleForm onClose={() => setShowAddForm(false)} />
      ) : (
        <div className="space-y-3">
          {vehicles && vehicles.length > 0 ? (
            vehicles.map((vehicle) => (
              <div
                key={vehicle.id}
                className="flex items-center justify-between p-3 bg-white/5 rounded-lg border border-white/10"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Truck className="w-5 h-5 text-cyan-200 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-white font-medium text-sm truncate">
                      {vehicle.year} {vehicle.make} {vehicle.model}
                    </p>
                    <p className="text-xs text-gray-400 truncate">
                      {vehicle.license_plate && `Plate: ${vehicle.license_plate}`}
                      {vehicle.license_plate && vehicle.mileage && ' • '}
                      {vehicle.mileage && `${vehicle.mileage.toLocaleString()} mi`}
                      {!vehicle.license_plate && !vehicle.mileage && 'No details yet'}
                    </p>
                  </div>
                </div>
                <ControlButton controlKind="icon"
                  onClick={() => setEditingVehicleId(vehicle.id)}
                  className="p-2 text-gray-400 hover:text-amber-400 transition-colors shrink-0"
                  title="Edit vehicle"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </ControlButton>
              </div>
            ))
          ) : (
            <p className="text-gray-400 text-sm py-4 text-center">No vehicles on file yet.</p>
          )}

          <ControlButton
            onClick={() => setShowAddForm(true)}
            className="w-full  border border-dashed border-white/20 hover:border-cyan-500/50 text-gray-400 hover:text-cyan-400 rounded-lg transition-colors flex items-center justify-center gap-2 text-sm"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add New Vehicle
          </ControlButton>
        </div>
      )}
    </div>
  )
}
