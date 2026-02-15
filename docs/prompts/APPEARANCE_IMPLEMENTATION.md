# Appearance/Theme System Implementation Prompt

Use this prompt to implement a global appearance settings system in any React + Tailwind CSS project. This provides user-customizable accent colors, font families, and font sizes with localStorage persistence and cross-tab synchronization.

---

## Overview

This system provides:
- **5 Accent Colors**: cyan, indigo, emerald, rose, amber (each with 400/500/600 shades)
- **3+ Font Families**: Project default + 2 alternatives (customizable)
- **4 Font Sizes**: compact (14px), default (16px), comfortable (18px), large (19px)
- **localStorage Caching**: Persists user preferences across sessions
- **Cross-Tab Sync**: Changes in one tab reflect in all open tabs
- **Live Preview UI**: Settings panel with real-time theme preview

---

## Step 1: Load Fonts in index.html

Add font preloading in your `<head>` section. Adjust fonts based on your project needs.

```html
<!-- Fonts: Geist, DM Sans, Plus Jakarta Sans -->
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=Plus+Jakarta+Sans:ital,wght@0,200..800;1,200..800&display=swap" rel="stylesheet" />
<link href="https://cdn.jsdelivr.net/npm/geist@1.3.1/dist/fonts/geist-sans/style.min.css" rel="stylesheet" />
```

**IMPORTANT**: If your project already uses a specific font, keep it as the first/default option.

---

## Step 2: Create ThemeContext.tsx

Create `src/contexts/ThemeContext.tsx`:

```tsx
import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'

// ============ TYPES ============
export type AccentColor = 'cyan' | 'indigo' | 'emerald' | 'rose' | 'amber'
export type FontFamily = 'default' | 'dm-sans' | 'jakarta'  // Customize IDs as needed
export type FontSize = 'compact' | 'default' | 'comfortable' | 'large'

export interface ThemeConfig {
  accent: AccentColor
  fontFamily: FontFamily
  fontSize: FontSize
}

// ============ OPTIONS ============
// IMPORTANT: First option should be your project's ORIGINAL/DEFAULT font
export const ACCENT_OPTIONS: { id: AccentColor; label: string; colors: { 400: string; 500: string; 600: string } }[] = [
  { id: 'cyan', label: 'Cyan', colors: { 400: '#22D3EE', 500: '#06B6D4', 600: '#0891B2' } },
  { id: 'indigo', label: 'Indigo', colors: { 400: '#818CF8', 500: '#6366F1', 600: '#4F46E5' } },
  { id: 'emerald', label: 'Emerald', colors: { 400: '#34D399', 500: '#10B981', 600: '#059669' } },
  { id: 'rose', label: 'Rose', colors: { 400: '#FB7185', 500: '#F43F5E', 600: '#E11D48' } },
  { id: 'amber', label: 'Amber', colors: { 400: '#FBBF24', 500: '#F59E0B', 600: '#D97706' } },
]

// IMPORTANT: First option = project's original font (preserve existing style as default)
export const FONT_FAMILY_OPTIONS: { id: FontFamily; label: string; stack: string }[] = [
  // CUSTOMIZE: Replace 'Your Font' with your project's existing font
  { id: 'default', label: 'System Default', stack: 'ui-sans-serif, system-ui, -apple-system, sans-serif' },
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
// These are used when no cached preference exists
const DEFAULT_THEME: ThemeConfig = {
  accent: 'cyan',           // Change to match your brand color
  fontFamily: 'default',    // First option = original project font
  fontSize: 'default',
}

// ============ STORAGE KEYS (for localStorage caching) ============
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

// ============ HELPER: Load from localStorage with validation ============
function loadFromStorage<T>(key: string, options: { id: T }[], defaultValue: T): T {
  if (typeof window === 'undefined') return defaultValue
  const stored = localStorage.getItem(key)
  // Validate stored value exists in options array
  if (stored && options.some(opt => opt.id === stored)) {
    return stored as T
  }
  return defaultValue
}

// ============ PROVIDER ============
export function ThemeProvider({ children }: { children: ReactNode }) {
  // Initialize state from localStorage cache (or defaults)
  const [accent, setAccentState] = useState<AccentColor>(() => 
    loadFromStorage(STORAGE_KEYS.accent, ACCENT_OPTIONS, DEFAULT_THEME.accent)
  )
  const [fontFamily, setFontFamilyState] = useState<FontFamily>(() => 
    loadFromStorage(STORAGE_KEYS.fontFamily, FONT_FAMILY_OPTIONS, DEFAULT_THEME.fontFamily)
  )
  const [fontSize, setFontSizeState] = useState<FontSize>(() => 
    loadFromStorage(STORAGE_KEYS.fontSize, FONT_SIZE_OPTIONS, DEFAULT_THEME.fontSize)
  )

  // ============ CSS VARIABLE INJECTION ============
  // Inject CSS variables into document root whenever theme changes
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

  // ============ CROSS-TAB SYNCHRONIZATION ============
  // Sync preferences across browser tabs via storage events
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

  // ============ SETTERS (with immediate cache write) ============
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
```

