import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import TemplateTaskEditor from './TemplateTaskEditor'
import { checklistKeys, errorDetail, isConflict } from './queries'
import { checklistTemplateSchema } from './schemas'
import type { ServiceChecklistTemplate, TemplateTaskDraft } from './types'

export default function ServiceChecklistEditor({ serviceId, initialDraft, onSaved }: {
  serviceId: string; initialDraft?: TemplateTaskDraft[]; onSaved?: () => void
}) {
  const user = useAuthStore(state => state.user)
  const sessionEpoch = useAuthStore(state => state.authSessionEpoch)
  if (!user?.tenant_id || !['garage_owner', 'garage_admin'].includes(user.role)) return null
  return <Editor key={`${user.tenant_id}:${user.id}:${user.role}:${sessionEpoch}:${serviceId}`} tenantId={user.tenant_id} serviceId={serviceId} initialDraft={initialDraft} onSaved={onSaved} />
}
function Editor({ tenantId, serviceId, initialDraft, onSaved }: {
  tenantId: string; serviceId: string; initialDraft?: TemplateTaskDraft[]; onSaved?: () => void
}) {
  const client = useQueryClient()
  const [draft, setDraft] = useState<TemplateTaskDraft[] | null>(initialDraft ?? null)
  const [version, setVersion] = useState<number | null>(initialDraft ? 0 : null)
  const [message, setMessage] = useState(initialDraft ? 'Service created. Checklist has not been saved. Retry below.' : '')
  const [conflict, setConflict] = useState(false)
  const active = useRef(true)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  const query = useQuery({
    queryKey: checklistKeys.template(tenantId, serviceId),
    queryFn: async ({ signal }) => {
      const template = checklistTemplateSchema.parse((await api.get(`/services/${serviceId}/checklist`, { signal })).data)
      if (template.service_id !== serviceId) throw new Error('Checklist does not match this service')
      return template
    },
    staleTime: 0,
  })
  const items = draft ?? query.data?.items ?? []
  const expectedVersion = version ?? query.data?.version
  const save = useMutation({
    mutationFn: async () => (await api.put<ServiceChecklistTemplate>(`/services/${serviceId}/checklist`, {
      expected_version: expectedVersion, items: items.map(item => ({ ...item, label: item.label.trim() })),
    })).data,
    onSuccess: data => {
      client.setQueryData(checklistKeys.template(tenantId, serviceId), data)
      if (!active.current) return
      setDraft(null); setVersion(null); setConflict(false); setMessage('Checklist saved. Existing jobs keep their original tasks.'); onSaved?.()
    },
    onError: error => {
      if (!active.current) return
      setMessage(errorDetail(error, 'Checklist could not be saved. Your edits are still here.'))
      setConflict(isConflict(error))
    },
  })
  const change = (next: TemplateTaskDraft[]) => { setVersion(expectedVersion ?? null); setDraft(next); setMessage('Unsaved checklist changes') }
  return <section aria-label="Service checklist" className="space-y-3 border-t border-gray-200 pt-4">
    <div><h3 className="text-sm font-semibold text-gray-900">Checklist</h3><p className="mt-1 text-xs text-gray-500">Required tasks must be checked before finishing the job. Changes apply to future jobs.</p></div>
    {query.isPending && !initialDraft ? <p role="status" className="text-sm text-gray-500">Loading checklist…</p> : <>
      {query.isError && <p role="alert" className="text-sm text-red-700">Could not load the checklist. <button type="button" onClick={() => void query.refetch()} className="underline">Retry</button></p>}
      {(!query.isError || draft !== null) && <TemplateTaskEditor items={items} onChange={change} disabled={save.isPending} />}
      {message && <p role={save.isError || conflict ? 'alert' : 'status'} className={`text-xs ${save.isError || conflict ? 'text-red-700' : 'text-gray-600'}`}>{message}</p>}
      {conflict && <button type="button" className="min-h-10 whitespace-nowrap text-sm font-semibold text-gray-700 underline" onClick={async () => {
        const result = await query.refetch()
        if (!active.current || !result.data || result.isError) return
        save.reset(); setDraft(null); setVersion(null); setConflict(false); setMessage('Latest checklist loaded. Reapply your changes before saving.')
      }}>Discard edits and reload</button>}
      <button type="button" disabled={save.isPending || conflict || draft === null || expectedVersion == null || items.some(item => !item.label.trim())}
        onClick={() => save.mutate()} className="min-h-10 whitespace-nowrap rounded-lg bg-gray-900 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{save.isPending ? 'Saving checklist…' : 'Save checklist'}</button>
    </>}
  </section>
}
