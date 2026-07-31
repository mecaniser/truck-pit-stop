import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { ArrowLeft, CheckCircle2, Link2, MapPin, Unplug } from 'lucide-react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '@/lib/api'

type Connection = { configured: boolean; is_connected: boolean; status: string; location_name: string | null; last_sync_at: string | null; last_sync_error: string | null }
type Location = { account_id: string; location_id: string; name: string }
type Settings = { brand_voice_prompt: string; reply_policy: string; auto_publish_five_star: boolean; alert_recipients: string[] }

export default function GoogleReviewsSettingsPage() {
  const queryClient = useQueryClient()
  const [voice, setVoice] = useState('')
  const [policy, setPolicy] = useState('')
  const [autoPublish, setAutoPublish] = useState(false)
  const [recipients, setRecipients] = useState('')
  const { data: connection, isLoading: connectionLoading } = useQuery<Connection>({ queryKey: ['google-review-connection'], queryFn: async () => (await api.get('/google-reviews/connection/status')).data })
  const { data: savedSettings } = useQuery<Settings>({ queryKey: ['google-review-settings'], queryFn: async () => (await api.get('/google-reviews/settings')).data })
  const selectionPending = connection?.status === 'location_selection_required'
  const { data: locations = [], isLoading: locationsLoading, error: locationsError } = useQuery<Location[]>({ queryKey: ['google-review-locations'], queryFn: async () => (await api.get('/google-reviews/connection/locations')).data, enabled: selectionPending })

  useEffect(() => {
    if (!savedSettings) return
    setVoice(savedSettings.brand_voice_prompt)
    setPolicy(savedSettings.reply_policy)
    setAutoPublish(savedSettings.auto_publish_five_star)
    setRecipients(savedSettings.alert_recipients.join(', '))
  }, [savedSettings])

  const connect = useMutation({ mutationFn: async () => (await api.post('/google-reviews/connection/authorize')).data.url, onSuccess: url => window.location.assign(url), onError: () => toast.error('Could not start Google connection') })
  const selectLocation = useMutation({ mutationFn: async (location: Location) => api.put('/google-reviews/connection/location', location), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['google-review-connection'] }); queryClient.invalidateQueries({ queryKey: ['google-review-locations'] }); toast.success('Google Business Profile connected') }, onError: () => toast.error('Could not save this location') })
  const disconnect = useMutation({ mutationFn: () => api.delete('/google-reviews/connection'), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['google-review-connection'] }); toast.success('Google disconnected') }, onError: () => toast.error('Could not disconnect Google') })
  const save = useMutation({ mutationFn: () => api.put('/google-reviews/settings', { brand_voice_prompt: voice, reply_policy: policy, auto_publish_five_star: autoPublish, alert_recipients: recipients.split(',').map(email => email.trim()).filter(Boolean) }), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['google-review-settings'] }); toast.success('Review settings saved') }, onError: () => toast.error('Could not save settings') })

  const reconnect = () => connect.mutate()
  const locationLoadMessage = (locationsError as any)?.response?.data?.detail as string | undefined

  return <div className="mx-auto max-w-4xl p-4 sm:p-6 text-white">
    <Link to="/dashboard/garage/reviews" className="inline-flex items-center gap-2 text-sm text-gray-400 hover:text-white"><ArrowLeft className="h-4 w-4" /> Google Reviews inbox</Link>
    <h1 className="mt-4 text-2xl font-semibold">Google Reviews settings</h1>
    <p className="mt-1 text-sm text-gray-400">Connect this shop’s own Google Business Profile and control how replies are handled.</p>

    <section className="mt-6 rounded-xl border border-white/10 bg-white/5 p-5">
      <div className="flex items-start justify-between gap-4"><div><h2 className="font-medium">1. Google Business Profile connection</h2><p className="mt-1 text-sm text-gray-400">Each tenant signs in with the Google account that manages its location. Credentials never appear in the browser.</p></div>{connection?.is_connected && <span className="inline-flex items-center gap-1 text-sm text-emerald-300"><CheckCircle2 className="h-4 w-4" /> Connected</span>}</div>
      {connectionLoading ? <p className="mt-4 text-sm text-gray-400">Checking connection…</p> : !connection?.configured ? <p className="mt-4 rounded-lg bg-amber-400/10 p-3 text-sm text-amber-200">Google OAuth has not been configured for this deployment yet. Ask the platform administrator to configure the Google Cloud app, redirect URL, and token-encryption key.</p> : connection?.is_connected ? <div className="mt-4 flex flex-wrap items-center gap-3"><span className="inline-flex items-center gap-2 rounded-lg bg-emerald-400/10 px-3 py-2 text-sm text-emerald-200"><MapPin className="h-4 w-4" /> {connection.location_name}</span><button onClick={() => disconnect.mutate()} disabled={disconnect.isPending} className="inline-flex items-center gap-2 rounded-lg border border-red-400/30 px-3 py-2 text-sm text-red-200 hover:bg-red-400/10"><Unplug className="h-4 w-4" /> Disconnect</button></div> : selectionPending ? <div className="mt-4"><p className="text-sm text-gray-300">2. Select the location whose reviews this tenant should manage.</p><div className="mt-3 space-y-2">{locationsLoading ? <p className="text-sm text-gray-400">Loading Google locations…</p> : locations.map(location => <button key={`${location.account_id}-${location.location_id}`} onClick={() => selectLocation.mutate(location)} disabled={selectLocation.isPending} className="flex w-full items-center justify-between rounded-lg border border-white/10 p-3 text-left hover:border-emerald-400/50 hover:bg-white/5"><span className="flex items-center gap-2"><MapPin className="h-4 w-4 text-emerald-300" />{location.name}</span><span className="text-xs text-gray-500">Select</span></button>)}{locationLoadMessage && <div className="rounded-lg bg-amber-400/10 p-3 text-sm text-amber-200"><p>{locationLoadMessage}</p></div>}{!locations.length && !locationsLoading && !locationLoadMessage && <div className="rounded-lg bg-amber-400/10 p-3 text-sm text-amber-200"><p>No eligible locations were found. Confirm that this Google account is a manager of the Business Profile, then reconnect.</p><button onClick={reconnect} disabled={connect.isPending} className="mt-3 inline-flex items-center gap-2 rounded-lg bg-amber-300 px-3 py-2 text-sm font-medium text-black hover:bg-amber-200"><Link2 className="h-4 w-4" />{connect.isPending ? 'Opening Google…' : 'Reconnect Google account'}</button></div>}</div></div> : <button onClick={reconnect} disabled={connect.isPending} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-emerald-400 px-3 py-2 text-sm font-medium text-black"><Link2 className="h-4 w-4" />{connect.isPending ? 'Opening Google…' : 'Connect Google Business Profile'}</button>}
    </section>

    <section className="mt-4 rounded-xl border border-white/10 bg-white/5 p-5"><h2 className="font-medium">Reply automation</h2><p className="mt-1 text-sm text-gray-400">Five-star replies can be automated only when enabled below. Four-star and lower reviews always need approval.</p><label className="mt-4 block text-sm text-gray-300">Brand voice</label><textarea value={voice} onChange={event => setVoice(event.target.value)} maxLength={4000} className="mt-1 min-h-28 w-full rounded border border-white/15 bg-black/20 p-3 text-sm" placeholder="Example: appreciative, neighborly, professional" /><label className="mt-4 block text-sm text-gray-300">Additional reply policy (optional)</label><textarea value={policy} onChange={event => setPolicy(event.target.value)} maxLength={4000} className="mt-1 min-h-20 w-full rounded border border-white/15 bg-black/20 p-3 text-sm" placeholder="Optional tenant-specific rules" /><label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={autoPublish} onChange={event => setAutoPublish(event.target.checked)} /> Auto-publish AI replies to 5-star reviews</label><label className="mt-4 block text-sm text-gray-300">Alert recipients</label><input value={recipients} onChange={event => setRecipients(event.target.value)} className="mt-1 w-full rounded border border-white/15 bg-black/20 p-3 text-sm" placeholder="manager@example.com, owner@example.com" /><button onClick={() => save.mutate()} disabled={save.isPending} className="mt-4 rounded bg-white/10 px-3 py-2 text-sm hover:bg-white/15">{save.isPending ? 'Saving…' : 'Save settings'}</button></section>
  </div>
}
