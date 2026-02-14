import type { SuggestedNextAction } from '@/types'

const ACTION_LABELS: Record<SuggestedNextAction, string> = {
  clock_in: 'Clock in to start the day',
  end_break: 'End break when ready',
  continue_ro: 'Continue the current repair order',
  stop_misc_pick_ro: 'Stop misc and pick up assigned repair order',
  start_assigned_ro: 'Start or resume assigned repair order',
  start_misc: 'Start a misc quick pick task',
  clock_out: 'Core target complete — clock out when ready',
}

const ACTION_BUTTON_LABELS: Record<SuggestedNextAction, string> = {
  clock_in: 'Clock In',
  end_break: 'End Break',
  continue_ro: 'Open Repair Order',
  stop_misc_pick_ro: 'Stop Misc + Open RO',
  start_assigned_ro: 'Open Repair Order',
  start_misc: 'Start Misc Timer',
  clock_out: 'Clock Out',
}

export function formatSuggestedNextAction(action?: string | null): string {
  if (!action) return ACTION_LABELS.start_misc
  const typed = action as SuggestedNextAction
  return ACTION_LABELS[typed] || ACTION_LABELS.start_misc
}

export function getSuggestedActionButtonLabel(action?: string | null): string {
  if (!action) return ACTION_BUTTON_LABELS.start_misc
  const typed = action as SuggestedNextAction
  return ACTION_BUTTON_LABELS[typed] || ACTION_BUTTON_LABELS.start_misc
}
