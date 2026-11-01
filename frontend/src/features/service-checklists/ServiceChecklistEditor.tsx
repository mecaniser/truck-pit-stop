import { ControlButton } from '@/components/ui/Controls'
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import TemplateTaskEditor from './TemplateTaskEditor'
import { checklistKeys, errorDetail, isConflict } from './queries'
import { checklistTemplateSchema } from './schemas'
import type { ServiceChecklistTemplate, TemplateTaskDraft } from './types'

export interface ServiceChecklistEditorHandle {
  saveBeforeClose: () => Promise<boolean>
}

export default function ServiceChecklistEditor({ serviceId, initialDraft, onSaved, editorRef }: {
  serviceId: string; initialDraft?: TemplateTaskDraft[]; onSaved?: () => void; editorRef?: Ref<ServiceChecklistEditorHandle>
}) {
  const user = useAuthStore(state => state.user)
  const sessionEpoch = useAuthStore(state => state.authSessionEpoch)
  if (!user?.tenant_id || !['garage_owner', 'garage_admin'].includes(user.role)) return null
  return <Editor key={`${user.tenant_id}:${user.id}:${user.role}:${sessionEpoch}:${serviceId}`} tenantId={user.tenant_id} serviceId={serviceId} initialDraft={initialDraft} onSaved={onSaved} editorRef={editorRef} />
}
function Editor({ tenantId, serviceId, initialDraft, onSaved, editorRef }: {
  tenantId: string; serviceId: string; initialDraft?: TemplateTaskDraft[]; onSaved?: () => void; editorRef?: Ref<ServiceChecklistEditorHandle>
}) {
  const client = useQueryClient()
  const [draft, setDraft] = useState<TemplateTaskDraft[] | null>(initialDraft ?? null)
  const [version, setVersion] = useState<number | null>(initialDraft ? 0 : null)
  const [message, setMessage] = useState(initialDraft ? 'Service created. Checklist has not been saved. Retry below.' : '')
  const [conflict, setConflict] = useState(false)
  const [validationError, setValidationError] = useState(false)
  const section = useRef<HTMLElement>(null)
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
    mutationFn: async () => {
      const saved = checklistTemplateSchema.parse((await api.put<ServiceChecklistTemplate>(`/services/${serviceId}/checklist`, {
        expected_version: expectedVersion, items: items.map(item => ({ ...item, label: item.label.trim() })),
      })).data)
      if (saved.service_id !== serviceId) throw new Error('Checklist does not match this service')
      return saved
    },
    onSuccess: data => {
      client.setQueryData(checklistKeys.template(tenantId, serviceId), data)
      if (!active.current) return
      setDraft(null); setVersion(null); setConflict(false); setValidationError(false); setMessage('Checklist saved. Existing jobs keep their original tasks.'); onSaved?.()
    },
    onError: error => {
      if (!active.current) return
      setMessage(errorDetail(error, 'Checklist could not be saved. Your edits are still here.'))
      setConflict(isConflict(error))
    },
  })
  useImperativeHandle(editorRef, () => ({
    saveBeforeClose: async () => {
      if (save.isPending) return false
      if (draft === null) return true
      if (conflict || expectedVersion == null || items.some(item => !item.label.trim())) {
        setValidationError(true)
        setMessage(conflict ? 'Reload the latest checklist before saving.' : expectedVersion == null
          ? 'The checklist must finish loading before saving.'
          : 'Enter a label for each task, or remove empty tasks, before closing.')
        section.current?.scrollIntoView?.({ block: 'nearest' })
        return false
      }
      try {
        await save.mutateAsync()
        return active.current
      } catch {
        section.current?.scrollIntoView?.({ block: 'nearest' })
        return false
      }
    },
  }))
  const change = (next: TemplateTaskDraft[]) => { setVersion(expectedVersion ?? null); setDraft(next); setValidationError(false); setMessage('Unsaved checklist changes') }
  return <section ref={section} aria-label="Service checklist" className="space-y-3 border-t border-gray-200 pt-4">
    <div><h3 className="text-sm font-semibold !text-[#111827]">Checklist</h3><p className="mt-1 text-xs !text-[#4b5563]">Required tasks must be checked before finishing the job. Changes apply to future jobs.</p></div>
    {query.isPending && !initialDraft ? <p role="status" className="text-sm !text-[#4b5563]">Loading checklist…</p> : <>
      {query.isError && <p role="alert" className="text-sm !text-[#b91c1c]">Could not load the checklist. <ControlButton type="button" onClick={() => void query.refetch()} className="underline">Retry</ControlButton></p>}
      {(!query.isError || draft !== null) && <TemplateTaskEditor items={items} onChange={change} disabled={save.isPending} />}
      {message && <p role={save.isError || conflict || validationError ? 'alert' : 'status'} className={`text-xs ${save.isError || conflict || validationError ? '!text-[#b91c1c]' : '!text-[#4b5563]'}`}>{message}</p>}
      {conflict && <ControlButton type="button" className=" whitespace-nowrap text-sm font-semibold !text-[#374151] underline" onClick={async () => {
        const result = await query.refetch()
        if (!active.current || !result.data || result.isError) return
        save.reset(); setDraft(null); setVersion(null); setConflict(false); setValidationError(false); setMessage('Latest checklist loaded. Reapply your changes before saving.')
      }}>Discard edits and reload</ControlButton>}
      <ControlButton type="button" disabled={save.isPending || conflict || draft === null || expectedVersion == null || items.some(item => !item.label.trim())}
        onClick={() => save.mutate()} className=" whitespace-nowrap rounded-lg !bg-[#111827] px-3  text-xs font-semibold !text-[#ffffff] disabled:opacity-40">{save.isPending ? 'Saving checklist…' : 'Save checklist'}</ControlButton>
    </>}
  </section>
}
