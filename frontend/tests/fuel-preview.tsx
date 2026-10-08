/** Synthetic UI acceptance only; no external requests or production data. */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../src/contexts/ThemeContext'
import TripOverview from '../src/features/fleet/TripOverview'
import type { FleetTripsResponse } from '../src/features/fleet/FleetTrips'
import type { BoardTruck } from '../src/features/fleet/types'
import type { FuelDaily } from '../src/features/fleet/fuelDaily'
import api from '../src/lib/api'
import '../src/index.css'
import '../src/features/fleet/fleet.css'
import '../src/features/fleet/trips.css'
if (!import.meta.env.DEV) throw new Error('Development only')
api.defaults.adapter = async config => ({ data: {}, status: 200, statusText: 'OK', headers: {}, config })
const trucks = ['860', '609', '531', '26'].map((unit, i) => ({ id: String(i), unit_number: unit, display_unit_number: unit, driver_name: 'Example driver' } as BoardTruck))
const items = trucks.map((truck, i) => ({ id: `trip-${i}`, vehicle_id: truck.id, unit_number: truck.unit_number, fleet_customer_id: 'example', fleet_name: 'Example fleet', started_at: '2026-10-05T13:00:00Z', ended_at: '2026-10-05T16:00:00Z', distance_miles: 180-i*20, driving_seconds: 10800, origin_label: 'Example origin', destination_label: 'Example destination', source: 'motive_dashboard_manual', captured_at: '2026-10-06T16:00:00Z', stops: null, ...(i === 0 ? { metrics: { fuel_used_gallons: null, trip_mpg: null, estimated_fuel_gallons: 30, estimate_baseline_mpg: 6, estimate_baseline_period: 'last_30_days', estimate_baseline_captured_at: '2026-10-06T16:00:00Z', idle_seconds: null, fuel_start_percent: null, fuel_end_percent: null } } : {}) })) as FleetTripsResponse['items']
const data: FleetTripsResponse = { items, summary: { coverage: 'partial', truck_count: 4, trip_count: 4, distance_miles: 600, driving_seconds: 43200 }, total: 4, limit: 50, offset: 0, timezone: 'America/New_York', start_date: '2026-10-05', end_date: '2026-10-05' }
const base: FuelDaily = { vehicle_id: '0', report_date: '2026-10-05', source_timezone: null, timezone_status: 'unverified', driving_fuel_gallons: 28, idling_fuel_gallons: 2, reported_total_fuel_gallons: 30, source_distance_miles: 180, source_driving_seconds: 10800, source_idling_seconds: 1200 }
const fuel = [base, { ...base, vehicle_id: '1', driving_fuel_gallons: 25, idling_fuel_gallons: null, reported_total_fuel_gallons: null }, { ...base, vehicle_id: '2', driving_fuel_gallons: 0, idling_fuel_gallons: 0, reported_total_fuel_gallons: 0 }]
ReactDOM.createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><ThemeProvider><main className="fleet-root" style={{ padding: 24, minHeight: '100vh', overflow: 'auto' }}><h1>Fuel report acceptance preview</h1><TripOverview data={data} trucks={trucks} timezone="America/New_York" selected={false} onSelectTruck={() => {}} renderDetails={() => null} fuelRecords={fuel} /></main></ThemeProvider></MemoryRouter></QueryClientProvider>)