---

## Step 3: Add CSS Variables to index.css

Add these CSS variable defaults to your global CSS file (e.g., `src/index.css`):

```css
/* Theme CSS Custom Properties - defaults set here, overridden by ThemeContext */
:root {
  /* Font settings */
  --theme-font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
  --theme-font-scale: 1;
  
  /* Accent color (default: cyan) - customize to match your brand */
  --accent-400: #22D3EE;
  --accent-500: #06B6D4;
  --accent-600: #0891B2;
}

html, body {
  font-family: var(--theme-font-family);
  font-size: calc(16px * var(--theme-font-scale));
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

---

## Step 4: Add Accent Colors to Tailwind Config

Add accent color palette to `tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Theme accent colors (5 distinct options)
        accent: {
          cyan: {
            400: '#22D3EE',
            500: '#06B6D4',
            600: '#0891B2',
          },
          indigo: {
            400: '#818CF8',
            500: '#6366F1',
            600: '#4F46E5',
          },
          emerald: {
            400: '#34D399',
            500: '#10B981',
            600: '#059669',
          },
          rose: {
            400: '#FB7185',
            500: '#F43F5E',
            600: '#E11D48',
          },
          amber: {
            400: '#FBBF24',
            500: '#F59E0B',
            600: '#D97706',
          },
        },
      }
    },
  },
  plugins: [],
}
```

---

## Step 5: Wrap App with ThemeProvider

In your `App.tsx` or main entry point:

```tsx
import { ThemeProvider } from './contexts/ThemeContext'

function App() {
  return (
    <ThemeProvider>
      {/* Your app routes/content here */}
    </ThemeProvider>
  )
}

export default App
```

---

## Step 6: Create AppearanceSection UI Component

Add this component to your settings page. Uses Tailwind CSS + lucide-react icons.

```tsx
import { useTheme, ACCENT_OPTIONS, FONT_FAMILY_OPTIONS, FONT_SIZE_OPTIONS } from '@/contexts/ThemeContext'
import { Palette, Zap, Type, Settings2, RotateCcw, Check } from 'lucide-react'

// Staggered animation helper
const staggeredReveal = (index: number) => ({
  animationDelay: `${index * 50}ms`,
})

