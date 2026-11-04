import { useQuery } from '@tanstack/react-query'
import { getPortalItems } from '@/features/customer-portal/portal-context'
import type { StaffVisitRequest } from './visit-requests'
export const visitRequestStaffRoles = ['garage_owner', 'garage_admin', 'receptionist']
export function useStaffRequests(identity: string | null, enabled = true) {
  return useQuery({ queryKey: ['staff-visit-requests', identity], queryFn: ({ signal }) => getPortalItems<StaffVisitRequest>('/appointments/visit-requests', {}, signal), enabled: !!identity && enabled, retry: false, refetchInterval: 60000 })
}
