import type { Vehicle } from '@/types'
import './customer-workspace.css'

export default function CustomerVehicleFooter({ vehicle, canMerge, onDelete, onMerge, onManage, onEdit }: {
  vehicle: Vehicle
  canMerge: boolean
  onDelete: (vehicle: Vehicle) => void
  onMerge: () => void
  onManage: (vehicle: Vehicle) => void
  onEdit: (vehicle: Vehicle) => void
}) {
  const completeVin = vehicle.vin?.replace(/[\s-]/g, '').length === 17
  return <div className="db-customer-actions db-customer-vehicle-actions">
    <button type="button" className="text-red-600 hover:bg-red-50 rounded-lg" onClick={() => onDelete(vehicle)}>Delete vehicle</button>
    {canMerge && <button type="button" disabled={!completeVin} title={!completeVin ? 'A complete VIN is required to find safe duplicates' : undefined} className="rounded-lg hover:bg-gray-100 disabled:opacity-45 disabled:cursor-not-allowed" onClick={onMerge}>Merge duplicate</button>}
    <button type="button" className="rounded-lg hover:bg-gray-100" onClick={() => onManage(vehicle)}>Manage connections</button>
    <button type="button" className="db-customer-vehicle-actions__edit rounded-lg bg-amber-500 hover:bg-amber-600 text-white" onClick={() => onEdit(vehicle)}>Edit vehicle</button>
  </div>
}
