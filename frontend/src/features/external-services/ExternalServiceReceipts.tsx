import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Paperclip, X } from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import {
  downloadError, MAX_RECEIPT_BYTES, RECEIPT_ACCEPT, receiptError, receiptFileError,
  receiptHistorySchema, receiptListSchema, receiptResultSchema, receiptSize, validateReceiptTarget,
  type Receipt, type ReceiptList,
} from './receipt-contract'
import './receipts.css'

type Props = { vehicleId: string; recordId: string; recordVersion: number; voidedAt: string | null; providerName: string; disabled?: boolean }
type Scope = readonly [string, string, string, number]
type Action = { kind: 'remove' | 'restore'; receipt: Receipt }
type Attempt = { kind: 'upload' | 'remove' | 'restore'; requestId: string; recordVersion: number; file?: File; receipt?: Receipt; reason?: string }
const dateLabel = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export function ExternalServiceReceipts(props: Props) {
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  if (!user?.tenant_id || !['garage_owner', 'garage_admin', 'receptionist'].includes(user.role)) return null
  const scope: Scope = [user.tenant_id, user.id, user.role, epoch]
  return <ScopedReceipts key={[...scope, props.vehicleId, props.recordId].join(':')} {...props} scope={scope} />
}

function ScopedReceipts({ vehicleId, recordId, recordVersion, voidedAt, providerName, disabled = false, scope }: Props & { scope: Scope }) {
  const client = useQueryClient()
  const [tenant, actor, role, epoch] = scope
  const prefix = useMemo(() => ['external-service-receipts', tenant, actor, role, epoch, vehicleId, recordId], [tenant, actor, role, epoch, vehicleId, recordId])
  const path = `/vehicles/${vehicleId}/external-services/${recordId}/receipts`
  const [open, setOpen] = useState(false)
  const [includeRemoved, setIncludeRemoved] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [action, setAction] = useState<Action | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [latest, setLatest] = useState<ReceiptList | null>(null)
  const attempt = useRef<Attempt | null>(null)
  const inFlight = useRef(false)
  const alive = useRef(true)
  const controllers = useRef(new Set<AbortController>())
  const objectUrls = useRef(new Set<string>())
  const fileInput = useRef<HTMLInputElement>(null)
  const reasonInput = useRef<HTMLTextAreaElement>(null)
  const trigger = useRef<HTMLButtonElement | null>(null)
  const disclosure = useRef<HTMLButtonElement>(null)
  const currentLifecycle = useRef({ voidedAt, disabled })
  currentLifecycle.current = { voidedAt, disabled }
  const isCurrent = () => {
    const auth = useAuthStore.getState()
    return alive.current && !auth.logoutInProgress && auth.user?.tenant_id === tenant && auth.user.id === actor && auth.user.role === role && auth.authSessionEpoch === epoch
  }
  useEffect(() => {
    alive.current = true
    const requests = controllers.current
    const urls = objectUrls.current
    return () => {
      alive.current = false
      requests.forEach(controller => controller.abort())
      urls.forEach(url => URL.revokeObjectURL(url))
      urls.clear()
      attempt.current = null
      void client.cancelQueries({ queryKey: prefix })
      client.removeQueries({ queryKey: prefix })
    }
  }, [client, prefix])
  const query = useQuery({
    queryKey: [...prefix, 'list', includeRemoved], enabled: open, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false,
    queryFn: async ({ signal }) => {
      const response = await api.get(path, { params: { include_removed: includeRemoved }, signal })
      if (signal.aborted || !isCurrent()) throw new Error('Receipt context changed')
      const result = receiptListSchema.parse(response.data)
      result.items.forEach(receipt => validateReceiptTarget(receipt, vehicleId, recordId))
      if (!includeRemoved && result.items.some(receipt => receipt.removed_at)) throw new Error('Invalid receipt lifecycle')
      return result
    },
  })
  const data = query.isError ? undefined : query.data
  const readOnly = Boolean(voidedAt || data?.record_voided_at)
  currentLifecycle.current = { voidedAt: voidedAt || data?.record_voided_at || null, disabled: disabled || query.isError }
  const unavailable = disabled || busy || query.isFetching || !data || query.isError
  const atCapacity = Boolean(data && (data.retained_count >= data.max_files || data.retained_bytes >= data.max_total_bytes))
  const clearFile = () => { setFile(null); if (fileInput.current) fileInput.current.value = '' }
  const closeAction = () => {
    setAction(null); setReason(''); setError(''); setConflict(false); setLatest(null); attempt.current = null
    requestAnimationFrame(() => { if (isCurrent()) (trigger.current?.isConnected ? trigger.current : disclosure.current)?.focus() })
  }
  const beginAction = (next: Action, button: HTMLButtonElement) => {
    trigger.current = button; setAction(next); setReason(''); setError(''); setMessage(''); setConflict(false); setLatest(null); attempt.current = null
    if (next.kind === 'remove') requestAnimationFrame(() => { if (isCurrent()) reasonInput.current?.focus() })
  }
  const save = async (nextAction = action) => {
    if (inFlight.current || unavailable || readOnly || conflict || !isCurrent()) return
    if (!nextAction && !file) return
    if (nextAction?.kind === 'remove' && !reason.trim()) { setError('Enter a reason for removing this receipt.'); return }
    if (!nextAction && file) {
      const invalid = receiptFileError(file)
      if (invalid) { setError(invalid); return }
    }
    if (!attempt.current) attempt.current = {
      kind: nextAction?.kind ?? 'upload', requestId: crypto.randomUUID(), recordVersion: data?.record_version ?? recordVersion,
      ...(nextAction ? { receipt: nextAction.receipt, ...(nextAction.kind === 'remove' ? { reason: reason.trim() } : {}) } : { file: file! }),
    }
    const saving = attempt.current
    const controller = new AbortController()
    controllers.current.add(controller); inFlight.current = true; setBusy(true); setError(''); setMessage('')
    try {
      const response = saving.kind === 'upload'
        ? await api.post(path, saving.file, { signal: controller.signal, skipAuthRefresh: true, headers: { 'Content-Type': 'application/octet-stream', 'X-Request-ID': saving.requestId, 'X-Expected-Record-Version': String(saving.recordVersion), 'X-Receipt-Filename': encodeURIComponent(saving.file!.name) } })
        : await api.post(`${path}/${saving.receipt!.id}/${saving.kind}`, { request_id: saving.requestId, expected_record_version: saving.recordVersion, expected_version: saving.receipt!.version, ...(saving.kind === 'remove' ? { reason: saving.reason } : {}) }, { signal: controller.signal, skipAuthRefresh: true })
      if (controller.signal.aborted || !isCurrent()) return
      const result = receiptResultSchema.parse(response.data)
      validateReceiptTarget(result.receipt, vehicleId, recordId, saving.receipt?.id)
      setMessage(result.replayed ? 'Save confirmed. No duplicate added.' : saving.kind === 'upload' ? 'Receipt uploaded.' : saving.kind === 'remove' ? 'Receipt removed. Restore it from Show removed.' : 'Receipt restored.')
      clearFile(); setAction(null); setReason(''); attempt.current = null; setConflict(false); setLatest(null)
      // A failed refresh must not turn an already confirmed save into an uncertain write.
      void client.invalidateQueries({ queryKey: prefix })
    } catch (failure) {
      if (controller.signal.aborted || !isCurrent()) return
      const detail = receiptError(failure, 'Save could not be confirmed. Your selection is kept. Retry to confirm without adding a duplicate.')
      setError(detail.message)
      setConflict(['record_changed', 'receipt_changed', 'request_id_conflict', 'record_voided', 'receipt_already_removed', 'receipt_already_active'].includes(detail.code))
      if (detail.code === 'duplicate_removed_receipt') setIncludeRemoved(true)
    } finally {
      controllers.current.delete(controller)
      if (isCurrent()) { inFlight.current = false; setBusy(false) }
    }
  }
  const refresh = async () => {
    const result = await query.refetch()
    if (!isCurrent()) return
    if (result.isError || !result.data) { setError('Could not refresh receipts. Your selection is kept.'); return }
    setLatest(result.data)
  }
  const adoptLatest = () => {
    if (!latest || latest.record_voided_at) return
    if (action) {
      const receipt = latest.items.find(item => item.id === action.receipt.id)
      if (!receipt || Boolean(receipt.removed_at) !== (action.kind === 'restore')) { setError('This receipt changed state. Cancel this action and use the current receipt list.'); return }
      setAction({ ...action, receipt })
    }
    attempt.current = null; setLatest(null); setConflict(false); setError('')
  }
  const download = async (receipt: Receipt) => {
    if (inFlight.current || unavailable || readOnly || receipt.removed_at || !isCurrent()) return
    const controller = new AbortController()
    controllers.current.add(controller); inFlight.current = true; setBusy(true); setError('')
    try {
      const response = await api.get(`${path}/${receipt.id}/download`, { responseType: 'blob', signal: controller.signal })
      if (controller.signal.aborted || !isCurrent() || currentLifecycle.current.voidedAt || currentLifecycle.current.disabled) return
      const blob = response.data
      const contentType = String(response.headers?.['content-type'] ?? '').split(';')[0].trim().toLowerCase()
      if (response.status !== 200 || !(blob instanceof Blob) || contentType !== 'application/octet-stream' || blob.type !== 'application/octet-stream' || blob.size !== receipt.size_bytes || blob.size > MAX_RECEIPT_BYTES) {
        throw { response: { data: blob } }
      }
      const url = URL.createObjectURL(blob)
      objectUrls.current.add(url)
      const link = document.createElement('a')
      link.href = url; link.download = receipt.filename; document.body.appendChild(link)
      try { link.click() } finally {
        link.remove()
        setTimeout(() => { if (objectUrls.current.delete(url)) URL.revokeObjectURL(url) }, 0)
      }
    } catch (failure) {
      const detail = await downloadError(failure)
      if (!controller.signal.aborted && isCurrent()) setError(detail)
    } finally {
      controllers.current.delete(controller)
      if (isCurrent()) { inFlight.current = false; setBusy(false) }
    }
  }
  return <div className="db-receipts">
    <button ref={disclosure} type="button" aria-expanded={open} aria-label={`Receipts for ${providerName}`} disabled={busy} onClick={() => setOpen(value => !value)}><ChevronRight size={14} className={open ? 'rotate-90' : ''} aria-hidden="true" /><Paperclip size={14} aria-hidden="true" />Receipts</button>
    {open && <div className="db-receipts__panel">
      {message && <p role="status">{message}</p>}
      {query.isPending && <p role="status">Loading receipts…</p>}
      {query.isError && <div role="alert">Could not load receipts. <button type="button" disabled={busy || query.isFetching} onClick={() => void query.refetch()}>Retry receipts</button></div>}
      {readOnly && <p className="db-receipts__muted">Restore this service to upload, download or change receipts.</p>}
      <div className="db-receipts__toolbar">
        <input ref={fileInput} className="db-receipts__file-input" type="file" aria-label="Receipt file" accept={RECEIPT_ACCEPT} disabled={unavailable || readOnly || Boolean(action) || atCapacity} onChange={event => {
          const selected = event.target.files?.[0] ?? null
          setFile(selected); attempt.current = null; setConflict(false); setLatest(null); setMessage(''); setError(selected ? receiptFileError(selected) ?? '' : '')
        }} />
        <button type="button" disabled={unavailable || readOnly || Boolean(action) || atCapacity} onClick={() => fileInput.current?.click()}>Choose file</button>
        <span className="db-receipts__muted">PDF, JPEG, PNG · 5 MiB max{data ? ` · ${data.retained_count}/${data.max_files} retained` : ''}</span>
        <label className="db-receipts__toggle"><input type="checkbox" checked={includeRemoved} disabled={busy || Boolean(action)} onChange={event => setIncludeRemoved(event.target.checked)} />Show removed</label>
      </div>
      {atCapacity && <p className="db-receipts__muted">Receipt storage is full. Removed files still count and can be restored.</p>}
      {file && <div className="db-receipts__selection"><span>{file.name} · {receiptSize(file.size)}</span><div className="db-receipts__buttons">
        <button type="button" disabled={busy || Boolean(action)} onClick={() => { clearFile(); attempt.current = null; setError(''); setConflict(false); setLatest(null) }}>Clear selection</button>
        <button type="button" disabled={unavailable || readOnly || Boolean(action) || conflict || Boolean(receiptFileError(file))} onClick={() => void save(null)}>{busy && !action ? 'Uploading…' : attempt.current?.kind === 'upload' ? 'Retry upload' : 'Upload receipt'}</button>
      </div></div>}
      {error && <p role="alert">{error}</p>}
      {conflict && <button type="button" disabled={busy || query.isFetching} onClick={() => void refresh()}>Refresh receipts / record</button>}
      {latest && <div className="db-receipts__latest"><p>Latest service version {latest.record_version}{latest.record_voided_at ? ' · Voided' : ''}. Your selection is kept.</p><button type="button" disabled={busy || Boolean(latest.record_voided_at)} onClick={adoptLatest}>Use refreshed version</button></div>}
      {data && <>
        {!data.items.length && <p className="db-receipts__muted">{data.retained_count ? 'No active receipts. Check Show removed.' : 'No receipts attached.'}</p>}
        <ul className="db-receipts__list">{data.items.map(receipt => <li key={receipt.id}>
          <div className="db-receipts__row"><div className="db-receipts__identity"><strong>{receipt.filename}</strong>
            <p className="db-receipts__muted">{receipt.media_type === 'application/pdf' ? 'PDF' : receipt.media_type === 'image/jpeg' ? 'JPEG' : 'PNG'} · {receiptSize(receipt.size_bytes)}{receipt.removed_at ? ' · Removed' : ''}</p>
            <p className="db-receipts__muted">Uploaded by {receipt.created_by_name || 'Staff'} · <time dateTime={receipt.created_at}>{dateLabel(receipt.created_at)}</time></p>
            {receipt.removed_at && <p className="db-receipts__muted">Removed by {receipt.updated_by_name || 'Staff'} · <time dateTime={receipt.removed_at}>{dateLabel(receipt.removed_at)}</time></p>}
          </div><div className="db-receipts__buttons">
            {receipt.removed_at ? <button type="button" aria-label={`Restore ${receipt.filename}`} disabled={unavailable || readOnly || Boolean(action)} onClick={event => { const next: Action = { kind: 'restore', receipt }; beginAction(next, event.currentTarget); void save(next) }}>Restore</button> : <>
              <button type="button" aria-label={`Download ${receipt.filename}`} disabled={unavailable || readOnly || Boolean(action)} onClick={() => void download(receipt)}>Download</button>
              <button type="button" aria-label={`Remove ${receipt.filename}`} disabled={unavailable || readOnly || Boolean(action)} onClick={event => beginAction({ kind: 'remove', receipt }, event.currentTarget)}>Remove</button>
            </>}
          </div></div>
          <ReceiptHistory receipt={receipt} path={path} prefix={prefix} isCurrent={isCurrent} />
        </li>)}</ul>
      </>}
      {action && query.isError && <button type="button" disabled={busy} onClick={closeAction}>Close receipt action</button>}
      {action && !query.isError && <form aria-label={action.kind === 'remove' ? 'Remove receipt' : 'Restore receipt'} className="db-receipts__confirmation" onSubmit={event => { event.preventDefault(); void save() }} onKeyDown={event => { if (event.key === 'Escape' && !busy) { event.preventDefault(); event.stopPropagation(); closeAction() } }}>
        <div className="db-receipts__toolbar"><strong>{action.kind === 'remove' ? 'Remove receipt' : 'Restore receipt'}</strong><button className="db-receipts__close" type="button" aria-label="Close receipt action" disabled={busy} onClick={closeAction}><X size={16} aria-hidden="true" /></button></div>
        <p>{action.receipt.filename}</p>
        {action.kind === 'remove' && <><p className="db-receipts__muted">The file and its history are kept. You can restore it from Show removed.</p><label>Removal reason<textarea ref={reasonInput} required maxLength={500} rows={2} value={reason} disabled={busy} onChange={event => { const next = event.target.value; setReason(next); if (next.trim() !== attempt.current?.reason) attempt.current = null }} /></label></>}
        <div className="db-receipts__buttons"><button type="button" disabled={busy} onClick={closeAction}>Cancel</button><button type="submit" disabled={unavailable || readOnly || conflict}>{busy ? 'Saving…' : action.kind === 'remove' ? 'Remove receipt' : 'Retry restore'}</button></div>
      </form>}
    </div>}
  </div>
}

