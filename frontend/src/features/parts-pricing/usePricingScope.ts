import { useAuthStore } from '@/stores/authStore'
export function usePricingScope() {
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  return JSON.stringify([user?.tenant_id, user?.id, user?.role, epoch])
}

export function isPricingScopeCurrent(scope: string) {
  const state = useAuthStore.getState()
  return !state.logoutInProgress && scope === JSON.stringify([state.user?.tenant_id, state.user?.id, state.user?.role, state.authSessionEpoch])
}
