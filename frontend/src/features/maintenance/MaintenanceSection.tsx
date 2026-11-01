import { ControlButton, ControlInput } from '@/components/ui/Controls'
import PlatformSelect from '@/components/PlatformSelect'
import { useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import DatePicker from '@/components/DatePicker'
import { useAuthStore } from '@/stores/authStore'
import { usePricingScope } from '@/features/parts-pricing/usePricingScope'
import PricingFeedback from '@/features/parts-pricing/PricingFeedback'
import { detachMutationSchema, historySchema, hours, label, programMutationSchema, programServices, readingMutationSchema, whole, type Channel, type Completion, type Program } from './contract'
import { maintenanceError, MaintenanceCancelled, programPath, scopedProgram, useMaintenanceCommand, usePrograms } from './api'
import { Reading, TargetValues } from './MaintenanceFields'
import ProgramEditor from './ProgramEditor'
import ProgramRow from './ProgramRow'
import MaintenanceEvidence from './MaintenanceEvidence'
import MaintenanceWork from './MaintenanceWork'
import './maintenance.css'

type Props = { vehicleId: string; channel: Channel; customerId?: string; onOpenOrder?: (id: string) => void }
type Editor = { kind: 'program'; program?: Program } | { kind: 'evidence'; program: Program; completion?: Completion } | { kind: 'reading' } | { kind: 'work'; programs: Program[] } | { kind: 'archive' | 'restore' | 'detach'; program: Program }
export default function MaintenanceSection(props: Props) {
  const scope = usePricingScope(); const user = useAuthStore(state => state.user)
  const allowed = user?.tenant_id && (props.channel === 'fleet' ? ['garage_owner', 'garage_admin', 'fleet_manager'] : ['garage_owner', 'garage_admin', 'receptionist']).includes(user.role)
  if (!allowed) return null
  return <ScopedMaintenance key={`${scope}:${props.vehicleId}:${props.channel}`} {...props} />
}
function ScopedMaintenance({ vehicleId, channel, customerId, onOpenOrder }: Props) {
  const [page, setPage] = useState(0); const [archived, setArchived] = useState(false); const [selected, setSelected] = useState<string[]>([])
  const [editor, setEditor] = useState<Editor | null>(null); const [historyId, setHistoryId] = useState<string | null>(null); const [notice, setNotice] = useState<{ message: string } | null>(null)
  const trigger = useRef<HTMLElement | null>(null); const addButton = useRef<HTMLButtonElement>(null)
  const query = usePrograms(vehicleId, channel, archived, page)
  const open = (next: Editor, element: HTMLElement) => { trigger.current = element; setEditor(next); setNotice(null) }
  const close = () => { setEditor(null); requestAnimationFrame(() => (trigger.current?.isConnected ? trigger.current : addButton.current)?.focus({ preventScroll: true })) }
  const done = () => { close(); setNotice({ message: 'Maintenance saved.' }); setSelected([]); void query.refetch() }
  const editedProgram = editor && 'program' in editor ? editor.program : undefined
  const rows = [...(query.data?.items ?? [])]
  if (editedProgram && !rows.some(program => program.id === editedProgram.id)) rows.push(editedProgram)
  const visibleRows = !query.isError && !query.isPending
  const selectedPrograms = query.data?.items.filter(program => selected.includes(program.id)) ?? []
  const selectionUnavailable = selectedPrograms.length !== selected.length || selectedPrograms.some(program => !program.capabilities.can_plan || Boolean(program.archived_at) || programServices(program).length === 0)
  const renderEditor = () => {
    if (!editor) return null
    const title = editor.kind === 'program' ? editor.program ? `Edit ${editor.program.name}` : 'New maintenance program' : editor.kind === 'reading' ? 'Record reading' : editor.kind === 'work' ? 'Plan maintenance work' : editor.kind === 'evidence' ? `Service evidence · ${editor.program.name}` : `${editor.kind === 'detach' ? 'Release work' : editor.kind === 'archive' ? 'Archive' : 'Restore'} · ${editor.program.name}`
    return <EditorRegion title={title}>
      {editor.kind === 'program' && <ProgramEditor vehicleId={vehicleId} channel={channel} program={editor.program} onDone={done} onCancel={close} onReload={async () => { const result = await query.refetch(); const current = result.data?.items.find(item => item.id === editor.program?.id); if (result.isError || !current) throw new Error('Saved program is not on this page. Cancel and reopen it from the refreshed list.'); return current }} />}
      {editor.kind === 'reading' && <ReadingEditor vehicleId={vehicleId} channel={channel} onDone={done} onCancel={close} />}
      {editor.kind === 'evidence' && <MaintenanceEvidence vehicleId={vehicleId} channel={channel} program={editor.program} completion={editor.completion} onDone={done} onCancel={close} />}
      {editor.kind === 'work' && <MaintenanceWork vehicleId={vehicleId} channel={channel} programs={editor.programs} customerId={customerId} onDone={orderId => { done(); setNotice({ message: 'Maintenance work saved.' }); onOpenOrder?.(orderId) }} onCancel={close} />}
      {['archive', 'restore', 'detach'].includes(editor.kind) && <ProgramAction vehicleId={vehicleId} channel={channel} editor={editor as Extract<Editor, { kind: 'archive' | 'restore' | 'detach' }>} onDone={done} onCancel={close} />}
    </EditorRegion>
  }
  return <section className="db-maintenance" aria-label="Maintenance">
    <div className="db-maintenance__heading"><h3>Maintenance</h3><ControlButton ref={addButton} type="button" disabled={Boolean(editor) || query.isPending || query.isError} onClick={event => open({ kind: 'program' }, event.currentTarget)}>Add program</ControlButton><ControlButton type="button" disabled={Boolean(editor) || query.isPending || query.isError} onClick={event => open({ kind: 'reading' }, event.currentTarget)}>Record reading</ControlButton></div>
    {editor && !editedProgram && renderEditor()}
    {query.isPending ? <p role="status">Loading maintenance…</p> : query.isError || !query.data ? <p role="alert">Maintenance unavailable. <ControlButton type="button" onClick={() => void query.refetch()}>Retry maintenance</ControlButton></p> : query.data.items.length === 0 && <p className="db-maintenance__muted">No {archived ? '' : 'active '}maintenance programs.</p>}
    <ul className="db-maintenance__programs">{rows.map(program => (visibleRows || editedProgram?.id === program.id) && <li key={program.id}>
      {visibleRows && <ProgramRow program={program} selected={selected.includes(program.id)} editing={Boolean(editor)} historyOpen={historyId === program.id} onSelect={checked => setSelected(current => checked ? [...current, program.id] : current.filter(id => id !== program.id))} onHistory={() => setHistoryId(current => current === program.id ? null : program.id)} onOpenOrder={onOpenOrder} onAction={(action, element) => open(action === 'plan' ? { kind: 'work', programs: [program] } : action === 'edit' ? { kind: 'program', program } : { kind: action, program }, element)} />}
      {editedProgram?.id === program.id && renderEditor()}
      {visibleRows && historyId === program.id && <MaintenanceHistory vehicleId={vehicleId} channel={channel} program={program} onOpenOrder={onOpenOrder} onReview={(completion, element) => open({ kind: 'evidence', program, completion }, element)} />}
    </li>)}</ul>
    {visibleRows && selectionUnavailable && !editor && <p role="alert">Selection changed. Clear selection and choose available programs again.</p>}
    {visibleRows && query.data && <div className="db-maintenance__actions"><label className="db-maintenance__check"><input type="checkbox" checked={archived} disabled={Boolean(editor)} onChange={event => { setArchived(event.target.checked); setPage(0); setSelected([]) }} />Show archived</label>{selected.length > 0 && <><ControlButton type="button" disabled={Boolean(editor)} onClick={() => setSelected([])}>Clear selection</ControlButton><ControlButton type="button" disabled={Boolean(editor) || selectionUnavailable} onClick={event => { if (!selectionUnavailable) open({ kind: 'work', programs: selectedPrograms }, event.currentTarget) }}>Plan work · {selected.length}</ControlButton></>}{(page > 0 || query.data.has_more) && <><ControlButton type="button" disabled={page === 0 || Boolean(editor) || query.isFetching} onClick={() => { setPage(value => value - 1); setSelected([]) }}>Previous programs</ControlButton><span>Page {page + 1}</span><ControlButton type="button" disabled={!query.data.has_more || Boolean(editor) || query.isFetching} onClick={() => { setPage(value => value + 1); setSelected([]) }}>Next programs</ControlButton></>}</div>}
    {notice && <PricingFeedback revision={notice} role="status">{notice.message}</PricingFeedback>}
  </section>
}
function EditorRegion({ title, children }: { title: string; children: ReactNode }) {
  const region = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const element = region.current
    if (!element) return
    for (let parent = element.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
      if (['auto', 'scroll'].includes(getComputedStyle(parent).overflowY) && parent.scrollHeight > parent.clientHeight) {
        const view = parent.getBoundingClientRect(); const bounds = element.getBoundingClientRect()
        if (bounds.top < view.top || bounds.top + 100 > view.bottom) parent.scrollTop = Math.max(0, parent.scrollTop + bounds.top - view.top - 8)
        break
      }
    }
    const first = element.querySelector<HTMLElement>('input:not(:disabled), select:not(:disabled), button:not(:disabled)')
    ;(first ?? element).focus({ preventScroll: true })
  }, [])
  return <div ref={region} role="region" aria-label={title} tabIndex={-1}><h4>{title}</h4>{children}</div>
}

