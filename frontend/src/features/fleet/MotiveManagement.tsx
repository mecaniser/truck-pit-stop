import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { motiveError } from './motiveErrors'

interface Person { user_id: string; name: string | null; email: string }
interface WebhookStatus {
  status: 'not_configured' | 'awaiting_provider' | 'receiving' | 'disabled'
  url: string | null; last_received_at: string | null; pending_count: number; failed_count: number
}

export function MotiveGrants({ companyId }: { companyId: string }) {
  const actor = useAuthStore((s) => s.user)
  const qc = useQueryClient()
  const params = { fleet_customer_id: companyId }
  const scope = [companyId, actor?.id, actor?.tenant_id]
  const [selection, setSelection] = useState('')
  const [notice, setNotice] = useState('')
  const grants = useQuery<{ items: Person[] }>({ queryKey: ['motive-grants', ...scope], queryFn: async ({ signal }) => (await api.get('/fleet/motive/grants', { params, signal })).data, retry: false })
  const candidates = useQuery<{ items: Person[] }>({ queryKey: ['motive-grant-candidates', ...scope], queryFn: async ({ signal }) => (await api.get('/fleet/motive/grant-candidates', { params, signal })).data, retry: false })
  const change = useMutation({
    mutationFn: ({ userId, revoke }: { userId: string; revoke: boolean }) => revoke
      ? api.delete(`/fleet/motive/grants/${encodeURIComponent(userId)}`, { params })
      : api.put(`/fleet/motive/grants/${encodeURIComponent(userId)}`, params),
    onSuccess: async (_, { revoke }) => {
      setSelection(''); setNotice(revoke ? 'Administrator access revoked.' : 'Administrator access granted.')
      await qc.invalidateQueries({ queryKey: ['motive-grants', ...scope] })
    },
    onError: (error) => setNotice(motiveError(error)),
  })
  const people = candidates.data?.items ?? []
  const active = grants.data?.items ?? []
  return <section className="motive-trucks" aria-label="Motive administrators">
    <h4>Company administrators</h4>
    <p className="motive-muted">Allow a linked customer to connect and manage this company’s Motive account.</p>
    {(grants.isError || candidates.isError) && <p role="alert">Could not load administrator access. <button className="dbtn dbtn-ghost" onClick={() => { void grants.refetch(); void candidates.refetch() }}>Retry</button></p>}
    {grants.isPending && <p role="status">Loading administrators…</p>}
    {!grants.isError && active.map((person) => <div className="motive-actions" key={person.user_id}><span>{person.name || person.email}</span><button className="dbtn dbtn-ghost" disabled={change.isPending} onClick={() => change.mutate({ userId: person.user_id, revoke: true })}>Revoke {person.name || person.email}</button></div>)}
    <label htmlFor={`motive-admin-${companyId}`}>Linked customer</label>
    <select id={`motive-admin-${companyId}`} value={selection} onChange={(e) => setSelection(e.target.value)} disabled={change.isPending || candidates.isError || grants.isError}>
      <option value="">Choose a customer</option>
      {people.filter((p) => !active.some((a) => a.user_id === p.user_id)).map((person) => <option key={person.user_id} value={person.user_id}>{person.name ? `${person.name} · ${person.email}` : person.email}</option>)}
    </select>
    <button className="dbtn dbtn-ghost" disabled={!selection || change.isPending || candidates.isError || grants.isError} onClick={() => change.mutate({ userId: selection, revoke: false })}>Grant administrator access</button>
    {notice && <p role="status">{notice}</p>}
  </section>
}

export function MotiveWebhook({ companyId }: { companyId: string }) {
  const actor = useAuthStore((s) => s.user)
  const params = { fleet_customer_id: companyId }
  const [secret, setSecret] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const status = useQuery<WebhookStatus>({ queryKey: ['motive-webhook', companyId, actor?.id, actor?.tenant_id], queryFn: async ({ signal }) => (await api.get('/fleet/motive/webhook', { params, signal })).data, retry: false, refetchInterval: 60000 })
  useEffect(() => { setSecret('') }, [companyId, actor?.id, actor?.tenant_id])
  useEffect(() => { if (status.isError) setSecret('') }, [status.isError])
  // This response must never enter React Query's mutation cache or browser storage.
  const rotate = async () => {
    setBusy(true); setSecret(''); setNotice('')
    try {
      const { data } = await api.post<WebhookStatus & { shared_secret: string }>('/fleet/motive/webhook/rotate', params)
      setSecret(data.shared_secret); setConfirm(false)
      await status.refetch()
    } catch (error) { setNotice(motiveError(error)) } finally { setBusy(false) }
  }
  const labels = { not_configured: 'Not configured', awaiting_provider: 'Awaiting Motive setup', receiving: 'Receiving events', disabled: 'Disabled' }
  return <section className="motive-trucks" aria-label="Motive webhook setup">
    <h4>Live updates</h4>
    {status.isPending && <p role="status">Loading live update status…</p>}
    {status.isError && <p role="alert">Could not load live update setup. <button className="dbtn dbtn-ghost" onClick={() => { setSecret(''); void status.refetch() }}>Retry</button></p>}
    {status.data && !status.isError && <>
      <p>{labels[status.data.status]}</p>
      {status.data.last_received_at && <p className="motive-muted">Last event: {new Date(status.data.last_received_at).toLocaleString()}</p>}
      <p className="motive-muted">{status.data.pending_count ?? 0} pending · {status.data.failed_count ?? 0} need attention</p>
      {status.data.url && <label>Webhook URL<input readOnly value={status.data.url} /></label>}
      <button className="dbtn dbtn-ghost" disabled={busy} onClick={() => { setSecret(''); setConfirm(true) }}>{status.data.url ? 'Rotate webhook secret' : 'Prepare live updates'}</button>
      {confirm && <div className="motive-confirm"><p>{status.data.url ? 'Replace the current secret? Update the Motive subscription with the new URL and secret to resume live events.' : 'Create a webhook URL and secret for this company’s Motive subscription.'}</p><div className="motive-actions"><button className="dbtn dbtn-ghost" disabled={busy} onClick={() => setConfirm(false)}>Cancel</button><button className="dbtn dbtn-yellow" disabled={busy} onClick={() => void rotate()}>Generate webhook secret</button></div></div>}
      {secret && <div className="motive-confirm"><p>Save this secret in Motive’s webhook configuration now. It is shown only once. Preparing these values does not activate a subscription in Motive.</p><label>One-time shared secret<input readOnly autoComplete="off" value={secret} /></label><button className="dbtn dbtn-ghost" onClick={() => setSecret('')}>Hide secret</button></div>}
    </>}
    {notice && <p role="status">{notice}</p>}
  </section>
}
