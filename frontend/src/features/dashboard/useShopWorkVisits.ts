import { useQuery } from '@tanstack/react-query'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'
import { useStaffRequests, visitRequestStaffRoles } from '@/features/appointments/staffVisitRequestQueries'
import { getPortalItems } from '@/features/customer-portal/portal-context'
import type { StaffBooking } from '@/features/appointments/booking-fulfillment'

export function useShopWorkVisits() {
  const identity = useAuthStore(getAuthenticatedSessionIdentity)
  const role = useAuthStore(state => state.user?.role)
  const allowed = !!identity && visitRequestStaffRoles.includes(role || '')
  const requests = useStaffRequests(identity, allowed)
  const reservations = useQuery({
    queryKey: ['staff-reservations', identity, 'confirmed'],
    queryFn: ({ signal }) => getPortalItems<StaffBooking>('/appointments', { status_filter: 'confirmed' }, signal),
    enabled: allowed, retry: false, refetchInterval: 60000,
  })
  return { allowed, requests, reservations }
}