function ProgramAction({ vehicleId, channel, editor, onDone, onCancel }: { vehicleId: string; channel: Channel; editor: Extract<Editor, { kind: 'archive' | 'restore' | 'detach' }>; onDone: () => void; onCancel: () => void }) {
  const command = useMaintenanceCommand(`${vehicleId}:${editor.program.id}:${editor.kind}`); const [error, setError] = useState<{ message: string } | null>(null)
  const save = async () => { try { const program = editor.program; const result = await command.run(`${programPath(vehicleId, program.id)}/${editor.kind === 'detach' ? 'detach-work' : editor.kind}`, { channel, expected_version: program.version, ...(editor.kind === 'detach' ? { work_link_id: program.work!.work_link_id, expected_link_version: program.work!.version } : {}) }, value => editor.kind === 'detach' ? detachMutationSchema.parse(value) : programMutationSchema.parse(value)); scopedProgram(result.program, vehicleId, program.id); onDone() } catch (failure) { if (!(failure instanceof MaintenanceCancelled)) setError({ message: maintenanceError(failure) }) } }
  return <div className="db-maintenance__review" onKeyDown={event => { if (event.defaultPrevented) { event.stopPropagation(); return } if (event.key === 'Escape' && !command.busy) { event.stopPropagation(); onCancel() } }}><p>{editor.kind === 'detach' ? 'Release the unperformed cycle claim? The operation and its prices stay on the order.' : `${editor.kind === 'archive' ? 'Archive' : 'Restore'} ${editor.program.name}? Targets and history are retained.`}</p>{error && <PricingFeedback revision={error}>{error.message}</PricingFeedback>}<div className="db-maintenance__actions"><ControlButton type="button" disabled={command.busy} onClick={onCancel}>Cancel</ControlButton><ControlButton type="button" disabled={command.busy} onClick={() => void save()}>{editor.kind === 'detach' ? 'Release work' : editor.kind === 'archive' ? 'Archive program' : 'Restore program'}</ControlButton></div></div>
}
function ReadingEditor({ vehicleId, channel, onDone, onCancel }: { vehicleId: string; channel: Channel; onDone: () => void; onCancel: () => void }) {
  const [date, setDate] = useState(''); const [time, setTime] = useState(''); const [miles, setMiles] = useState(''); const [engineHours, setHours] = useState(''); const [source, setSource] = useState('staff_observed'); const [note, setNote] = useState(''); const [error, setError] = useState<{ message: string } | null>(null)
  const command = useMaintenanceCommand(`${vehicleId}:reading`)
  const timeHintId = useId()
  const save = async () => { try { const odometer = whole(miles, 'mileage'); const hourValue = hours(engineHours); if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) throw new Error('Enter a time from 00:00 to 23:59 (HH:MM).'); if (!date || Number.isNaN(new Date(`${date}T${time}`).getTime())) throw new Error('Enter the observation date and time.'); if (odometer === null && hourValue === null) throw new Error('Enter mileage or engine hours.'); await command.run(`/vehicles/${vehicleId}/maintenance-readings`, { channel, observed_at: new Date(`${date}T${time}`).toISOString(), odometer_miles: odometer, engine_hours: hourValue, source, note: note.trim() || null }, value => readingMutationSchema.parse(value)); onDone() } catch (failure) { if (!(failure instanceof MaintenanceCancelled)) setError({ message: maintenanceError(failure) }) } }
  return <form className="db-maintenance__editor" aria-label="Record current reading" onSubmit={event => { event.preventDefault(); void save() }} onKeyDown={event => { if (event.defaultPrevented) { event.stopPropagation(); return } if (event.key === 'Escape' && !command.busy) { event.stopPropagation(); onCancel() } }}><fieldset disabled={command.busy} className="db-maintenance__fields"><DatePicker label="Observed date" value={date} onChange={setDate} disabled={command.busy} showDayDetails={false} /><div><label>Observed time<ControlInput type="text" placeholder="HH:MM" aria-describedby={timeHintId} maxLength={5} autoComplete="off" spellCheck={false} value={time} onChange={event => setTime(event.target.value)} /></label><small id={timeHintId}>24-hour local time</small></div><label>Miles<ControlInput inputMode="numeric" value={miles} onChange={event => setMiles(event.target.value)} /></label><label>Engine hours<ControlInput inputMode="decimal" value={engineHours} onChange={event => setHours(event.target.value)} /></label><label>Basis<PlatformSelect value={source} onChange={event => setSource(event.target.value)}><option value="staff_observed">Observed</option><option value="staff_reported">Reported</option></PlatformSelect></label><label className="db-maintenance__wide">Note<ControlInput value={note} maxLength={500} onChange={event => setNote(event.target.value)} /></label></fieldset>{error && <PricingFeedback revision={error}>{error.message}</PricingFeedback>}<div className="db-maintenance__actions"><ControlButton type="button" disabled={command.busy} onClick={onCancel}>Cancel</ControlButton><ControlButton type="submit" disabled={command.busy}>{command.busy ? 'Saving…' : 'Save reading'}</ControlButton></div></form>
}
function MaintenanceHistory({ vehicleId, channel, program, onReview, onOpenOrder }: { vehicleId: string; channel: Channel; program: Program; onReview: (completion: Completion, element: HTMLElement) => void; onOpenOrder?: (id: string) => void }) {
  const scope = usePricingScope(); const [page, setPage] = useState(0)
  const query = useQuery({ queryKey: ['maintenance-history', scope, vehicleId, program.id, channel, page], gcTime: 0, retry: false, queryFn: async ({ signal }) => { const result = historySchema.parse((await api.get(`${programPath(vehicleId, program.id)}/history`, { signal, params: { channel, skip: page * 25, limit: 25 } })).data); if (result.items.some(item => item.completion && item.completion.program_id !== program.id)) throw new Error('Invalid maintenance history'); return result } })
  return <section className="db-maintenance__history" aria-label={`${program.name} history`}>{query.isPending ? <p role="status">Loading maintenance history…</p> : query.isError || !query.data ? <p role="alert">History unavailable. <ControlButton type="button" onClick={() => void query.refetch()}>Retry history</ControlButton></p> : <>{query.data.items.length === 0 && <p>No history yet.</p>}{query.data.items.map(item => <article key={item.id}><strong>{item.summary}</strong><small>{new Date(item.occurred_at).toLocaleString()} · {label(item.action)}</small>{item.reason && <p>{item.reason}</p>}{item.completion && <><p>{item.completion.performed_on ?? 'Service date unknown'} · {label(item.completion.result)} · {item.completion.source.label}</p>{item.completion.readings.odometer_miles && <Reading value={item.completion.readings.odometer_miles} />}{item.completion.readings.engine_hours && <Reading value={item.completion.readings.engine_hours} />}<div><small>Next </small><TargetValues value={item.completion.next_targets} /></div><div className="db-maintenance__actions">{item.completion.source.kind === 'repair_order' && item.completion.source.can_open && item.completion.source.id && onOpenOrder && <ControlButton type="button" onClick={() => onOpenOrder(item.completion!.source.id!)}>Open source</ControlButton>}{program.capabilities.can_record_evidence && <ControlButton type="button" onClick={event => onReview(item.completion!, event.currentTarget)}>Review evidence</ControlButton>}</div></>}</article>)}{(page > 0 || query.data.has_more) && <div className="db-maintenance__actions"><ControlButton type="button" disabled={page === 0 || query.isFetching} onClick={() => setPage(value => value - 1)}>Previous events</ControlButton><ControlButton type="button" disabled={!query.data.has_more || query.isFetching} onClick={() => setPage(value => value + 1)}>Next events</ControlButton></div>}</>}</section>
}
