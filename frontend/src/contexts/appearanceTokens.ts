import type { AppearancePreferences } from '../types/presentation'

const ACCENTS = {
  cyan: { 400: '#22d3ee', 500: '#06b6d4', 600: '#0891b2' },
  indigo: { 400: '#818cf8', 500: '#6366f1', 600: '#4f46e5' },
  emerald: { 400: '#34d399', 500: '#10b981', 600: '#059669' },
  rose: { 400: '#fb7185', 500: '#f43f5e', 600: '#e11d48' },
  amber: { 400: '#fbbf24', 500: '#f59e0b', 600: '#d97706' },
} as const

const FONTS = {
  geist: "'Geist', ui-sans-serif, system-ui, sans-serif",
  'dm-sans': "'DM Sans', ui-sans-serif, sans-serif",
  jakarta: "'Plus Jakarta Sans', ui-sans-serif, sans-serif",
  inter: "'Inter', ui-sans-serif, system-ui, sans-serif",
} as const

export function appearanceTokenRecord(value: AppearancePreferences) {
  const accent = ACCENTS[value.accent]
  const font = FONTS[value.font_family]
  return {
    '--personal-accent-400': accent[400],
    '--personal-accent-500': accent[500],
    '--personal-accent-600': accent[600],
    '--font-body': font,
    '--font-display': font,
    '--font-size-body': value.font_size === 'small' ? '14px' : value.font_size === 'large' ? '18px' : '16px',
    '--density-row-min': value.density === 'compact' ? '48px' : value.density === 'comfortable' ? '56px' : value.density === 'large' ? '64px' : '52px',
    '--density-control-min': value.density === 'large' ? '48px' : '44px',
  } as const
}
