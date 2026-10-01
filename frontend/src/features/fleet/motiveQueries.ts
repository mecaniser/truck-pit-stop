import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/authStore'
import api from '@/lib/api'

export interface MotiveCompany {
  id: string; company_name: string; fleet_enabled: boolean;
  is_internal_fleet?: boolean; can_manage_grants?: boolean;
}

export function useMotiveCompanies() {
  const user = useAuthStore((state) => state.user)
  const allowed = ['garage_owner', 'garage_admin', 'customer'].includes(user?.role ?? '')
  return useQuery<{ items: MotiveCompany[] }>({
    queryKey: ['motive-companies', user?.id, user?.tenant_id, user?.customer_id],
    queryFn: async ({ signal }) => (await api.get('/fleet/motive/companies', { signal })).data,
    enabled: allowed, retry: false, refetchInterval: 60000,
  })
}
