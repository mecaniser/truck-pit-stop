import { useEffect } from 'react'
import toast from 'react-hot-toast'
import { formatSuggestedNextAction } from '@/lib/mechanicSuggestions'
import type { SuggestedNextAction } from '@/types'
import type { MechanicSuggestion } from '@/hooks/useMechanicSuggestion'

interface SuggestionToastEntry {
  shown_count: number
  last_shown_at_ms: number
}

interface SuggestionToastState {
  last_shown_at_ms: number
  entries: Partial<Record<SuggestedNextAction, SuggestionToastEntry>>
}

const SUGGESTION_TOAST_STORAGE_PREFIX = 'mechanic-next-step-toasts-v1'
const SUGGESTION_TOAST_COOLDOWNS_MS = [
  0,
  90_000,
  4 * 60_000,
  12 * 60_000,
  30 * 60_000,
  90 * 60_000,
  4 * 60 * 60_000,
  12 * 60 * 60_000,
  24 * 60 * 60_000,
]
const SUGGESTION_TOAST_GLOBAL_MIN_GAP_MS = 45_000

function buildMechanicSuggestionToast(suggestion: MechanicSuggestion): string {
  switch (suggestion.action) {
    case 'clock_in':
      return 'Clock in to start your day.'
    case 'end_break':
      return 'You are on break. End break when you are ready.'
    case 'continue_ro':
      return suggestion.recommendedJob
        ? `Continue ${suggestion.recommendedJob.order_number}.`
        : 'Continue your active repair order.'
    case 'stop_misc_pick_ro':
      return suggestion.recommendedJob
        ? `Stop misc timer, then open ${suggestion.recommendedJob.order_number}.`
        : 'Stop misc timer and pick up the next assigned repair order.'
    case 'start_assigned_ro':
      return suggestion.recommendedJob
        ? `Next up: ${suggestion.recommendedJob.order_number}.`
        : 'Start your assigned repair order.'
    case 'start_misc':
      return 'No assigned repair order is ready. Start a quick-pick timer.'
    case 'clock_out':
      return 'Great day! You\'ve hit your goal.'
    default:
      return formatSuggestedNextAction(suggestion.action)
  }
}

function readSuggestionToastState(storageKey: string): SuggestionToastState {
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) {
      return { last_shown_at_ms: 0, entries: {} }
    }
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') {
      return { last_shown_at_ms: 0, entries: {} }
    }
    const entries = (parsed.entries && typeof parsed.entries === 'object') ? parsed.entries : {}
    const lastShown = Number.isFinite(parsed.last_shown_at_ms) ? parsed.last_shown_at_ms : 0
    return {
      last_shown_at_ms: lastShown,
      entries: entries as Partial<Record<SuggestedNextAction, SuggestionToastEntry>>,
    }
  } catch {
    return { last_shown_at_ms: 0, entries: {} }
  }
}

function writeSuggestionToastState(storageKey: string, state: SuggestionToastState): void {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(state))
  } catch {
    // Ignore storage errors; toasts still work for this session.
  }
}

interface UseSuggestionToastsParams {
  userId: string | undefined
  view: string
  isClockedIn: boolean
  suggestion: MechanicSuggestion
}

export function useSuggestionToasts({ userId, view, isClockedIn, suggestion }: UseSuggestionToastsParams): void {
  useEffect(() => {
    if (view !== 'list' || !isClockedIn) return
    const storageKey = `${SUGGESTION_TOAST_STORAGE_PREFIX}:${userId || 'unknown'}`
    const now = Date.now()
    const state = readSuggestionToastState(storageKey)
    const entry = state.entries[suggestion.action]
    const shownCount = entry && Number.isFinite(entry.shown_count) ? entry.shown_count : 0
    const lastShownAt = entry && Number.isFinite(entry.last_shown_at_ms) ? entry.last_shown_at_ms : 0
    const cooldownMs = SUGGESTION_TOAST_COOLDOWNS_MS[Math.min(shownCount, SUGGESTION_TOAST_COOLDOWNS_MS.length - 1)]

    if (now - state.last_shown_at_ms < SUGGESTION_TOAST_GLOBAL_MIN_GAP_MS) return
    if (now - lastShownAt < cooldownMs) return

    toast.dismiss('mechanic-next-step-guidance')
    toast(buildMechanicSuggestionToast(suggestion), {
      id: 'mechanic-next-step-guidance',
      icon: '🧭',
      duration: 3500,
    })

    state.last_shown_at_ms = now
    state.entries[suggestion.action] = {
      shown_count: shownCount + 1,
      last_shown_at_ms: now,
    }
    writeSuggestionToastState(storageKey, state)
  }, [
    view,
    isClockedIn,
    userId,
    suggestion.action,
    suggestion.recommendedJob?.id,
  ])
}
