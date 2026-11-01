import { useEffect, useRef, useState } from 'react'
import type { ZodType } from 'zod'
import api from '../lib/api'
import { useAuthStore } from '../stores/authStore'
import { draftIdentity, readFormDraft, registerDraftWriter, removeFormDraft, saveFormDraft } from '../lib/formDrafts'

/** Explicitly opted-in fields only; writes a draft synchronously before session clear. */
export function useFormDraftRecovery<T>(kind: string, active: boolean, data: T, schema: ZodType<T>) {
  const user = useAuthStore(s => s.user)
  const identity = draftIdentity(user)
  const [candidate, setCandidate] = useState<{ data: T; uncertain: boolean; identity: string; savedAt: number } | null>(null)
  const openingOwner = useRef<string | null>(null)
  const previouslyActive = useRef(false)
  const suppressed = useRef(false)
  if (active && !previouslyActive.current) {
    openingOwner.current = identity
    suppressed.current = false
  }
  previouslyActive.current = active
  const latest = useRef({ active, data, identity })
  latest.current = { active, data, identity }
  const uncertain = useRef(false)
  const generation = useRef(0)
  useEffect(() => registerDraftWriter(owner => {
    const current = latest.current
    if (suppressed.current || !current.active || current.identity !== owner || openingOwner.current !== owner) return
    const parsed = schema.safeParse(current.data)
    if (parsed.success) saveFormDraft(kind, owner, parsed.data, uncertain.current)
  }), [kind, schema])
  useEffect(() => {
    setCandidate(null)
    if (!identity) return
    const envelope = readFormDraft(kind, identity)
    if (!envelope) return
    const loadGeneration = generation.current
    let live = true
    // Persisted auth flags alone are not sufficient authority to show a draft.
    void api.get('/auth/me').then(response => {
      if (!live || generation.current !== loadGeneration || draftIdentity(response.data) !== identity || draftIdentity(useAuthStore.getState().user) !== identity) return
      const parsed = schema.safeParse(envelope.data)
      if (parsed.success) setCandidate({ data: parsed.data, uncertain: envelope.uncertain, identity, savedAt: envelope.savedAt })
      else removeFormDraft(kind)
    }).catch(() => { /* Keep the draft for the next verified sign-in. */ })
    return () => { live = false }
  }, [identity, kind, schema])
  return {
    candidate: candidate?.identity === identity ? candidate : null,
    restoreData: (): T => {
      if (latest.current.active) throw new Error('A newer form is open')
      const owner = draftIdentity(useAuthStore.getState().user)
      if (!owner || candidate?.identity !== owner) throw new Error('Session changed')
      const envelope = readFormDraft(kind, owner)
      if (!envelope || envelope.savedAt !== candidate.savedAt) throw new Error('Draft expired or changed')
      return schema.parse(envelope.data)
    },
    markSubmitting: () => { uncertain.current = true },
    clear: () => { generation.current += 1; suppressed.current = true; uncertain.current = false; removeFormDraft(kind); setCandidate(null) },
  }
}
