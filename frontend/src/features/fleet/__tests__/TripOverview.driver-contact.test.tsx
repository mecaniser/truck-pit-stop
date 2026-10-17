import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TripOverview from '../TripOverview'
import type { FleetTripsResponse } from '../FleetTrips'
import { driverTruck } from './driverRecordFixture'

const trips: FleetTripsResponse = {
  items: [{
    id: 'trip-1', vehicle_id: driverTruck.id, unit_number: 'TEST-1', fleet_customer_id: 'synthetic-company', fleet_name: 'Example Fleet',
    started_at: '2026-10-15T12:00:00Z', ended_at: '2026-10-15T13:00:00Z', origin_label: 'Origin', destination_label: 'Destination',
    distance_miles: 50, driving_seconds: 3600, captured_at: '2026-10-16T12:00:00Z', source: 'motive_dashboard_manual', stops: null,
  }],
  summary: { truck_count: 1, trip_count: 1, distance_miles: 50, driving_seconds: 3600, coverage: 'partial' },
  total: 1, limit: 50, offset: 0, timezone: 'America/New_York', start_date: '2026-10-15', end_date: '2026-10-15',
}

describe('Trips driver identity', () => {
  it('shows the current driver and score without local contact details', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><TripOverview data={trips} trucks={[driverTruck]} timezone="America/New_York" selected={false} onSelectTruck={() => {}} renderDetails={() => null} /></QueryClientProvider>)
    expect(screen.getByText('Example Driver')).toBeVisible()
    expect(screen.getByRole('button', { name: /Driver record for Example Driver/ })).toHaveTextContent('82')
    expect(screen.queryByText('Example · (704) 555-0123')).not.toBeInTheDocument()
    expect(document.querySelector('a[href^="tel:"]')).toBeNull()
  })
})
