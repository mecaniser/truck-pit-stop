import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../../stores/authStore'
import api from '../../lib/api'
import { Vehicle } from '../../types'

const editVehicleSchema = z.object({
  license_plate: z.string().optional(),
})

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

type EditVehicleData = z.infer<typeof editVehicleSchema>
type AddVehicleData = z.infer<typeof addVehicleSchema>

function EditVehicleForm({ vehicle, onClose }: { vehicle: Vehicle; onClose: () => void }) {
  const queryClient = useQueryClient()
  
  const { register, handleSubmit, formState: { isDirty } } = useForm<EditVehicleData>({
    resolver: zodResolver(editVehicleSchema),
    defaultValues: {
      license_plate: vehicle.license_plate || '',
    },
  })

  const mutation = useMutation({
    mutationFn: async (data: EditVehicleData) => {
      const response = await api.patch(`/vehicles/${vehicle.id}`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      onClose()
    },
  })

  const inputClasses = "w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500 text-sm"

  return (
    <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4">
      <div className="bg-white/5 p-3 rounded-lg mb-4">
        <p className="text-white font-medium">{vehicle.year} {vehicle.make} {vehicle.model}</p>
        <div className="flex flex-wrap gap-x-4 text-xs text-gray-500 mt-1">
          {vehicle.vin && <span>VIN: {vehicle.vin}</span>}
          {vehicle.color && <span>Color: {vehicle.color}</span>}
          {vehicle.mileage && <span>{vehicle.mileage.toLocaleString()} mi</span>}
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">Tag / License Plate</label>
        <input {...register('license_plate')} className={inputClasses} placeholder="ABC-1234" />
      </div>

      {mutation.isError && (
        <p className="text-sm text-red-400">Failed to update vehicle</p>
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!isDirty || mutation.isPending}
          className="flex-1 px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {mutation.isPending ? 'Saving...' : 'Save Changes'}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white text-sm font-medium rounded-lg transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

function AddVehicleForm({ onClose }: { onClose: () => void }) {
  const { user } = useAuthStore()
  const queryClient = useQueryClient()
  
  const { register, handleSubmit, formState: { errors } } = useForm<AddVehicleData>({
    resolver: zodResolver(addVehicleSchema),
  })

  const mutation = useMutation({
    mutationFn: async (data: AddVehicleData) => {
      const response = await api.post('/vehicles', {
        ...data,
        customer_id: user?.customer_id,
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      onClose()
    },
  })

  const inputClasses = (hasError: boolean) => {
    const base = "w-full px-3 py-2 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 text-sm"
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
          <label className="block text-xs font-medium text-gray-400 mb-1">Make *</label>
          <input {...register('make')} className={inputClasses(!!errors.make)} placeholder="Peterbilt" />
          {errors.make && <p className="text-xs text-red-400 mt-1">{errors.make.message}</p>}
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">Model *</label>
          <input {...register('model')} className={inputClasses(!!errors.model)} placeholder="579" />
          {errors.model && <p className="text-xs text-red-400 mt-1">{errors.model.message}</p>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">Year</label>
          <input {...register('year')} type="number" className={inputClasses(!!errors.year)} placeholder="2022" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">VIN</label>
          <input {...register('vin')} className={inputClasses(false)} placeholder="1HTMMAAM45H123456" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">License Plate</label>
          <input {...register('license_plate')} className={inputClasses(false)} placeholder="ABC-1234" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">Color</label>
          <input {...register('color')} className={inputClasses(false)} placeholder="Red" />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">Mileage</label>
        <input {...register('mileage')} type="number" className={inputClasses(false)} placeholder="150000" />
      </div>

      {mutation.isError && (
        <p className="text-sm text-red-400">Failed to add vehicle</p>
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="flex-1 px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {mutation.isPending ? 'Adding...' : 'Add Vehicle'}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white text-sm font-medium rounded-lg transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

export default function VehiclesCard() {
  const [editingVehicle, setEditingVehicle] = useState<Vehicle | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)

  const { data: vehicles, isLoading } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles')
      return response.data
    },
  })

  return (
    <div className="bg-white/5 rounded-xl p-6 border border-white/10 h-fit">
      <div className="flex items-center gap-2 mb-4">
        <svg className="w-5 h-5 text-cyan-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
        </svg>
        <h2 className="text-lg font-semibold text-white">My Vehicles</h2>
      </div>
      <p className="text-gray-400 text-sm mb-4">
        Vehicles on file for service. You can update plate, color, and mileage.
      </p>

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-500"></div>
        </div>
      ) : editingVehicle ? (
        <EditVehicleForm vehicle={editingVehicle} onClose={() => setEditingVehicle(null)} />
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
                  <span className="text-lg shrink-0">🚛</span>
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
                <button
                  onClick={() => setEditingVehicle(vehicle)}
                  className="p-2 text-gray-400 hover:text-amber-400 transition-colors shrink-0"
                  title="Edit vehicle"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </button>
              </div>
            ))
          ) : (
            <p className="text-gray-400 text-sm py-4 text-center">No vehicles on file yet.</p>
          )}

          <button
            onClick={() => setShowAddForm(true)}
            className="w-full py-2.5 border border-dashed border-white/20 hover:border-cyan-500/50 text-gray-400 hover:text-cyan-400 rounded-lg transition-colors flex items-center justify-center gap-2 text-sm"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add New Vehicle
          </button>
        </div>
      )}
    </div>
  )
}
