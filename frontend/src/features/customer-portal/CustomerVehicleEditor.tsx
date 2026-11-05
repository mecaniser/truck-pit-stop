import { useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ControlButton, ControlInput } from '@/components/ui/Controls'
import api from '@/lib/api'
import { isCurrentAuthEpoch, useAuthStore } from '@/stores/authStore'
import type { Vehicle } from '@/types'
import './portal-task-flow.css'

const schema = z.object({
  unit_number: z.string().max(50, 'Use 50 characters or fewer.'),
  license_plate: z.string().max(20, 'Use 20 characters or fewer.'),
  color: z.string().max(50, 'Use 50 characters or fewer.'),
  notes: z.string(),
})
type VehicleLabels = z.infer<typeof schema>

export default function CustomerVehicleEditor({ vehicle, onClose }: { vehicle: Vehicle; onClose: () => void }) {
  const { user, authSessionEpoch } = useAuthStore()
  const session = useRef({ epoch: authSessionEpoch, customerId: user?.customer_id }).current
  const client = useQueryClient()
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const { register, handleSubmit, formState: { errors, isDirty } } = useForm<VehicleLabels>({
    resolver: zodResolver(schema),
    defaultValues: { unit_number: vehicle.unit_number || '', license_plate: vehicle.license_plate || '', color: vehicle.color || '', notes: vehicle.notes || '' },
  })
  const mutation = useMutation({
    retry: false,
    mutationFn: async (labels: VehicleLabels) => {
      if (!mounted.current || !isCurrentAuthEpoch(session.epoch) || !session.customerId) throw new Error('Vehicle editor session changed')
      // Use nested endpoint under customer
      const payload = Object.fromEntries(Object.entries(labels).map(([field, value]) => [field, value || null]))
      return api.put(`/customers/${session.customerId}/vehicles/${vehicle.id}`, payload)
    },
    onSuccess: async () => {
      if (!mounted.current || !isCurrentAuthEpoch(session.epoch)) return
      await Promise.all([
        client.invalidateQueries({ queryKey: ['customerVehicles', session.customerId] }),
        client.invalidateQueries({ queryKey: ['vehicles'] }),
      ])
      if (mounted.current && isCurrentAuthEpoch(session.epoch)) onClose()
    },
  })
  return <form className="cp-root cp-vehicle-editor" aria-label="Edit vehicle" onSubmit={handleSubmit(values => { if (!mutation.isPending) mutation.mutate(values) })}>
    <h2>Edit vehicle</h2>
    <p>{[vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(' ')}</p>
    <fieldset disabled={mutation.isPending}>
      <label className="cp-field">VIN<ControlInput value={vehicle.vin || ''} readOnly aria-describedby="vehicle-vin-help"/></label>
      <p id="vehicle-vin-help">VIN is read-only. Contact the shop to correct it.</p>
      {([['unit_number', 'Unit number'], ['license_plate', 'License plate'], ['color', 'Color']] as const).map(([field, label]) => <label className="cp-field" key={field}>{label}
        <ControlInput {...register(field)} aria-invalid={Boolean(errors[field])}/>
        {errors[field] && <span role="alert">{errors[field]?.message}</span>}
      </label>)}
      <label className="cp-field">Notes<textarea {...register('notes')} rows={3}/></label>
      {mutation.isError && <p role="alert">Couldn’t save changes. Your edits are still here. Please try again.</p>}
      <div className="cp-editor-actions">
        <ControlButton type="submit" className="cp-primary" disabled={!isDirty || mutation.isPending}>{mutation.isPending ? 'Saving…' : 'Save changes'}</ControlButton>
        <ControlButton type="button" className="cp-secondary" onClick={onClose}>Cancel</ControlButton>
      </div>
    </fieldset>
  </form>
}