function ReceiptHistory({ receipt, path, prefix, isCurrent }: { receipt: Receipt; path: string; prefix: (string | number)[]; isCurrent: () => boolean }) {
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(0)
  const history = useQuery({
    queryKey: [...prefix, 'history', receipt.id, receipt.version, page], enabled: open, retry: false, gcTime: 0, refetchOnWindowFocus: false,
    queryFn: async ({ signal }) => {
      const response = await api.get(`${path}/${receipt.id}/history`, { params: { skip: page * 10, limit: 10 }, signal })
      if (signal.aborted || !isCurrent()) throw new Error('Receipt context changed')
      const result = receiptHistorySchema.parse(response.data)
      if (result.items.some(event => event.receipt_id !== receipt.id || event.record_id !== receipt.record_id || event.snapshot.id !== receipt.id || event.snapshot.record_id !== receipt.record_id)) throw new Error('Invalid receipt history')
      // Older snapshots retain the vehicle at the time of the action, including before a merge.
      return result
    },
  })
  return <div className="db-receipts__history"><button type="button" aria-expanded={open} aria-label={`Receipt history for ${receipt.filename}`} onClick={() => setOpen(value => !value)}><ChevronRight size={14} className={open ? 'rotate-90' : ''} aria-hidden="true" />History</button>
    {open && <>
      {history.isPending && <p role="status">Loading receipt history…</p>}
      {history.isError && <div role="alert">Could not load receipt history. <button type="button" onClick={() => void history.refetch()}>Retry receipt history</button></div>}
      {history.data && !history.isError && <><ol>{history.data.items.map(event => <li key={event.id}><p><strong>{{ upload: 'Uploaded', remove: 'Removed', restore: 'Restored' }[event.action]}</strong> · {event.actor_name || 'Staff'} · <time dateTime={event.created_at}>{dateLabel(event.created_at)}</time></p>{event.reason && <p>{event.reason}</p>}</li>)}</ol>
        {(page > 0 || history.data.has_more) && <div className="db-receipts__buttons"><button type="button" disabled={!page || history.isFetching} onClick={() => setPage(value => value - 1)}>Newer changes</button><button type="button" disabled={!history.data.has_more || history.isFetching} onClick={() => setPage(value => value + 1)}>Older changes</button></div>}
      </>}
    </>}
  </div>
}
