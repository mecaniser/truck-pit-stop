import { deepFreeze } from './appearance'

export const tenantBranding = deepFreeze({ name: 'Truck Pit Stop Wisconsin', state: 'WI', logo_url: '/tenant-logo.svg' })
export const longTenantBranding = deepFreeze({ name: 'Wisconsin Commercial Diesel Repair and Fleet Operations Center', state: 'WI', logo_url: null })
export const absentTenantLogo = deepFreeze({ name: 'Northline Garage', state: 'NC', logo_url: null })
export const oversizedTenantLogo = deepFreeze({ name: 'Northline Garage', state: 'NC', logo_url: '/oversized-tenant-logo.svg' })
