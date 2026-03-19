import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'

// ============ TYPES ============
export type AccentColor = 'cyan' | 'indigo' | 'emerald' | 'rose' | 'amber'
export type FontFamily = 'geist' | 'dm-sans' | 'jakarta'
export type FontSize = 'compact' | 'default' | 'comfortable' | 'large'

export interface ThemeConfig {
  accent: AccentColor
  fontFamily: FontFamily
  fontSize: FontSize
}

// ============ OPTIONS ============
export const ACCENT_OPTIONS: { id: AccentColor; label: string; colors: { 400: string; 500: string; 600: string } }[] = [
  { id: 'cyan', label: 'Cyan', colors: { 400: '#22D3EE', 500: '#06B6D4', 600: '#0891B2' } },
  { id: 'indigo', label: 'Indigo', colors: { 400: '#818CF8', 500: '#6366F1', 600: '#4F46E5' } },
  { id: 'emerald', label: 'Emerald', colors: { 400: '#34D399', 500: '#10B981', 600: '#059669' } },
  { id: 'rose', label: 'Rose', colors: { 400: '#FB7185', 500: '#F43F5E', 600: '#E11D48' } },
  { id: 'amber', label: 'Amber', colors: { 400: '#FBBF24', 500: '#F59E0B', 600: '#D97706' } },
]

export const FONT_FAMILY_OPTIONS: { id: FontFamily; label: string; stack: string }[] = [
  { id: 'geist', label: 'Geist', stack: "'Geist', ui-sans-serif, system-ui, sans-serif" },
  { id: 'dm-sans', label: 'DM Sans', stack: "'DM Sans', ui-sans-serif, sans-serif" },
  { id: 'jakarta', label: 'Jakarta', stack: "'Plus Jakarta Sans', ui-sans-serif, sans-serif" },
]

export const FONT_SIZE_OPTIONS: { id: FontSize; label: string; scale: number; previewPx: number }[] = [
  { id: 'compact', label: 'Compact', scale: 0.875, previewPx: 14 },
  { id: 'default', label: 'Default', scale: 1, previewPx: 16 },
  { id: 'comfortable', label: 'Comfortable', scale: 1.125, previewPx: 18 },
  { id: 'large', label: 'Large', scale: 1.2, previewPx: 19 },
]

// ============ DEFAULTS ============
const DEFAULT_THEME: ThemeConfig = {
  accent: 'cyan',
  fontFamily: 'geist',
  fontSize: 'default',
}

// ============ STORAGE KEYS ============
const STORAGE_KEYS = {
  accent: 'theme-accent',
  fontFamily: 'theme-font-family',
  fontSize: 'theme-font-size',
}

// ============ CONTEXT ============
interface ThemeContextType {
  // Current values
  accent: AccentColor
  fontFamily: FontFamily
  fontSize: FontSize
  
  // Setters
  setAccent: (color: AccentColor) => void
  setFontFamily: (font: FontFamily) => void
  setFontSize: (size: FontSize) => void
  
  // Helpers
  accentColors: { 400: string; 500: string; 600: string }
  resetToDefaults: () => void
}

const ThemeContext = createContext<ThemeContextType | null>(null)

// ============ HELPER: Load from localStorage ============
function loadFromStorage<T>(key: string, options: { id: T }[], defaultValue: T): T {
  if (typeof window === 'undefined') return defaultValue
  const stored = localStorage.getItem(key)
  if (stored && options.some(opt => opt.id === stored)) {
    return stored as T
  }
  return defaultValue
}

// ============ PROVIDER ============
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [accent, setAccentState] = useState<AccentColor>(() => 
    loadFromStorage(STORAGE_KEYS.accent, ACCENT_OPTIONS, DEFAULT_THEME.accent)
  )
  const [fontFamily, setFontFamilyState] = useState<FontFamily>(() => 
    loadFromStorage(STORAGE_KEYS.fontFamily, FONT_FAMILY_OPTIONS, DEFAULT_THEME.fontFamily)
  )
  const [fontSize, setFontSizeState] = useState<FontSize>(() => {
    const viewportDefault: FontSize =
      typeof window !== 'undefined' && window.innerWidth < 1024 ? 'compact' : 'default'
    return loadFromStorage(STORAGE_KEYS.fontSize, FONT_SIZE_OPTIONS, viewportDefault)
  })

  // Inject CSS variables whenever theme changes
  useEffect(() => {
    const root = document.documentElement
    
    // Accent colors
    const accentOption = ACCENT_OPTIONS.find(opt => opt.id === accent)
    if (accentOption) {
      root.style.setProperty('--accent-400', accentOption.colors[400])
      root.style.setProperty('--accent-500', accentOption.colors[500])
      root.style.setProperty('--accent-600', accentOption.colors[600])
    }
    
    // Font family
    const fontOption = FONT_FAMILY_OPTIONS.find(opt => opt.id === fontFamily)
    if (fontOption) {
      root.style.setProperty('--theme-font-family', fontOption.stack)
    }
    
    // Font size scale
    const sizeOption = FONT_SIZE_OPTIONS.find(opt => opt.id === fontSize)
    if (sizeOption) {
      root.style.setProperty('--theme-font-scale', sizeOption.scale.toString())
    }
  }, [accent, fontFamily, fontSize])

  // Sync across tabs
  useEffect(() => {
    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEYS.accent && e.newValue) {
        if (ACCENT_OPTIONS.some(opt => opt.id === e.newValue)) {
          setAccentState(e.newValue as AccentColor)
        }
      }
      if (e.key === STORAGE_KEYS.fontFamily && e.newValue) {
        if (FONT_FAMILY_OPTIONS.some(opt => opt.id === e.newValue)) {
          setFontFamilyState(e.newValue as FontFamily)
        }
      }
      if (e.key === STORAGE_KEYS.fontSize && e.newValue) {
        if (FONT_SIZE_OPTIONS.some(opt => opt.id === e.newValue)) {
          setFontSizeState(e.newValue as FontSize)
        }
      }
    }
    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  const setAccent = useCallback((color: AccentColor) => {
    setAccentState(color)
    localStorage.setItem(STORAGE_KEYS.accent, color)
  }, [])

  const setFontFamily = useCallback((font: FontFamily) => {
    setFontFamilyState(font)
    localStorage.setItem(STORAGE_KEYS.fontFamily, font)
  }, [])

  const setFontSize = useCallback((size: FontSize) => {
    setFontSizeState(size)
    localStorage.setItem(STORAGE_KEYS.fontSize, size)
  }, [])

  const resetToDefaults = useCallback(() => {
    setAccent(DEFAULT_THEME.accent)
    setFontFamily(DEFAULT_THEME.fontFamily)
    setFontSize(DEFAULT_THEME.fontSize)
  }, [setAccent, setFontFamily, setFontSize])

  const accentColors = ACCENT_OPTIONS.find(opt => opt.id === accent)?.colors || ACCENT_OPTIONS[0].colors

  return (
    <ThemeContext.Provider value={{
      accent,
      fontFamily,
      fontSize,
      setAccent,
      setFontFamily,
      setFontSize,
      accentColors,
      resetToDefaults,
    }}>
      {children}
    </ThemeContext.Provider>
  )
}

// ============ HOOK ============
export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
