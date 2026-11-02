import { create } from 'zustand'

// Waiting feedback only: never retry or queue requests here.
export const useRequestActivity = create<{ slow: number }>(() => ({ slow: 0 }))
const pending = new WeakMap<object, { timer: ReturnType<typeof setTimeout>; slow: boolean }>()
export function startRequest(config: object) {
  finishRequest(config)
  const entry = { slow: false, timer: setTimeout(() => {
    entry.slow = true
    useRequestActivity.setState(s => ({ slow: s.slow + 1 }))
  }, 8000) }
  pending.set(config, entry)
}
export function finishRequest(config?: object) {
  if (!config) return
  const entry = pending.get(config)
  if (!entry) return
  clearTimeout(entry.timer)
  pending.delete(config)
  if (entry.slow) useRequestActivity.setState(s => ({ slow: Math.max(0, s.slow - 1) }))
}
