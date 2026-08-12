import { deepFreeze, presentationFixture } from './appearance'

const base = {
  email: 'owner@example.test', first_name: 'Alex', last_name: 'Rivera', phone: null, is_active: true,
  tenant_id: 'tenant-wisconsin', tenant_name: 'Truck Pit Stop Wisconsin', tenant_slug: 'wisconsin', tenant_logo_url: null, customer_id: null,
  presentation: presentationFixture('new'),
}

export const garageOwnerSession = deepFreeze({ ...base, id: 'user-owner', role: 'garage_owner' as const })
export const garageAdminSession = deepFreeze({ ...base, id: 'user-admin', role: 'garage_admin' as const })
export const receptionistSession = deepFreeze({ ...base, id: 'user-reception', role: 'receptionist' as const })
export const assignedMechanicSession = deepFreeze({ ...base, id: 'user-mechanic', role: 'mechanic' as const })
export const fleetManagerWithMessaging = deepFreeze({ ...base, id: 'user-fleet-message', role: 'fleet_manager' as const, can_access_messaging: true })
export const fleetManagerWithoutMessaging = deepFreeze({ ...base, id: 'user-fleet', role: 'fleet_manager' as const, can_access_messaging: false })
export const sameUserOtherTenant = deepFreeze({ ...garageOwnerSession, tenant_id: 'tenant-north-carolina', tenant_name: 'Truck Pit Stop' })
export const secondUserSameTenant = deepFreeze({ ...garageOwnerSession, id: 'user-owner-2', email: 'second@example.test' })
