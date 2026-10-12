import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RecommendationConversionAction from '../RecommendationConversionAction'
import RecommendationSourceLink from '../RecommendationSourceLink'
import { conversionHours, conversionTotal, recommendationErrorMessage, recommendationLink, type RecommendationConversion } from '../recommendationConversion'

const api = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const conversion: RecommendationConversion = {
  id: id(1), recommendation_id: id(2), source_order: { id: id(3), order_number: 'RO-SOURCE', available: true },
  source_description: 'Inspect seal', target_order: { id: id(4), order_number: 'RO-TARGET', status: 'in_progress', available: true },
  labor_id: id(5), state: 'active', created_at: '2026-10-12T12:00:00Z', can_replace: false, can_resolve: false,
}
const receipt = { data: { conversion, replayed: false, warnings: [] } }
function setup(overrides: Partial<React.ComponentProps<typeof RecommendationConversionAction>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const onOpenOperation = vi.fn()
  const view = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/dashboard?queue=on_floor&selected=old']}>
    <RecommendationConversionAction recommendationId={id(2)} description="Inspect seal" contextOrderId={id(4)}
      canConvert hourlyRate={145} onOpenOperation={onOpenOperation} {...overrides} />
  </MemoryRouter></QueryClientProvider>)
  return { ...view, client, onOpenOperation }
}
const open = () => fireEvent.click(screen.getByRole('button', { name: 'Add to this order: Inspect seal' }))
const fill = () => fireEvent.change(screen.getByRole('textbox', { name: 'Hours' }), { target: { value: '1:30' } })
afterEach(() => vi.clearAllMocks())

