import { useQuery } from '@tanstack/react-query'

import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type { TenantBranding } from '@/types'

export function tenantBrandingQueryKey(tenantId: string | null | undefined) {
  return ['tenant-branding', tenantId ?? 'none'] as const
}

export default function useTenantBranding() {
  const user = useAuthStore((state) => state.user)
  const tenantId = user?.tenant_id ?? null
  const enabled = Boolean(tenantId && user?.role !== 'super_admin')

  return useQuery({
    queryKey: tenantBrandingQueryKey(tenantId),
    queryFn: async () => {
      const { data } = await api.get<TenantBranding>('/auth/tenant-branding')
      return data
    },
    enabled,
    initialData: enabled
      ? {
          name: user?.tenant_name ?? null,
          slug: user?.tenant_slug ?? null,
          logo_url: user?.tenant_logo_url ?? null,
          state: null,
        }
      : undefined,
    staleTime: 60_000,
  })
}
