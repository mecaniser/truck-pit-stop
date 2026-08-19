// Design System Components
// See /src/styles/DESIGN_SYSTEM.md for full documentation

export {
  // Cards
  GlassNoirCard,
  Card,
  
  // Buttons
  GlassNoirButton,
  Button,
  
  // Form Elements
  Input,
  Label,
  Toggle,
  
  // Layout
  SectionHeader,
  GlassNoirHeader,
  Header,
  Divider,
  
  // Data Display
  GlassNoirBadge,
  Badge,
  GlassNoirStat,
  Stat,
  StatusLED,

  // Utilities
  staggeredReveal,
  designStyles,
} from './GlassNoirCard'

// Feedback — the single shared loading indicator (replaces the old
// GlassNoirCard Spinner and the scattered hand-rolled/border/Loader2 spinners).
export { Spinner, LoadingLine, default as SpinnerDefault } from './Spinner'
export type { SpinnerSize, SpinnerProps, LoadingLineProps } from './Spinner'
export { default as StaffSearchField } from './StaffSearchField'
