// A drill-in can return only to an internal customer or inventory record in the same staff session.
export type WorkspaceVisit = {
  scope: string
  pathname: '/dashboard/customers' | '/dashboard/garage/inventory'
  search: string
  record: string
  triggerId?: string
}

export function readWorkspaceVisit(state: unknown, scope: string): WorkspaceVisit | null {
  const visit = (state as { workspaceVisit?: Partial<WorkspaceVisit> } | null)?.workspaceVisit
  if (visit?.scope !== scope || (visit.pathname !== '/dashboard/customers' && visit.pathname !== '/dashboard/garage/inventory')
    || typeof visit.record !== 'string' || !visit.record || typeof visit.search !== 'string' || !visit.search.startsWith('?')
    || !new URLSearchParams(visit.search).get('selected')) return null
  return visit as WorkspaceVisit
}
