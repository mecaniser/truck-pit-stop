import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes } from 'react'
import './controls.css'

/** Geometry only: existing surface classes continue to own color and emphasis.
 * Content buttons (records, tiles, navigation and disclosures) keep their layout.
 * Native button defaults, form attributes, event handlers and refs are preserved.
 */
export type ControlButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  controlKind?: 'action' | 'icon' | 'content'
}
export const ControlButton = forwardRef<HTMLButtonElement, ControlButtonProps>(
  function ControlButton({ controlKind = 'action', ...props }, ref) {
    return <button {...props} ref={ref} data-db-control={controlKind} />
  },
)

/** Text-like fields share the same sizing as actions and select triggers.
 * Compound fields retain their horizontal padding for icons, units and steppers.
 */
export const ControlInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function ControlInput(props, ref) {
    return <input {...props} ref={ref} data-db-control="field" />
  },
)

/** Wrapping command group; callers retain alignment and accessible naming. */
export function ControlGroup({ className = '', ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={`db-control-group ${className}`} />
}
