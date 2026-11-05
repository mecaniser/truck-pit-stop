import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link2 } from 'lucide-react'
import { ControlButton } from '@/components/ui/Controls'
import PlatformSelect from '@/components/PlatformSelect'
import api from '@/lib/api'
import { assetTypeLabel } from './assetIdentity'
import type { BoardTruck, EquipmentType } from './types'
import './assetAttachment.css'

export default function AssetAttachment({ asset, assets, onOpen }: { asset: BoardTruck; assets: BoardTruck[]; onOpen: (id: string) => void }) {
  const qc = useQueryClient()
  const [baseline, setBaseline] = useState({ type: asset.equipment_type || 'unknown', attached: asset.attached_asset?.id || null })
  const [kind, setKind] = useState<EquipmentType>(baseline.type)
  const [selected, setSelected] = useState(baseline.attached || '')
  const [saved, setSaved] = useState(false)
  const counterpart = asset.attached_asset
  const opposite = kind === 'tractor' ? 'trailer' : kind === 'trailer' ? 'tractor' : null
  const candidates = assets.filter(other => other.id !== asset.id && other.equipment_type === opposite && (!other.attached_asset || other.id === counterpart?.id))
  const dirty = kind !== baseline.type || (selected || null) !== baseline.attached
  const changedRemotely = baseline.type !== (asset.equipment_type || 'unknown') || baseline.attached !== (asset.attached_asset?.id || null)
  const save = useMutation({
    mutationFn: () => api.put<BoardTruck>(`/fleet/trucks/${asset.id}/asset-settings`, {
      equipment_type: kind, attached_vehicle_id: selected || null,
      expected_equipment_type: baseline.type, expected_attached_vehicle_id: baseline.attached,
    }),
    onSuccess: async ({ data }) => {
      setBaseline({ type: data.equipment_type || 'unknown', attached: data.attached_asset?.id || null })
      setKind(data.equipment_type || 'unknown'); setSelected(data.attached_asset?.id || ''); setSaved(true)
      await Promise.all([qc.invalidateQueries({ queryKey: ['fleet-board'] }), qc.invalidateQueries({ queryKey: ['fleet-truck'] })])
    },
    onError: () => { void qc.invalidateQueries({ queryKey: ['fleet-board'] }); void qc.invalidateQueries({ queryKey: ['fleet-truck'] }) },
  })
  return <section className="fleet-reference-section asset-attachment" aria-label="Equipment settings">
    <div className="fleet-reference-heading"><h3 className="dmap-side-h">Equipment</h3>
      {counterpart && <ControlButton controlKind="action" type="button" className="dbtn dbtn-ghost" onClick={() => onOpen(counterpart.id)}><Link2 size={15} />{assetTypeLabel(counterpart.equipment_type)} {counterpart.unit_number || 'details'}</ControlButton>}
    </div>
    <div className="asset-attachment-controls">
      <label><span>Equipment type</span><PlatformSelect aria-label="Equipment type" value={kind} disabled={save.isPending || !!counterpart} onChange={event => { const next = event.target.value as EquipmentType; setKind(next); setSelected(next === baseline.type ? baseline.attached || '' : ''); setSaved(false) }}>
        <option value="unknown">Unclassified</option><option value="tractor">Tractor</option><option value="trailer">Trailer</option><option value="other">Other equipment</option>
      </PlatformSelect></label>
      {opposite && <label><span>{kind === 'trailer' ? 'Assigned tractor' : 'Attached trailer'}</span><PlatformSelect aria-label={kind === 'trailer' ? 'Assigned tractor' : 'Attached trailer'} value={selected} disabled={save.isPending} onChange={event => { setSelected(event.target.value); setSaved(false) }}>
        <option value="" disabled={kind === 'trailer' || !!counterpart}> {kind === 'trailer' ? 'Select tractor…' : 'No trailer'}</option>
        {candidates.map(other => <option key={other.id} value={other.id}>{other.unit_number || 'Unit not recorded'} · {other.owner_company_name || other.fleet_company_name || other.make}</option>)}
      </PlatformSelect></label>}
    </div>
    {kind === 'trailer' && <p>A tractor is required while this trailer is on the fleet. Reassign it here, or remove it from the fleet to release the tractor.</p>}
    {kind === 'tractor' && counterpart && <p>Reassign the trailer to another tractor, or remove it from the fleet before changing this attachment.</p>}
    <ControlButton controlKind="action" type="button" className="dbtn dbtn-yellow" disabled={save.isPending || changedRemotely || !dirty || (kind === 'trailer' && !selected)} onClick={() => { setSaved(false); save.mutate() }}>{save.isPending ? 'Saving…' : 'Save equipment'}</ControlButton>
    {saved && <p role="status">Equipment saved.</p>}
    {changedRemotely && !save.isPending ? <p role="alert">Equipment changed while these details were open. Close and reopen details to load the current assignment.</p> : save.isError && <p role="alert">Equipment settings could not be saved. Close and reopen details to check the current assignment, then try again.</p>}
  </section>
}
