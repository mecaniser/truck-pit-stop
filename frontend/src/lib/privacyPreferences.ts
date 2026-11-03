import { useSyncExternalStore } from 'react'

export const PRIVACY_KEY = 'dieselbridge.privacy.v1'
const CHANGE_EVENT = 'dieselbridge:privacy'
const MAX_AGE = 180 * 24 * 60 * 60 * 1000
export type PrivacyChoice = 'rejected' | null

export function privacySignal(): boolean {
  return (navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl === true
    || navigator.doNotTrack === '1'
}

export function readPrivacyChoice(): PrivacyChoice {
  if (privacySignal()) return 'rejected'
  try {
    const value = JSON.parse(localStorage.getItem(PRIVACY_KEY) || 'null')
    if (value?.version !== 1 || typeof value.at !== 'number' || value.at > Date.now() || Date.now() - value.at >= MAX_AGE) return null
    return value.choice === 'rejected' ? value.choice : null
  } catch { return null }
}

export function clearAnalyticsCookies() {
  const host = window.location.hostname.split('.')
  for (const cookie of document.cookie.split(';')) {
    const name = cookie.split('=')[0].trim()
    if (name !== '_ga' && !name.startsWith('_ga_') && name !== '_gid' && name !== '_gat') continue
    document.cookie = `${name}=; Max-Age=0; path=/; SameSite=Lax`
    for (let i = 0; i < host.length - 1; i++) {
      document.cookie = `${name}=; Max-Age=0; path=/; domain=.${host.slice(i).join('.')}; SameSite=Lax`
    }
  }
}

export function savePrivacyChoice(choice: Exclude<PrivacyChoice, null>): boolean {
  let persisted = false
  try {
    localStorage.setItem(PRIVACY_KEY, JSON.stringify({ version: 1, choice, at: Date.now() }))
    persisted = true
  } catch { /* Remain denied when browser storage is unavailable. */ }
  if (choice === 'rejected') clearAnalyticsCookies()
  window.dispatchEvent(new Event(CHANGE_EVENT))
  return persisted
}

function subscribe(callback: () => void) {
  window.addEventListener('storage', callback)
  window.addEventListener(CHANGE_EVENT, callback)
  window.addEventListener('focus', callback)
  // Expiry must revoke consent even if the tab stays open.
  const timer = window.setInterval(callback, 60_000)
  return () => {
    window.removeEventListener('storage', callback)
    window.removeEventListener(CHANGE_EVENT, callback)
    window.removeEventListener('focus', callback)
    window.clearInterval(timer)
  }
}
export function usePrivacyChoice() {
  return useSyncExternalStore(subscribe, readPrivacyChoice, () => null)
}
