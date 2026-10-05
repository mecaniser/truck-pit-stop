import { useEffect, useState } from 'react'

export const FLEET_HOME_ADDRESS = '416 Seaboard Drive, Matthews, NC 28104'

// Temporary geocoding stays in memory; no cross-tenant or persisted location cache.
export function useFleetHome(address?: string) {
  const token = import.meta.env.VITE_MAPBOX_TOKEN || ''
  const [state, setState] = useState<{ address: string; point?: [number, number]; failed?: boolean }>()
  useEffect(() => {
    if (!address || !token) return
    let cancelled = false
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 15000)
    void fetch(`https://api.mapbox.com/search/geocode/v6/forward?${new URLSearchParams({ q: address, country: 'us', types: 'address', limit: '1', access_token: token })}`, { signal: controller.signal, credentials: 'omit' })
      .then(async response => {
        if (!response.ok) throw new Error('Home lookup unavailable')
        const data = await response.json()
        const point = data.features?.[0]?.geometry?.coordinates
        if (!Array.isArray(point) || point.length !== 2 || !point.every(Number.isFinite) || Math.abs(point[0]) > 180 || Math.abs(point[1]) > 90) throw new Error('Home not found')
        if (!controller.signal.aborted) setState({ address, point: point as [number, number] })
      }).catch(() => { if (!cancelled) setState({ address, failed: true }) })
      .finally(() => clearTimeout(timer))
    return () => { cancelled = true; clearTimeout(timer); controller.abort() }
  }, [address, token])
  return { point: state?.address === address ? state?.point : undefined, failed: !!address && (!token || (state?.address === address && !!state.failed)) }
}