describe('tracked recommendation conversion', () => {
  it('opens without writing, previews entered duration and sends one exact operation', async () => {
    api.post.mockResolvedValue(receipt)
    const { onOpenOperation, client } = setup()
    client.setQueryData(['recommended-work', 'tenant'], { items: [{ id: id(2) }, { id: id(8) }] })
    open()
    expect(api.post).not.toHaveBeenCalled()
    expect(screen.getByRole('textbox', { name: 'Hours' })).toHaveValue('')
    fill()
    expect(screen.getByText('Labor $217.50')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add operation' }))
    await waitFor(() => expect(onOpenOperation).toHaveBeenCalledWith(id(5)))
    expect(api.post).toHaveBeenCalledWith(`/repair-orders/${id(4)}/recommended-work/${id(2)}/convert`, {
      request_id: expect.any(String), hours: '1.50', hourly_rate: '145.00', replaces_conversion_id: null,
    })
    expect(client.getQueryData(['recommended-work', 'tenant'])).toEqual({ items: [{ id: id(2), conversion }, { id: id(8) }] })
  })

  it('blocks repeat clicks while pending and keeps exact payload and inputs after lost response', async () => {
    let reject!: (error: Error) => void
    api.post.mockImplementationOnce(() => new Promise((_resolve, failure) => { reject = failure }))
    setup(); open(); fill()
    fireEvent.click(screen.getByRole('button', { name: 'Add operation' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Adding…' })).toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'Adding…' }))
    expect(api.post).toHaveBeenCalledTimes(1)
    await act(async () => reject(new Error('lost response')))
    expect(await screen.findByRole('alert')).toHaveTextContent('Retry safely')
    expect(screen.getByRole('textbox', { name: 'Hours' })).toHaveValue('1:30')
    expect(screen.getByRole('textbox', { name: 'Hours' })).toBeDisabled()
    api.post.mockResolvedValue(receipt)
    fireEvent.click(screen.getByRole('button', { name: 'Retry safely' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
    expect(api.post.mock.calls[1]).toEqual(api.post.mock.calls[0])
  })

  it.each(['', '0', '-1', '1:75', 'NaN', '1000', '1.234'])('rejects invalid duration %s without writing', async (hours) => {
    setup(); open()
    fireEvent.change(screen.getByRole('textbox', { name: 'Hours' }), { target: { value: hours } })
    fireEvent.click(screen.getByRole('button', { name: 'Add operation' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Enter 0.01–999.99 hours')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('rejects invalid rates, preserves draft on a known validation failure and permits correcting it', async () => {
    setup(); open(); fill()
    fireEvent.change(screen.getByRole('textbox', { name: 'Rate / hr' }), { target: { value: '-2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add operation' }))
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.change(screen.getByRole('textbox', { name: 'Rate / hr' }), { target: { value: '125' } })
    api.post.mockRejectedValueOnce({ response: { status: 422, data: { detail: 'Price is too large.' } } })
    fireEvent.click(screen.getByRole('button', { name: 'Add operation' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Price is too large.')
    expect(screen.getByRole('textbox', { name: 'Hours' })).toBeEnabled()
    expect(screen.getByRole('textbox', { name: 'Rate / hr' })).toHaveValue('125')
  })

  it('links existing work and never offers another Add', () => {
    const { onOpenOperation } = setup({ conversion })
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'Open linked operation on RO-TARGET' }))
    expect(onOpenOperation).toHaveBeenCalledWith(id(5))
    expect(api.post).not.toHaveBeenCalled()
  })

  it('handles a conflicting concurrent conversion by offering its exact target', async () => {
    api.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'already_converted', message: 'Already added.', conversion } } } })
    setup(); open(); fill()
    fireEvent.click(screen.getByRole('button', { name: 'Add operation' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Already added.')
    expect(screen.getByRole('link', { name: 'Open linked operation on RO-TARGET' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add operation' })).not.toBeInTheDocument()
  })

  it('requires explicit replacement and sends the prior conversion identity', async () => {
    api.post.mockResolvedValue(receipt)
    setup({ conversion: { ...conversion, state: 'operation_removed', can_replace: true } })
    fireEvent.click(screen.getByRole('button', { name: 'Add again: Inspect seal' })); fill()
    expect(api.post).not.toHaveBeenCalled()
    expect(screen.getByText(/previous link stays/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add replacement' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    expect(api.post.mock.calls[0][1].replaces_conversion_id).toBe(id(1))
  })

  it('cancels and restores focus without a write', () => {
    setup(); open(); fill()
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Hours' }), { key: 'Escape' })
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add to this order: Inspect seal' })).toHaveFocus()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('does not offer writes on locked/finalized or missing target context', () => {
    setup({ canConvert: false })
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('does not focus a different workspace after an unmounted submit finishes', async () => {
    let resolve!: (data: typeof receipt) => void
    api.post.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const view = setup(); open(); fill()
    fireEvent.click(screen.getByRole('button', { name: 'Add operation' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    view.unmount()
    await act(async () => resolve(receipt))
    expect(view.onOpenOperation).not.toHaveBeenCalled()
  })

  it('keeps source description and links exact recommendation without losing queue context', () => {
    render(<MemoryRouter initialEntries={['/dashboard?queue=on_floor&customer=old']}>
      <RecommendationSourceLink source={{ conversion_id: id(1), recommendation_id: id(2), source_order: conversion.source_order, description: 'Original seal note', state: 'active' }} />
    </MemoryRouter>)
    expect(screen.getByText('Original seal note')).toBeInTheDocument()
    expect(screen.getByRole('link')).toHaveAttribute('href', `/dashboard?queue=on_floor&selected=${id(3)}&recommendation=${id(2)}`)
  })

  it('formats navigation and duration without ambiguous partial parsing', () => {
    expect(recommendationLink('/dashboard/customers', '?customer=1&operation=old', id(4), { operation: id(5) })).toBe(`/dashboard/repair-orders?selected=${id(4)}&operation=${id(5)}`)
    expect(conversionHours('1:20')).toBe(1.33)
    expect(conversionHours('1.25bad')).toBeNull()
  })

  it('previews the exact canonical half-even labor amount before submitting', () => {
    setup(); open()
    fireEvent.change(screen.getByRole('textbox', { name: 'Hours' }), { target: { value: '0.50' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Rate / hr' }), { target: { value: '145.01' } })
    expect(screen.getByText('Labor $72.50')).toBeInTheDocument()
    expect(conversionTotal(0.5, 145.03)).toBe(72.52)
    expect(conversionTotal(1.33, 145)).toBe(192.85)
  })

  it('explains structured resolution failures and legacy/network errors', () => {
    expect(recommendationErrorMessage({ response: { data: { detail: { code: 'converted_work_not_completed', message: 'Complete the linked work first.' } } } }, 'Retry')).toBe('Complete the linked work first.')
    expect(recommendationErrorMessage({ response: { data: { detail: 'Order locked' } } }, 'Retry')).toBe('Order locked')
    expect(recommendationErrorMessage(new Error('offline'), 'Please retry.')).toBe('Please retry.')
  })
})
