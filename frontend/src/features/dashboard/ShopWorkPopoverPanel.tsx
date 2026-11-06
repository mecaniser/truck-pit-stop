import { PopoverPanel } from '@headlessui/react'
import type { ComponentProps, CSSProperties } from 'react'
import { appearanceTokenRecord, useTheme } from '@/contexts/ThemeContext'
import './shopWorkMotion.css'

/** Portal keeps menus outside scrolling board panels, anchored to their trigger. */
export function ShopWorkPopoverPanel({ className, style, ...props }: ComponentProps<typeof PopoverPanel>) {
  const { appearance } = useTheme()
  return <PopoverPanel {...props} transition anchor="bottom end"
    data-appearance-mode={appearance.mode}
    className={`db-work-motion-panel ${className || ''}`}
    style={{ ...appearanceTokenRecord(appearance), ...style } as CSSProperties} />
}
