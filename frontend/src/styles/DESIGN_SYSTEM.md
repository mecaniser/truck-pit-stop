# DieselBridge Network Design System

A hybrid industrial-organic design system combining modern dashboard aesthetics with soft, approachable UI elements.

## Quick Start

```tsx
// Import components
import { 
  Card, Button, Input, Label, Badge, 
  StatusLED, Toggle, Spinner, Header,
  SectionHeader, Stat, Divider, staggeredReveal 
} from '@/components/ui'

// Or import specific components
import { GlassNoirCard, GlassNoirButton } from '@/components/ui/GlassNoirCard'
```

## File Locations

- **Components**: `/src/components/ui/GlassNoirCard.tsx` - Core UI components
- **Mobile Stats**: `/src/components/ui/MobileStats.tsx` - Mobile-optimized stat displays
- **Slide Panel**: `/src/components/SlidePanel.tsx` - Modal/drawer component (supports `dark` prop)
- **Theme Context**: `/src/contexts/ThemeContext.tsx` - Accent colors, fonts
- **Base Styles**: `/src/index.css` - Global CSS, animations

## Design Philosophy

- **Industrial elements**: LED status indicators, glow effects, structured headers
- **Organic softness**: Rounded corners, subtle gradients, gentle shadows
- **Dark theme**: Zinc-based palette with accent color theming
- **Data clarity**: High contrast, clear hierarchy, readable typography

---

## Color Palette

### Base Colors (Zinc)
```
zinc-950: #09090b  - Deepest background
zinc-900: #18181b  - Card backgrounds (with opacity)
zinc-800: #27272a  - Elevated surfaces, inputs
zinc-700: #3f3f46  - Borders (with /50 opacity)
zinc-600: #52525b  - Secondary borders
zinc-500: #71717a  - Muted text, labels
zinc-400: #a1a1aa  - Secondary text
zinc-300: #d4d4d8  - Primary text (light)
zinc-100: #f4f4f5  - Headings, emphasis
```

### Accent Colors (CSS Variables)
```css
--accent-400: Lighter shade (highlights, active states)
--accent-500: Primary accent (buttons, links)
--accent-600: Darker shade (hover states)
```

Available accents: `cyan`, `indigo`, `emerald`, `rose`, `amber`

### Status Colors
```
emerald-400/500: Success, active, connected
amber-400/500:   Warning, pending, incomplete
red-400/500:     Error, danger, disconnected
```

---

## Typography

### Font Families
- **Geist** (default): Modern, excellent for data/numbers
- **DM Sans**: High x-height, great for forms
- **Plus Jakarta Sans**: Friendly geometric

### Font Weights
- `font-medium` (500): Labels, secondary text
- `font-semibold` (600): Buttons, emphasis
- `font-bold` (700): Headings, important values

### Text Sizes
- `text-xs`: Labels, badges, hints
- `text-sm`: Body text, form inputs
- `text-base`: Standard content
- `text-lg`: Subheadings, values
- `text-xl/2xl`: Page titles

---

## Components

### Card
```tsx
className={`
  relative bg-zinc-900/80 backdrop-blur-sm 
  border border-zinc-700/50 rounded-2xl
  overflow-hidden shadow-xl shadow-black/20
`}
```

**Variants:**
- Default: `bg-zinc-900/80`
- Elevated: `bg-zinc-800/60`
- Subtle: `bg-zinc-800/40`

### Input
```tsx
className={`
  w-full px-4 py-3 
  bg-zinc-800/60 border border-zinc-600/50 rounded-xl
  text-zinc-100 text-sm
  placeholder-zinc-500 
  focus:outline-none focus:border-[var(--accent-500)] 
  focus:bg-zinc-800 focus:ring-2 focus:ring-[var(--accent-500)]/20
  transition-all duration-200
  hover:border-zinc-500
`}
```

### Button - Primary
```tsx
className={`
  px-6 py-3 rounded-xl
  bg-[var(--accent-600)] hover:bg-[var(--accent-500)] 
  text-white font-semibold text-sm
  border border-[var(--accent-400)]/50
  transition-all duration-200
  hover:shadow-[0_0_24px_var(--accent-500)]
  active:scale-[0.98]
  disabled:opacity-50 disabled:cursor-not-allowed
`}
```

### Button - Secondary
```tsx
className={`
  px-6 py-3 rounded-xl
  bg-zinc-800/80 hover:bg-zinc-700 
  text-zinc-300 font-semibold text-sm
  border border-zinc-600/50 hover:border-zinc-500
  transition-all duration-200
