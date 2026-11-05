import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'
import api from '@/lib/api'
import { ControlButton } from '@/components/ui/Controls'
import { Spinner } from '@/components/ui'
import AccountConfirmationDialog from './AccountConfirmationDialog'

const FIELDS = ['invoice_email', 'invoice_sms', 'repair_email', 'repair_sms'] as const
type Choice = typeof FIELDS[number]
type Choices = Record<Choice, boolean>
type Preferences = Choices & { context_key: string; revision: number; has_email: boolean; has_phone: boolean; sms_opted_out: boolean }
const values = (data: Preferences): Choices => Object.fromEntries(FIELDS.map(name => [name, data[name]])) as Choices

export default function NotificationPreferencesSection({ onDirtyChange }: { onDirtyChange: (dirty: boolean) => void }) {
  const auth = useAuthStore()
  const scope = getAuthenticatedSessionIdentity(auth)
  return scope ? <PreferencesEditor key={scope} scope={scope} onDirtyChange={onDirtyChange} /> : null
}

function PreferencesEditor({ scope, onDirtyChange }: { scope: string; onDirtyChange: (dirty: boolean) => void }) {
  const client = useQueryClient()
  const key = ['customer-notification-preferences', scope]
  const query = useQuery<Preferences>({
    queryKey: key, retry: false,
    queryFn: async ({ signal }) => (await api.get('/auth/me/notification-preferences', { signal })).data,
  })
  const [baseline, setBaseline] = useState<Preferences | null>(null)
  const [saveError, setSaveError] = useState('')
  const [requiresReload, setRequiresReload] = useState(false)
  const [reloadDialog, setReloadDialog] = useState(false)
  const [saved, setSaved] = useState(false)
  const { reset, setValue, watch, handleSubmit, formState: { isDirty } } = useForm<Choices>()
  const draft = watch()
  useEffect(() => { onDirtyChange(isDirty) }, [isDirty, onDirtyChange])
  useEffect(() => () => onDirtyChange(false), [onDirtyChange])
  useEffect(() => {
    if (query.data && !isDirty) { setBaseline(query.data); reset(values(query.data)) }
  }, [query.data, isDirty, reset])
  useEffect(() => {
    if (!isDirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [isDirty])
  const current = () => getAuthenticatedSessionIdentity(useAuthStore.getState()) === scope
  const save = useMutation({
    retry: false,
    mutationFn: async (data: Choices) => {
      if (!baseline) throw new Error('Preferences are unavailable')
      return (await api.put<Preferences>('/auth/me/notification-preferences', { ...data, expected_context: baseline.context_key, base_revision: baseline.revision })).data
    },
    onSuccess: data => {
      if (!current()) return
      client.setQueryData(key, data)
      setBaseline(data); reset(values(data)); setSaveError(''); setRequiresReload(false); setSaved(true)
    },
    onError: (error: { response?: { status?: number } }) => {
      if (!current()) return
      setRequiresReload(true); setSaved(false)
      setSaveError(error.response?.status === 409 ? 'These preferences changed elsewhere. Reload them before saving.' : 'We could not confirm whether your preferences were saved. Reload them before trying again.')
    },
  })
  const reload = async () => {
    setReloadDialog(false)
    const result = await query.refetch()
    if (!current()) return
    if (result.data && !result.error) {
      setBaseline(result.data); reset(values(result.data)); setSaveError(''); setRequiresReload(false); setSaved(false)
    }
  }
  if (query.isLoading || (!baseline && query.isSuccess)) return <div role="status" className="flex items-center gap-3 py-6"><Spinner />Loading notification preferences…</div>
  if (query.isError && !baseline) return <div role="alert" className="space-y-3"><p>Unable to load notification preferences.</p><ControlButton type="button" disabled={query.isFetching} onClick={() => void query.refetch()} className="text-violet-300 underline">Retry loading preferences</ControlButton></div>
  if (!baseline) return null
  return <form onSubmit={handleSubmit(data => save.mutate(data))} className="space-y-6">
    <div>
      <h2 className="text-lg font-semibold">Notifications</h2>
      <p className="mt-2 text-sm text-gray-400">Choose automatic updates for your customer account at this shop. Saved preferences apply across browsers and devices.</p>
    </div>
    {baseline.sms_opted_out && <p role="status" className="rounded-lg border border-amber-300/30 bg-amber-300/5 p-3 text-sm text-amber-200">Text messages are currently opted out. These settings cannot re-enable text delivery. Contact your shop for help.</p>}
    {(!baseline.has_email || !baseline.has_phone) && <p className="text-sm text-gray-400">Delivery requires a current email address or phone number in Profile.</p>}
    <div className="divide-y divide-[#30384b]">
      {([
        { title: 'Invoice updates', detail: 'New invoices by email, and payment reminders by email or text.', prefix: 'invoice' },
        { title: 'Repair updates', detail: 'Work-started emails and text updates when work starts, finishes, or is ready for pickup.', prefix: 'repair' },
      ] as const).map(topic => <fieldset key={topic.prefix} disabled={save.isPending || query.isFetching} className="py-4 first:pt-0">
        <legend className="sr-only">{topic.title}</legend>
        <h3 className="font-semibold">{topic.title}</h3>
        <p className="mt-1 text-sm text-gray-400">{topic.detail}</p>
        <div className="mt-3 flex flex-wrap gap-3">
          {(['email', 'sms'] as const).map(channel => {
            const name = (topic.prefix + '_' + channel) as Choice
            const label = channel === 'email' ? 'Email' : 'Text messages'
            return <ControlButton key={name} type="button" role="switch" aria-checked={Boolean(draft[name])} aria-label={topic.title + ': ' + label}
              disabled={channel === 'sms' && baseline.sms_opted_out}
              onClick={() => { setSaved(false); setValue(name, !draft[name], { shouldDirty: true }) }}
              className="min-w-[140px] justify-between rounded-lg border border-[#434c63] px-3 text-sm text-[#eceef4] disabled:opacity-50">
              {label}<span aria-hidden="true" className={draft[name] ? 'font-semibold text-violet-200' : 'text-gray-400'}>{draft[name] ? 'On' : 'Off'}</span>
            </ControlButton>
          })}
        </div>
      </fieldset>)}
      <div className="py-4"><h3 className="font-semibold">Maintenance reminders</h3><p className="mt-1 text-sm text-gray-400">Customer maintenance reminders are not available yet.</p></div>
    </div>
    <p className="text-sm text-gray-400">Security notices, receipts, approval requests and direct messages from your shop are handled separately. Messages already being sent may still arrive.</p>
    {saveError && <div role="alert" className="space-y-2 text-sm text-red-300"><p>{saveError}</p><ControlButton type="button" disabled={query.isFetching} onClick={() => isDirty ? setReloadDialog(true) : void reload()} className="underline">Reload preferences</ControlButton></div>}
    <div className="flex flex-wrap items-center gap-3 border-t border-[#30384b] pt-4">
      <ControlButton type="submit" disabled={!isDirty || save.isPending || requiresReload || query.isFetching} className="rounded-lg bg-violet-600 px-4 font-semibold text-white hover:bg-violet-500 disabled:opacity-50">{save.isPending ? 'Saving…' : 'Save preferences'}</ControlButton>
      {isDirty && <ControlButton type="button" disabled={save.isPending} onClick={() => { reset(values(baseline)); setSaved(false) }} className="text-gray-300">Cancel</ControlButton>}
      <span role="status" className="text-sm text-gray-400">{isDirty ? 'Unsaved changes' : saved ? 'Preferences saved' : ''}</span>
    </div>
    <AccountConfirmationDialog open={reloadDialog} title="Reload notification preferences?" description="Reloading will discard your unsaved notification choices and show the current saved preferences." confirmLabel="Reload preferences" cancelLabel="Keep editing" onCancel={() => setReloadDialog(false)} onConfirm={() => void reload()} />
  </form>
}
