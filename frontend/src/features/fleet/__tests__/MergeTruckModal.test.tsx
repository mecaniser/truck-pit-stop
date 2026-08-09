import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { BoardTruck, VehicleMergePreview, VehicleMergeSummary } from '../types'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: {
    get: apiMocks.get,
    post: apiMocks.post,
  },
}))

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

import { MergeTruckModal } from '../TruckDetail'

const openedTruck: BoardTruck = {
  id: 'opened-truck',
  unit_number: '101',
  display_unit_number: '77 CARGO LLC 101',
  year: 2020,
  make: 'Hino',
  model: '268',
  vin: 'JHHRDM2H4LK001234',
  plate: 'ABC123',
  status: 'yard',
  odometer: 222_563,
  pm_interval_miles: 25_000,
  moving: false,
  open_work_order_count: 0,
  open_incident_count: 0,
}

const openedSummary: VehicleMergeSummary = {
  id: openedTruck.id,
  customer_id: 'customer-77',
  customer_name: '77 CARGO LLC',
  vin: openedTruck.vin!,
  unit_number: openedTruck.unit_number,
  make: openedTruck.make,
  model: openedTruck.model,
  year: openedTruck.year,
  license_plate: openedTruck.plate,
  mileage: openedTruck.odometer,
  source: 'dieselbridge',
  repair_order_count: 4,
  appointment_count: 1,
  inspection_count: 1,
  incident_count: 0,
}

const candidateSummary: VehicleMergeSummary = {
  id: 'candidate-truck',
  customer_id: 'customer-77',
  customer_name: '77 CARGO LLC',
  vin: openedTruck.vin!,
  unit_number: '101',
  make: 'Hino',
  model: '268',
  year: 2020,
  license_plate: null,
  mileage: 200_000,
  source: 'easy_truck_shop_import',
  repair_order_count: 2,
  appointment_count: 0,
  inspection_count: 0,
  incident_count: 0,
}

function renderMerge(preview: VehicleMergePreview) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === `/vehicles/${openedTruck.id}/duplicate-candidates`) {
      return Promise.resolve({ data: [candidateSummary] })
    }
    if (url === `/vehicles/${openedTruck.id}/merge-preview/${candidateSummary.id}`) {
      return Promise.resolve({ data: preview })
    }
    return Promise.reject(new Error(`Unexpected GET ${url}`))
  })
  apiMocks.post.mockResolvedValue({
    data: {
      canonical_vehicle: { id: preview.recommended_canonical_id },
      archived_vehicle_id: preview.recommended_canonical_id === openedTruck.id
        ? candidateSummary.id
        : openedTruck.id,
      merge_record_id: 'merge-1',
      moved: { repair_orders: 2, inspections: 0, incidents: 0, appointments: 0 },
    },
  })

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  const onClose = vi.fn()
  const onMerged = vi.fn()

  render(
    <QueryClientProvider client={queryClient}>
      <MergeTruckModal truck={openedTruck} onClose={onClose} onMerged={onMerged} />
    </QueryClientProvider>,
  )

  return { onClose, onMerged }
}

async function reviewAndConfirm(user: ReturnType<typeof userEvent.setup>, expectedKeepUnit: string) {
  const reviewButton = await screen.findByRole('button', { name: /review merge/i })
  await waitFor(() => expect(reviewButton).toBeEnabled())
  await user.click(reviewButton)

  const mergeButton = screen.getByRole('button', { name: `Merge into Unit ${expectedKeepUnit}` })
  expect(mergeButton).toBeDisabled()

  const confirmation = screen.getByRole('checkbox', { name: /i verified/i })
  expect(confirmation).toHaveAttribute('aria-checked', 'false')
  await user.click(confirmation)
  expect(confirmation).toHaveAttribute('aria-checked', 'true')
  expect(mergeButton).toBeEnabled()

  return mergeButton
}

describe('MergeTruckModal merge direction', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
  })

  it('keeps the opened truck when it is recommended and archives the selected candidate', async () => {
    const preview: VehicleMergePreview = {
      canonical: openedSummary,
      duplicate: candidateSummary,
      match_basis: 'vin',
      match_value: openedTruck.vin!,
      recommended_canonical_id: openedTruck.id,
      warnings: [],
    }
    const user = userEvent.setup()
    const { onMerged } = renderMerge(preview)

    const mergeButton = await reviewAndConfirm(user, '101')
    await user.click(mergeButton)

    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith(`/vehicles/${openedTruck.id}/merge`, {
        duplicate_vehicle_id: candidateSummary.id,
        confirm_vin: openedTruck.vin,
      })
    })
    expect(onMerged).toHaveBeenCalledWith(openedTruck.id)
  })

  it('keeps the selected candidate when it is recommended and archives the opened truck', async () => {
    const strongerCandidate = { ...candidateSummary, unit_number: 'ETS-101', repair_order_count: 12 }
    const preview: VehicleMergePreview = {
      canonical: openedSummary,
      duplicate: strongerCandidate,
      match_basis: 'unit_number',
      match_value: '101',
      recommended_canonical_id: strongerCandidate.id,
      warnings: ['This cleanup match uses the shared unit number.'],
    }
    const user = userEvent.setup()
    const { onMerged } = renderMerge(preview)

    const mergeButton = await reviewAndConfirm(user, 'ETS-101')
    expect(screen.getByLabelText('Keep Unit ETS-101')).toBeInTheDocument()
    expect(screen.getByLabelText('Archive Unit 101')).toBeInTheDocument()
    await user.click(mergeButton)

    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith(`/vehicles/${strongerCandidate.id}/merge`, {
        duplicate_vehicle_id: openedTruck.id,
        confirm_unit_number: '101',
      })
    })
    expect(onMerged).toHaveBeenCalledWith(strongerCandidate.id)
  })
})