`}
```

### Button - Danger
```tsx
className={`
  px-6 py-3 rounded-xl
  bg-red-950/80 hover:bg-red-900 
  text-red-400 font-semibold text-sm
  border border-red-800/50 hover:border-red-600
  transition-all duration-200
`}
```

### Badge
```tsx
className={`
  inline-flex items-center gap-2 
  px-3 py-1.5 text-xs font-semibold 
  rounded-full border
`}

// Variants:
default: 'bg-zinc-800/80 text-zinc-300 border-zinc-600/50'
success: 'bg-emerald-950/80 text-emerald-400 border-emerald-700/50'
warning: 'bg-amber-950/80 text-amber-400 border-amber-700/50'
error:   'bg-red-950/80 text-red-400 border-red-700/50'
```

### LED Status Indicator
```tsx
// Active (green glow)
className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.9)] animate-pulse"

// Warning (amber glow)
className="w-2.5 h-2.5 rounded-full bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.9)] animate-pulse"

// Error (red glow)
className="w-2.5 h-2.5 rounded-full bg-red-400 shadow-[0_0_10px_rgba(248,113,113,0.9)]"

// Inactive
className="w-2.5 h-2.5 rounded-full bg-zinc-600"
```

### Toggle Switch
```tsx
<button className={`
  relative w-14 h-8 rounded-full border transition-colors
  ${enabled 
    ? 'bg-[var(--accent-600)] border-[var(--accent-400)]/50' 
    : 'bg-zinc-800 border-zinc-600/50'
  }
`}>
  <span className={`
    absolute top-1 w-5 h-5 bg-white rounded-full 
    transition-transform shadow-md
    ${enabled ? 'left-7' : 'left-1'}
  `} />
</button>
```

### Section Header
```tsx
className={`
  text-xs font-bold uppercase tracking-[0.2em] text-zinc-500
  border-b border-zinc-800/50 pb-2 mb-6
  flex items-center gap-3
`}
```

### Label
```tsx
className="block text-xs font-medium text-zinc-400 mb-2"
```

---

## Spacing & Layout

### Border Radius
- `rounded-full`: Pills, badges, toggles, LEDs
- `rounded-2xl`: Cards, modals, large containers
- `rounded-xl`: Buttons, inputs, smaller cards
- `rounded-lg`: Small elements, file inputs

### Shadows
- Cards: `shadow-xl shadow-black/20`
- Hover glow: `hover:shadow-[0_0_24px_var(--accent-500)]`
- LED glow: `shadow-[0_0_10px_rgba(R,G,B,0.9)]`

### Borders
- Default: `border border-zinc-700/50`
- Active: `border border-[var(--accent-500)]/30`
- Subtle: `border border-zinc-600/50`

---

## Animation

### Staggered Reveal
```tsx
const staggeredReveal = (index: number) => ({
  animationDelay: `${index * 50}ms`,
})

// Usage
style={staggeredReveal(i)}
className="animate-[fadeIn_0.3s_ease-out_forwards] opacity-0"
```

### Keyframes (add to global CSS or inject)
```css
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
```

### Transitions
- Default: `transition-all duration-200`
- Hover scale: `active:scale-[0.98]`
- LED pulse: `animate-pulse`

---

## Patterns

### Form Field
```tsx
<div>
  <label className="block text-xs font-medium text-zinc-400 mb-2">
    Field Label
  </label>
  <input className="w-full px-4 py-3 bg-zinc-800/60 border border-zinc-600/50 rounded-xl text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:border-[var(--accent-500)] focus:ring-2 focus:ring-[var(--accent-500)]/20 transition-all duration-200 hover:border-zinc-500" />
  {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
</div>
```

### Status Card with LED
```tsx
<div className="flex items-start gap-4">
  <div className="p-3 bg-zinc-800/60 border border-zinc-700/50 rounded-xl">
    <StatusLED status="active" />
  </div>
  <div>
    <h4 className="font-semibold text-zinc-100">Status Title</h4>
    <p className="text-sm text-zinc-400 mt-1">Description text</p>
  </div>
</div>
```

### Action Button Group
```tsx
<div className="flex gap-4 pt-4 border-t border-zinc-800/50">
  <button className="px-6 py-3 rounded-xl bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-semibold text-sm border border-zinc-600/50">
    Cancel
  </button>
  <button className="px-6 py-3 rounded-xl bg-[var(--accent-600)] hover:bg-[var(--accent-500)] text-white font-semibold text-sm border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)]">
    Save Changes
  </button>
</div>
```

