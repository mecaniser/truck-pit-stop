import type { AccentColor, AppearanceMode, AppearancePreferences } from '../types/presentation'

export type AccentRamp = { 400: string; 500: string; 600: string; foreground: string; swatchForeground: string }

const ACCENTS_BY_MODE: Record<AppearanceMode, Record<AccentColor, AccentRamp>> = {
  // Day shop uses darker fills so white text and focus treatment remain readable on road-white surfaces.
  light: {
    cyan: { 400: '#0e7490', 500: '#0f766e', 600: '#115e59', foreground: '#ffffff', swatchForeground: '#ffffff' },
    indigo: { 400: '#4f46e5', 500: '#4338ca', 600: '#3730a3', foreground: '#ffffff', swatchForeground: '#ffffff' },
    emerald: { 400: '#047857', 500: '#065f46', 600: '#064e3b', foreground: '#ffffff', swatchForeground: '#ffffff' },
    rose: { 400: '#be123c', 500: '#9f1239', 600: '#881337', foreground: '#ffffff', swatchForeground: '#ffffff' },
    amber: { 400: '#b45309', 500: '#92400e', 600: '#78350f', foreground: '#ffffff', swatchForeground: '#ffffff' },
  },
  // Night shop keeps the selection signal brighter against the navy operating field.
  dark: {
    cyan: { 400: '#67e8f9', 500: '#22d3ee', 600: '#0e7490', foreground: '#ffffff', swatchForeground: '#07101d' },
    indigo: { 400: '#c7d2fe', 500: '#a5b4fc', 600: '#4f46e5', foreground: '#ffffff', swatchForeground: '#07101d' },
    emerald: { 400: '#6ee7b7', 500: '#34d399', 600: '#047857', foreground: '#ffffff', swatchForeground: '#07101d' },
    rose: { 400: '#fda4af', 500: '#fb7185', 600: '#be123c', foreground: '#ffffff', swatchForeground: '#07101d' },
    amber: { 400: '#fde68a', 500: '#fbbf24', 600: '#b45309', foreground: '#ffffff', swatchForeground: '#07101d' },
  },
  // High contrast keeps authored accent identity while retaining an opaque, AA-safe action fill.
  high_contrast: {
    cyan: { 400: '#a5f3fc', 500: '#22d3ee', 600: '#0e7490', foreground: '#ffffff', swatchForeground: '#000000' },
    indigo: { 400: '#e0e7ff', 500: '#a5b4fc', 600: '#4338ca', foreground: '#ffffff', swatchForeground: '#000000' },
    emerald: { 400: '#a7f3d0', 500: '#34d399', 600: '#047857', foreground: '#ffffff', swatchForeground: '#000000' },
    rose: { 400: '#fecdd3', 500: '#fb7185', 600: '#be123c', foreground: '#ffffff', swatchForeground: '#000000' },
    amber: { 400: '#fef3c7', 500: '#fbbf24', 600: '#92400e', foreground: '#ffffff', swatchForeground: '#000000' },
  },
} as const

export function accentRampFor(accent: AccentColor, mode: AppearanceMode): AccentRamp {
  return ACCENTS_BY_MODE[mode][accent]
}

export function accentRampsFor(mode: AppearanceMode) {
  return ACCENTS_BY_MODE[mode]
}

const FONTS = {
  geist: "'Geist', ui-sans-serif, system-ui, sans-serif",
  'dm-sans': "'DM Sans', ui-sans-serif, sans-serif",
  jakarta: "'Plus Jakarta Sans', ui-sans-serif, sans-serif",
  inter: "'Inter', ui-sans-serif, system-ui, sans-serif",
} as const

export function appearanceTokenRecord(value: AppearancePreferences) {
  const accent = accentRampFor(value.accent, value.mode)
  const font = FONTS[value.font_family]
  return {
    '--personal-accent-400': accent[400],
    '--personal-accent-500': accent[500],
    '--personal-accent-600': accent[600],
    '--personal-accent-foreground': accent.foreground,
    '--font-body': font,
    '--font-display': font,
    '--font-size-body': value.font_size === 'small' ? '14px' : value.font_size === 'large' ? '18px' : '16px',
    '--density-row-min': value.density === 'compact' ? '48px' : value.density === 'comfortable' ? '56px' : value.density === 'large' ? '64px' : '52px',
    '--density-control-min': value.density === 'large' ? '48px' : '44px',
  } as const
}
