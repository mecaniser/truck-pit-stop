export type DraftIdentity = { id: string; tenant_id: string | null; role: string; customer_id: string | null; is_active: boolean }
export type DraftEnvelope = { version: 1; identity: string; savedAt: number; uncertain: boolean; data: unknown }
const PREFIX = 'dieselbridge:form-draft:v1:'
const TTL = 2 * 60 * 60 * 1000
const writers = new Set<(identity: string) => void>()
export function draftIdentity(user: DraftIdentity | null): string | null {
  return user?.is_active ? JSON.stringify([user.tenant_id, user.id, user.role, user.customer_id]) : null
}
export function registerDraftWriter(writer: (identity: string) => void) {
  writers.add(writer)
  return () => { writers.delete(writer) }
}
export function captureFormDrafts(user: DraftIdentity | null) {
  const identity = draftIdentity(user)
  if (identity) writers.forEach(writer => { try { writer(identity) } catch { /* Never block session termination. */ } })
}
export function removeFormDraft(kind: string) {
  try { sessionStorage.removeItem(PREFIX + kind) } catch { /* Storage may be disabled. */ }
}
export function clearFormDrafts() {
  try {
    Object.keys(sessionStorage).filter(key => key.startsWith(PREFIX)).forEach(key => sessionStorage.removeItem(key))
  } catch { /* Storage may be disabled. */ }
}
export function saveFormDraft(kind: string, identity: string, data: unknown, uncertain: boolean) {
  try {
    const value = JSON.stringify({ version: 1, identity, savedAt: Date.now(), data, uncertain })
    if (value.length > 100_000) return false
    sessionStorage.setItem(PREFIX + kind, value)
    return true
  } catch { return false }
}
export function readFormDraft(kind: string, identity: string): DraftEnvelope | null {
  try {
    const raw = sessionStorage.getItem(PREFIX + kind)
    if (!raw) return null
    const value = JSON.parse(raw)
    if (raw.length > 100_000 || value.version !== 1 || value.identity !== identity || typeof value.uncertain !== 'boolean'
      || !Number.isFinite(value.savedAt) || Date.now() - value.savedAt > TTL || value.savedAt > Date.now()) {
      removeFormDraft(kind)
      return null
    }
    return value
  } catch { removeFormDraft(kind); return null }
}
