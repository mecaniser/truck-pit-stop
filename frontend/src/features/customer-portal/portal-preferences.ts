export type CustomerPortalPreferences = {
  defaultPaymentMethod: 'zelle' | 'card'
  notifications: {
    invoiceReady: boolean
    repairStatus: boolean
    pmReminders: boolean
  }
}

const defaults: CustomerPortalPreferences = {
  defaultPaymentMethod: 'zelle',
  notifications: {
    invoiceReady: true,
    repairStatus: true,
    pmReminders: true,
  },
}

export function portalPreferencesKey(customerId: string | null | undefined) {
  return `truck-pit-stop:customer-portal-preferences:${customerId || 'guest'}`
}

export function getPortalPreferences(customerId: string | null | undefined): CustomerPortalPreferences {
  if (typeof window === 'undefined') return defaults
  try {
    const saved = JSON.parse(window.localStorage.getItem(portalPreferencesKey(customerId)) || '{}')
    return {
      defaultPaymentMethod: saved.defaultPaymentMethod === 'card' ? 'card' : 'zelle',
      notifications: {
        invoiceReady: saved.notifications?.invoiceReady ?? true,
        repairStatus: saved.notifications?.repairStatus ?? true,
        pmReminders: saved.notifications?.pmReminders ?? true,
      },
    }
  } catch {
    return defaults
  }
}

export function savePortalPreferences(
  customerId: string | null | undefined,
  preferences: CustomerPortalPreferences,
) {
  window.localStorage.setItem(portalPreferencesKey(customerId), JSON.stringify(preferences))
}
