import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '@/contexts/ThemeContext'
import ActivityChart from '../ActivityChart'
import { activityBuckets, defaultActivityInterval, loadTripRange } from '../tripAggregation'
import { tripPreset } from '../tripFilters'
import type { FleetTrip, FleetTripsResponse } from '../FleetTrips'
const trips = [
  { id: '1', vehicle_id: 'a', started_at: '2026-09-01T14:00:00Z', distance_miles: 100, driving_seconds: 3600 },
  { id: '2', vehicle_id: 'a', started_at: '2026-09-07T14:00:00Z', distance_miles: 200, driving_seconds: 7200 },
] as FleetTrip[]
const data = { items: trips, start_date: '2026-09-01', end_date: '2026-09-30' } as FleetTripsResponse

describe('calendar activity', () => {
  it('clips Monday weeks to the selection and conserves totals with missing buckets', () => {
    const buckets = activityBuckets(trips, 'America/New_York', data.start_date, data.end_date, 'week')
    expect(buckets.map(b => [b.start, b.end])).toEqual([['2026-09-01','2026-09-06'],['2026-09-07','2026-09-13'],['2026-09-14','2026-09-20'],['2026-09-21','2026-09-27'],['2026-09-28','2026-09-30']])
    expect(buckets.map(b => b.miles)).toEqual([100, 200, 0, 0, 0])
    expect(buckets.reduce((sum, b) => sum + b.seconds, 0)).toBe(10800)
    expect(buckets[2].count).toBe(0)
  })
  it('uses local departure dates across year and leap-month boundaries', () => {
    const items = [{ ...trips[0], started_at:'2027-01-01T02:00:00Z' }]
    expect(activityBuckets(items, 'America/New_York','2026-12-31','2027-01-02','year').map(b=>b.count)).toEqual([1,0])
    expect(activityBuckets([], 'UTC','2028-02-01','2028-03-01','month').map(b=>b.end)).toEqual(['2028-02-29','2028-03-01'])
    expect(defaultActivityInterval('2026-10-01','2026-10-04','month')).toBe('week')
    expect(defaultActivityInterval('2026-01-01','2026-01-04','year')).toBe('month')
    expect(tripPreset('year',new Date(2026,9,4))).toEqual({start:'2026-01-01',end:'2026-10-04'})
  })
  it('loads disjoint API windows and counts each truck only once', async () => {
    const fetch = vi.fn(async (start:string,end:string,offset:number) => ({items:[{...trips[0],id:start,started_at:`${start}T14:00:00Z`}],total:1,offset, start_date:start,end_date:end,summary:{trip_count:1,truck_count:1,distance_miles:100,driving_seconds:3600,coverage:'partial'}} as FleetTripsResponse))
    const result = await loadTripRange('2026-01-01','2026-03-01',fetch)
    expect(fetch.mock.calls).toEqual([['2026-01-01','2026-01-31',0],['2026-02-01','2026-03-01',0]])
    expect(result.summary).toMatchObject({truck_count:1,trip_count:2,distance_miles:200,driving_seconds:7200})
    fetch.mockRejectedValueOnce(new Error('failed window'))
    await expect(loadTripRange('2026-01-01','2026-03-01',fetch)).rejects.toThrow('failed window')
    await expect(loadTripRange('2025-01-01','2026-03-01',fetch)).rejects.toThrow('Invalid trip range')
  })
  it('trims leading empty periods but keeps zero-mile trips and internal gaps', async () => {
    const user = userEvent.setup()
    const items = [{ ...trips[0], distance_miles: 0 }, { ...trips[1], started_at: '2026-11-07T14:00:00Z' }]
    render(<ThemeProvider><ActivityChart data={{ ...data, items, start_date: '2026-01-01', end_date: '2026-11-30' }} timezone="UTC" metric="miles" selected={false} preset="year" onOpen={vi.fn()} /></ThemeProvider>)
    expect(document.querySelectorAll('.otr-period-chart > button')).toHaveLength(3)
    expect(screen.getByRole('button', { name: /Sep 1 – Sep 30: 0 miles/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Oct: No imported trips' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Nov 1 – Nov 30: 200 miles/ })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Activity grouping' }))
    await user.click(screen.getByRole('option', { name: 'By week' }))
    expect(document.querySelector('.otr-period-chart > button')).toHaveAccessibleName(/Aug 31 – Sep 6: 0 miles/)
    await user.click(screen.getByRole('button', { name: 'Line', exact: true }))
    expect(document.querySelector('.otr-trend path')?.getAttribute('d')).not.toContain('L')
  })
  it('shows an empty state instead of an empty calendar', () => {
    render(<ThemeProvider><ActivityChart data={{ ...data, items: [] }} timezone="UTC" metric="miles" selected={false} onOpen={vi.fn()} /></ThemeProvider>)
    expect(screen.getByText('No imported trips in this period')).toBeVisible()
    expect(document.querySelectorAll('.otr-period-chart > button')).toHaveLength(0)
  })
  it('switches grouping and chart style independently and drills into the entire bucket', async () => {
    const onOpen = vi.fn(); const user = userEvent.setup()
    render(<ThemeProvider><ActivityChart data={data} timezone="UTC" metric="miles" selected={false} preset="month" onOpen={onOpen} /></ThemeProvider>)
    expect(screen.getByRole('button',{name:'Activity grouping'})).toHaveTextContent('By week')
    const bucket = screen.getByRole('button',{name:'Sep 1 – Sep 6: 100 miles, 1.0h driving. Compare trucks'})
    await user.click(screen.getByRole('button',{name:'Line',exact:true}))
    expect(screen.getByRole('button',{name:'Line',exact:true})).toHaveAttribute('aria-pressed','true')
    await user.click(bucket)
    expect(onOpen).toHaveBeenCalledWith('2026-09-01','2026-09-06',bucket)
    await user.click(screen.getByRole('button',{name:'Activity grouping'}))
    await user.click(screen.getByRole('option',{name:'By month'}))
    expect(screen.getByRole('button',{name:'Sep 1 – Sep 30: 300 miles, 3.0h driving. Compare trucks'})).toBeVisible()
    expect(screen.getByRole('button',{name:'Line',exact:true})).toHaveAttribute('aria-pressed','true')
  })
})
