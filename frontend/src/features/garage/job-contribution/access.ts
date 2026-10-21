import { useAuthStore } from '@/stores/authStore'
export function isCostOwner(state: ReturnType<typeof useAuthStore.getState>) { return Boolean(state.isAuthenticated && !state.logoutInProgress && state.user?.is_active && state.user.role === 'garage_owner' && state.user.tenant_id) }
