import { ControlButton } from '@/components/ui/Controls'
import { useRef, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { label, programServices, type Program } from './contract'
import { Reading } from './MaintenanceFields'

type Action = 'edit' | 'evidence' | 'detach' | 'archive' | 'restore' | 'plan'
export default function ProgramRow({ program, selected, editing, historyOpen, onSelect, onHistory, onAction, onOpenOrder }: { program: Program; selected: boolean; editing: boolean; historyOpen: boolean; onSelect: (value: boolean) => void; onHistory: () => void; onAction: (action: Action, trigger: HTMLElement) => void; onOpenOrder?: (id: string) => void }) {
  const [more, setMore] = useState(false); const moreButton = useRef<HTMLButtonElement>(null)
  const closeMore = () => { setMore(false); moreButton.current?.focus({ preventScroll: true }) }
  const extra = (action: Action) => { const trigger = moreButton.current; setMore(false); if (trigger) onAction(action, trigger) }
  const pending = program.work?.state === 'pending_evidence'
  const canOpen = program.work?.can_open && program.work.repair_order_id && onOpenOrder
  const services = programServices(program)
  const canPlan = program.capabilities.can_plan && !program.archived_at && services.length > 0
  return <>
    <div className="db-maintenance__row"><label className="db-maintenance__check"><input type="checkbox" aria-label={`Select ${program.name}`} checked={selected} disabled={editing || !canPlan} onChange={event => onSelect(event.target.checked)} /><strong>{program.name}</strong></label><span className="db-maintenance__state" data-state={program.due.state}>{program.archived_at ? 'Archived' : label(program.due.state)}</span>{program.work && <span>{program.work.state === 'active' ? 'In work' : label(program.work.state)}{program.work.order_number ? ` · ${program.work.order_number}` : ''}</span>}{program.review.required && <strong className="db-maintenance__warning">Review required</strong>}</div>
    <div className="db-maintenance__targets">{program.intervals.days !== null && <span>{program.targets.due_on ?? 'Date unknown'} · every {program.intervals.days} days</span>}{program.intervals.miles !== null && <span>{program.targets.odometer_miles === null ? 'Miles unknown' : `${program.targets.odometer_miles.toLocaleString()} mi`} · every {program.intervals.miles.toLocaleString()} mi</span>}{program.intervals.engine_hours !== null && <span>{program.targets.engine_hours === null ? 'Hours unknown' : `${program.targets.engine_hours} h`} · every {program.intervals.engine_hours} h</span>}</div>
    <small>{services.map(service => `${service.name}${service.availability !== 'active' ? ` (${service.availability})` : ''}`).join(' · ') || 'No service selected'}{program.mode === 'legacy' ? ' · Legacy package' : ''}</small>
    <div className="db-maintenance__actions">
      {pending && program.capabilities.can_record_evidence ? <ControlButton type="button" disabled={editing} onClick={event => onAction('evidence', event.currentTarget)}>Resolve readings</ControlButton> : canOpen ? <ControlButton type="button" onClick={() => onOpenOrder!(program.work!.repair_order_id!)}>Open work</ControlButton> : canPlan && <ControlButton type="button" disabled={editing} onClick={event => onAction('plan', event.currentTarget)}>Plan work</ControlButton>}
      <ControlButton controlKind="action" type="button" aria-expanded={historyOpen} onClick={onHistory}>History</ControlButton>{program.capabilities.can_edit && <ControlButton type="button" disabled={editing} onClick={event => onAction('edit', event.currentTarget)}>Edit</ControlButton>}
      <ControlButton controlKind="action" type="button" ref={moreButton} aria-label={`More for ${program.name}`} aria-expanded={more} onClick={() => setMore(value => !value)}>More {more ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}</ControlButton>
    </div>
    {more && <div className="db-maintenance__more" role="group" aria-label={`${program.name} options`} onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); closeMore() } }}>
      {program.intervals.miles !== null && <div><small>Mileage source</small><Reading value={program.due.miles.reading} /></div>}{program.intervals.engine_hours !== null && <div><small>Engine hours source</small><Reading value={program.due.engine_hours.reading} /></div>}
      <div className="db-maintenance__actions">{program.capabilities.can_record_evidence && !pending && <ControlButton type="button" disabled={editing} onClick={() => extra('evidence')}>Prior service</ControlButton>}{program.work?.state === 'active' && program.capabilities.can_plan && <ControlButton type="button" disabled={editing} onClick={() => extra('detach')}>Release work</ControlButton>}{program.capabilities.can_archive && <ControlButton type="button" disabled={editing} onClick={() => extra(program.archived_at ? 'restore' : 'archive')}>{program.archived_at ? 'Restore' : 'Archive'}</ControlButton>}<ControlButton type="button" aria-label={`Close ${program.name} options`} onClick={closeMore}>Close</ControlButton></div>
    </div>}
  </>
}
