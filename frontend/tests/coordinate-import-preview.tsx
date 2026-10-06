import React from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import api from '../src/lib/api'
import { useAuthStore } from '../src/stores/authStore'
import CoordinateImport from '../src/features/fleet/CoordinateImport'
import { exampleObservation } from '../src/features/fleet/coordinateImportModel'
const actor = { id: '22222222-2222-4222-8222-222222222222', tenant_id: exampleObservation.expected_tenant_id, role: 'garage_owner', is_active: true, first_name: 'Synthetic', last_name: 'Worker', email: 'synthetic@example.invalid', phone: null, customer_id: null } as const
useAuthStore.setState({ user: actor, isAuthenticated: true, token: null })
let request: Record<string, unknown> | null = null
const receipt = { id: '55555555-5555-4555-8555-555555555555', vehicle_id: '33333333-3333-4333-8333-333333333333', fleet_customer_id: '44444444-4444-4444-8444-444444444444', captured_by_user_id: actor.id, captured_at: new Date().toISOString(), observed_at: null, source: 'motive_dashboard_manual' }
api.defaults.adapter = async config => {
 let data: unknown; let status = 200
 if (config.url === '/auth/me') data = actor
 else if (config.url === '/fleet/board') data = { trucks: [{ id: receipt.vehicle_id, vin: exampleObservation.vin, board_membership_customer_id: receipt.fleet_customer_id, telemetry: request ? { location: { lat: request.lat, lng: request.lng, snapshot_id: receipt.id, observed_at: request.observed_at } } : null }] }
 else if (config.method === 'post' && config.url === `/fleet/trucks/${receipt.vehicle_id}/telemetry-snapshots`) { status = request ? 200 : 201; request = JSON.parse(config.data); data = receipt }
 else throw Error('Synthetic preview blocks all other requests')
 return { data, status, statusText: 'Synthetic', headers: {}, config }
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><MemoryRouter><CoordinateImport /></MemoryRouter></React.StrictMode>)
