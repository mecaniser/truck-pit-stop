import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link2, Pencil, Unlink } from 'lucide-react'
import { ControlButton } from '@/components/ui/Controls'
import PlatformSelect from '@/components/PlatformSelect'
import api from '@/lib/api'
import { assetTypeLabel } from './assetIdentity'
import type { BoardTruck, EquipmentType } from './types'
import './assetAttachment.css'

export default function AssetAttachment({ asset, assets, onOpen }: { asset: BoardTruck; assets: BoardTruck[]; onOpen: (id: string) => void }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [kind, setKind] = useState<EquipmentType>(asset.equipment_type || 'unknown')
  const [selected, setSelected] = useState('')
  const counterpart = asset.attached_asset
  const opposite = asset.equipment_type === 'tractor' ? 'trailer' : asset.equipment_type === 'trailer' ? 'tractor' : null
  const candidates = assets.filter(other => other.id !== asset.id && other.equipment_type === opposite && !other.attached_asset)
  const refresh = async () => {
    await Promise.all([qc.invalidateQueries({ queryKey: ['fleet-board'] }), qc.invalidateQueries({ queryKey: ['fleet-truck'] })])
  }
  const classify = useMutation({
    mutationFn: () => api.patch(`/fleet/trucks/${asset.id}`, { equipment_type: kind }),
    onSuccess: async () => { setEditing(false); await refresh() },
  })
  const attach = useMutation({
    mutationFn: (id: string | null) => api.put(`/fleet/trucks/${asset.id}/attachment`, { attached_vehicle_id: id, expected_attached_vehicle_id: counterpart?.id || null }),
    onSuccess: async () => { setSelected(''); await refresh() },
    onError: () => { void refresh() },
  })
  const pending = classify.isPending || attach.isPending
  return <section className="asset-attachment" aria-label="Equipment and attachment">
    <div className="asset-attachment-summary">
      <strong>{assetTypeLabel(asset.equipment_type)}</strong>
      <ControlButton controlKind="action" type="button" className="dbtn dbtn-ghost" disabled={pending || !!counterpart} onClick={() => { setKind(asset.equipment_type || 'unknown'); setEditing(!editing); classify.reset() }}><Pencil size={14} />Change type</ControlButton>
      {counterpart && <>
        <ControlButton controlKind="action" type="button" className="dbtn dbtn-ghost" onClick={() => onOpen(counterpart.id)}><Link2 size={15} />{assetTypeLabel(counterpart.equipment_type)} {counterpart.unit_number || 'details'}</ControlButton>
        <ControlButton controlKind="action" type="button" className="dbtn dbtn-ghost" disabled={pending} onClick={() => attach.mutate(null)}><Unlink size={15} />Detach</ControlButton>
      </>}
      {!counterpart && opposite && <span className="asset-attachment-muted">No {opposite} attached</span>}
    </div>
    {editing && <div className="asset-attachment-controls">
      <PlatformSelect aria-label="Equipment type" value={kind} disabled={pending} onChange={event => setKind(event.target.value as EquipmentType)}>
        <option value="unknown">Unclassified</option><option value="tractor">Tractor</option><option value="trailer">Trailer</option><option value="other">Other equipment</option>
      </PlatformSelect>
      <ControlButton controlKind="action" type="button" className="dbtn dbtn-yellow" disabled={pending || kind === asset.equipment_type} onClick={() => classify.mutate()}>Save type</ControlButton>
    </div>}
    {!counterpart && opposite && <div className="asset-attachment-controls">
      <PlatformSelect aria-label={`Attach ${opposite}`} value={selected} disabled={pending} onChange={event => setSelected(event.target.value)}>
        <option value="">Select {opposite}…</option>
        {candidates.map(other => <option key={other.id} value={other.id}>{other.unit_number || 'Unit not recorded'} · {other.owner_company_name || other.fleet_company_name || other.make}</option>)}
      </PlatformSelect>
      <ControlButton controlKind="action" type="button" className="dbtn dbtn-ghost" disabled={pending || !selected} onClick={() => attach.mutate(selected)}><Link2 size={15} />Attach</ControlButton>
    </div>}
    {!opposite && <p>Set the equipment type to attach a tractor or trailer.</p>}
    {(classify.isError || attach.isError) && <p role="alert">The change could not be saved. Refresh the asset and check its current attachment before trying again.</p>}
  </section>
}