function AppearanceSection() {
  const { 
    accent, setAccent, 
    fontFamily, setFontFamily, 
    fontSize, setFontSize, 
    accentColors, 
    resetToDefaults 
  } = useTheme()

  return (
    <div className="space-y-8">
      {/* Live Preview */}
      <div className="p-6 bg-zinc-900/80 border border-zinc-700/50 rounded-2xl">
        <div className="flex items-center gap-3 text-xs font-bold uppercase tracking-wider text-zinc-500 mb-6">
          <Palette className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Live Preview</span>
          <button
            onClick={resetToDefaults}
            className="ml-auto px-3 py-1.5 text-xs font-medium text-zinc-500 hover:text-zinc-300 border border-zinc-700/50 hover:border-zinc-600 rounded-lg transition-colors flex items-center gap-2"
          >
            <RotateCcw className="w-3 h-3" />
            Reset
          </button>
        </div>

        <div 
          className="p-4 bg-zinc-800/40 border rounded-xl" 
          style={{ borderColor: accentColors[500] + '40' }}
        >
          <div className="flex items-center gap-3 mb-4">
            <div 
              className="w-10 h-10 flex items-center justify-center rounded-xl border"
              style={{ backgroundColor: accentColors[500] + '20', borderColor: accentColors[500] + '60' }}
            >
              <Palette className="w-5 h-5" style={{ color: accentColors[500] }} />
            </div>
            <div>
              <h4 className="font-semibold text-zinc-100">Theme Preview</h4>
              <p className="text-xs text-zinc-500">See how your theme looks</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button 
              className="px-4 py-2.5 text-white text-sm font-semibold rounded-xl border transition-all hover:shadow-lg"
              style={{ backgroundColor: accentColors[500], borderColor: accentColors[400] + '60' }}
            >
              Primary Button
            </button>
            <button 
              className="px-4 py-2.5 text-sm font-semibold rounded-xl border bg-transparent transition-all"
              style={{ borderColor: accentColors[500], color: accentColors[500] }}
            >
              Secondary
            </button>
            <span 
              className="px-3 py-1.5 text-xs font-semibold rounded-full border"
              style={{ backgroundColor: accentColors[500] + '20', color: accentColors[400], borderColor: accentColors[500] + '40' }}
            >
              Badge
            </span>
          </div>
        </div>
      </div>

      {/* Accent Color */}
      <div className="p-6 bg-zinc-900/80 border border-zinc-700/50 rounded-2xl">
        <div className="flex items-center gap-3 text-xs font-bold uppercase tracking-wider text-zinc-500 mb-6">
          <Zap className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Accent Color</span>
        </div>

        <div className="flex flex-wrap gap-4">
          {ACCENT_OPTIONS.map((option, i) => (
            <button
              key={option.id}
              onClick={() => setAccent(option.id)}
              style={staggeredReveal(i)}
              className={`group flex flex-col items-center gap-2 p-3 rounded-xl border transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
                accent === option.id
                  ? 'border-white/50 bg-zinc-800/80'
                  : 'border-zinc-700/50 hover:border-zinc-600 bg-zinc-800/40'
              }`}
            >
              <div
                className={`w-10 h-10 sm:w-12 sm:h-12 flex items-center justify-center rounded-xl border transition-all ${
                  accent === option.id ? 'scale-110' : 'group-hover:scale-105'
                }`}
                style={{ backgroundColor: option.colors[500], borderColor: option.colors[400] + '60' }}
              >
                {accent === option.id && (
                  <Check className="w-5 h-5 text-white drop-shadow-md" />
                )}
              </div>
              <span className={`text-xs font-medium ${
                accent === option.id ? 'text-white' : 'text-zinc-500 group-hover:text-zinc-400'
              }`}>
                {option.label}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Font Family */}
      <div className="p-6 bg-zinc-900/80 border border-zinc-700/50 rounded-2xl">
        <div className="flex items-center gap-3 text-xs font-bold uppercase tracking-wider text-zinc-500 mb-6">
          <Type className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Font Family</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {FONT_FAMILY_OPTIONS.map((option, i) => (
            <button
              key={option.id}
              onClick={() => setFontFamily(option.id)}
              style={{ ...staggeredReveal(i), fontFamily: option.stack }}
              className={`p-4 text-left rounded-xl border transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
                fontFamily === option.id
                  ? 'border-white/50 bg-zinc-800/80'
                  : 'border-zinc-700/50 hover:border-zinc-600 bg-zinc-800/40'
              }`}
            >
              <span className={`block text-sm font-semibold ${fontFamily === option.id ? 'text-white' : 'text-zinc-400'}`}>
                {option.label}
              </span>
              <span className="block text-xs text-zinc-600 mt-1">Aa Bb Cc 123</span>
            </button>
          ))}
        </div>
      </div>

      {/* Font Size */}
      <div className="p-6 bg-zinc-900/80 border border-zinc-700/50 rounded-2xl">
        <div className="flex items-center gap-3 text-xs font-bold uppercase tracking-wider text-zinc-500 mb-6">
          <Settings2 className="w-4 h-4 text-[var(--accent-400)]" />
          <span>Font Size</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {FONT_SIZE_OPTIONS.map((option, i) => (
            <button
              key={option.id}
              onClick={() => setFontSize(option.id)}
              style={staggeredReveal(i)}
              className={`py-3 px-4 text-center rounded-xl border transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
                fontSize === option.id
                  ? 'border-white/50 bg-zinc-800/80'
                  : 'border-zinc-700/50 hover:border-zinc-600 bg-zinc-800/40'
              }`}
            >
              <span className={`block text-sm font-semibold ${fontSize === option.id ? 'text-white' : 'text-zinc-400'}`}>
                {option.label}
              </span>
              <span className="block text-xs text-zinc-600 mt-1">
                {option.previewPx}px
              </span>
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs text-zinc-600">
        All preferences are saved automatically and persist across sessions.
      </p>
    </div>
  )
}

export default AppearanceSection
```

---

## Step 7: Add fadeIn Animation (if not present)

Add to your global CSS if the animation doesn't exist:

```css
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

---

## Using Theme Values in Components

### Via CSS Variables (recommended for most cases)

```tsx
// Buttons
className="bg-[var(--accent-500)] hover:bg-[var(--accent-600)] border-[var(--accent-400)]/50"

// Text
className="text-[var(--accent-400)]"

// Borders
className="border-[var(--accent-500)]"

// Shadows/Glows
className="hover:shadow-[0_0_24px_var(--accent-500)]"
```

### Via useTheme Hook (for dynamic values)

```tsx
import { useTheme } from '@/contexts/ThemeContext'

function MyComponent() {
  const { accentColors, accent, fontFamily, fontSize } = useTheme()
  
  return (
    <div style={{ backgroundColor: accentColors[500] }}>
      Current accent: {accent}
    </div>
  )
}
```

---

## Customization Guide

### Change Default Accent Color

In `ThemeContext.tsx`, modify `DEFAULT_THEME`:

```tsx
const DEFAULT_THEME: ThemeConfig = {
  accent: 'indigo',  // Change from 'cyan' to your brand color
  fontFamily: 'default',
  fontSize: 'default',
}
```

Also update the CSS variable defaults in `index.css` to match.

### Add/Remove Accent Colors

Modify `ACCENT_OPTIONS` array. Each color needs 400/500/600 shades.

### Change Font Options

1. Add font loading in `index.html`
2. Update `FONT_FAMILY_OPTIONS` with new font stack
3. Update `FontFamily` type

**IMPORTANT**: Keep the project's original font as the first option (index 0) to preserve existing style as default.

### Change Font Size Scale

Modify `FONT_SIZE_OPTIONS`. The `scale` multiplies the base 16px.

---

## Caching Behavior Summary

| Action | Behavior |
|--------|----------|
| First visit | Uses `DEFAULT_THEME` values |
| Change setting | Immediately saved to localStorage |
| Page refresh | Loads from localStorage cache |
| Invalid cache value | Falls back to default |
| New tab | Syncs via `storage` event listener |
| Reset button | Clears to `DEFAULT_THEME` and updates cache |

### Storage Keys

- `theme-accent` - Accent color ID
- `theme-font-family` - Font family ID  
- `theme-font-size` - Font size ID

---

## Dependencies

- React 18+
- Tailwind CSS 3+
- lucide-react (for icons, can substitute)

---

## File Checklist

- [ ] `index.html` - Font preloading links
- [ ] `src/contexts/ThemeContext.tsx` - Theme state + CSS variable injection
- [ ] `src/index.css` - CSS variable defaults + global font application
- [ ] `tailwind.config.js` - Accent color palette
- [ ] `src/App.tsx` - ThemeProvider wrapper
- [ ] Settings page - AppearanceSection component