---

## Responsive Breakpoints

```
sm:  640px   - Mobile landscape
md:  768px   - Tablet
lg:  1024px  - Desktop
xl:  1280px  - Large desktop
2xl: 1536px  - Extra large
```

### Mobile-First Patterns
- Stack on mobile, row on desktop: `flex flex-col sm:flex-row`
- Hide on mobile: `hidden sm:block`
- Adjust padding: `p-4 sm:p-6 lg:p-8`
- Adjust text: `text-sm sm:text-base`

---

## Component Usage Examples

### Basic Card with Content
```tsx
import { Card, SectionHeader, Button } from '@/components/ui'
import { Settings } from 'lucide-react'

<Card className="p-6">
  <SectionHeader icon={<Settings className="w-4 h-4" />}>
    Settings
  </SectionHeader>
  <p className="text-sm text-zinc-400 mb-6">
    Configure your preferences.
  </p>
  <Button>Save Changes</Button>
</Card>
```

### Form with Validation
```tsx
import { Card, Input, Label, Button, Divider } from '@/components/ui'

<Card className="p-6">
  <div className="space-y-4">
    <div>
      <Label>Email Address</Label>
      <Input 
        type="email" 
        placeholder="you@example.com"
        error={!!errors.email}
      />
      {errors.email && (
        <p className="mt-2 text-xs text-red-400">{errors.email}</p>
      )}
    </div>
    <Divider className="my-6" />
    <div className="flex gap-4">
      <Button variant="secondary">Cancel</Button>
      <Button>Submit</Button>
    </div>
  </div>
</Card>
```

### Status Display with LED
```tsx
import { Card, StatusLED, Badge } from '@/components/ui'

<Card className="p-6">
  <div className="flex items-center gap-4">
    <div className="p-3 bg-zinc-800/60 border border-zinc-700/50 rounded-xl">
      <StatusLED status="active" />
    </div>
    <div>
      <h4 className="font-semibold text-zinc-100">System Online</h4>
      <p className="text-sm text-zinc-400">All services operational</p>
    </div>
    <Badge variant="success" className="ml-auto">Connected</Badge>
  </div>
</Card>
```

### Staggered Animation List
```tsx
import { Card, staggeredReveal } from '@/components/ui'

{items.map((item, i) => (
  <Card 
    key={item.id}
    style={staggeredReveal(i)}
    className="p-4 animate-[fadeIn_0.3s_ease-out_forwards] opacity-0"
  >
    {item.name}
  </Card>
))}
```

### Dark Slide Panel
```tsx
import SlidePanel from '@/components/SlidePanel'
import { Settings } from 'lucide-react'

<SlidePanel
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  title="Settings"
  subtitle="Configure options"
  headerIcon={<Settings className="w-5 h-5 text-[var(--accent-400)]" />}
  dark // Enable dark theme
  footer={
    <div className="flex gap-4">
      <Button variant="secondary" onClick={() => setIsOpen(false)}>Cancel</Button>
      <Button onClick={handleSave}>Save</Button>
    </div>
  }
>
  <div className="p-6">
    {/* Panel content */}
  </div>
</SlidePanel>
```

---

## Migration Guide

When updating existing components to use this design system:

1. **Replace hardcoded colors** with zinc palette or CSS variables
2. **Add rounded corners**: `rounded-2xl` for cards, `rounded-xl` for inputs/buttons
3. **Use softer borders**: `border border-zinc-700/50` instead of `border-2`
4. **Add backdrop blur** to floating elements: `backdrop-blur-sm`
5. **Replace uppercase text** in labels with `font-medium`
6. **Add hover glows** to primary actions: `hover:shadow-[0_0_24px_var(--accent-500)]`

### Before/After Examples

```tsx
// Before
<div className="bg-gray-800 border-2 border-gray-600 rounded-lg p-4">

// After  
<div className="bg-zinc-900/80 backdrop-blur-sm border border-zinc-700/50 rounded-2xl p-4">
```

```tsx
// Before
<button className="bg-blue-600 text-white font-bold uppercase px-4 py-2">

// After
<button className="bg-[var(--accent-600)] hover:bg-[var(--accent-500)] text-white font-semibold px-6 py-3 rounded-xl border border-[var(--accent-400)]/50 hover:shadow-[0_0_24px_var(--accent-500)] transition-all">
```
