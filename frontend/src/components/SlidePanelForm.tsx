import { FormEvent, ReactNode, useEffect, useRef } from 'react'
import { Spinner } from '@/components/ui'
import { X } from 'lucide-react'
import { useTheme } from '../contexts/ThemeContext'

interface SlidePanelFormProps {
  isOpen: boolean
  onClose: () => void
  /** Category label shown above title (e.g., "Suppliers", "Inventory") */
  category?: string
  title: string
  /** Optional subtitle below title */
  subtitle?: string
  /** Form submit handler. If not provided, children should contain their own form. */
  onSubmit?: (e: FormEvent) => void
  /** Main form content */
  children: ReactNode
  /** Primary action button label */
  submitLabel?: string
  /** Cancel button label */
  cancelLabel?: string
  /** Show loading state on submit button */
  isSubmitting?: boolean
  /** Disable submit button */
  submitDisabled?: boolean
  /** Hide footer (when children handle their own actions) */
  hideFooter?: boolean
  /** Width class, defaults to sm:w-[520px] */
  width?: string
  /** Optional aria-label for accessibility */
  ariaLabel?: string
  /** Optional action rendered in the header, left of the close button (e.g. edit toggle) */
  headerAction?: ReactNode
  /** Optional avatar/thumbnail rendered left of the category/title text */
  titleIcon?: ReactNode
  /** Optional surface hook for a domain-owned panel treatment. */
  panelClassName?: string
}

export default function SlidePanelForm({
  isOpen,
  onClose,
  category,
  title,
  subtitle,
  onSubmit,
  children,
  submitLabel = 'Save',
  cancelLabel = 'Cancel',
  isSubmitting = false,
  submitDisabled = false,
  hideFooter = false,
  width = 'sm:w-[520px]',
  ariaLabel,
  headerAction,
  titleIcon,
  panelClassName,
}: SlidePanelFormProps) {
  const { accentColors } = useTheme()
  const panelRef = useRef<HTMLElement>(null)
  const previouslyFocusedRef = useRef<HTMLElement | null>(null)
  const wasOpenRef = useRef(false)
  const onCloseRef = useRef(onClose)
  const isSubmittingRef = useRef(isSubmitting)
  onCloseRef.current = onClose
  isSubmittingRef.current = isSubmitting
  if (isOpen && !wasOpenRef.current) {
    previouslyFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
  }
  wasOpenRef.current = isOpen

  useEffect(() => {
    if (!isOpen) return
    const panel = panelRef.current
    if (!panel) return
    const previouslyFocused = previouslyFocusedRef.current
    const focusable = () => Array.from(panel.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])')).filter((element) => !element.hidden && element.getAttribute('aria-hidden') !== 'true')
    const focusFrame = window.requestAnimationFrame(() => {
      if (!panel.contains(document.activeElement)) (focusable()[0] || panel).focus()
    })
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape' && !isSubmittingRef.current) {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const controls = focusable()
      if (!controls.length) { event.preventDefault(); panel.focus(); return }
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (event.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      window.cancelAnimationFrame(focusFrame)
      document.removeEventListener('keydown', handleKeyDown)
      window.requestAnimationFrame(() => previouslyFocused?.focus())
    }
  }, [isOpen])

  if (!isOpen) return null

  const header = (
    <div className="db-slide-panel-form__header px-5 py-4 border-b border-gray-200 flex items-center justify-between gap-2">
      <div className="flex items-center gap-3 min-w-0">
        {titleIcon}
        <div className="min-w-0">
          {category && (
            <p className="text-xs uppercase text-gray-500 font-semibold">{category}</p>
          )}
          <p className="text-lg font-semibold text-slate-800">{title}</p>
          {subtitle && (
            <p className="text-sm text-gray-500">{subtitle}</p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {headerAction}
        <button
          type="button"
          onClick={onClose}
          aria-label={`Close ${title}`}
          className="p-2 text-gray-500 hover:text-gray-700 rounded-full hover:bg-gray-100"
        >
          <X className="w-5 h-5" />
        </button>
      </div>
    </div>
  )

  const content = (
    <div className="db-slide-panel-form__content p-5 space-y-4 overflow-y-auto flex-1">
      {children}
    </div>
  )

  const footer = !hideFooter && (
    <div className="db-slide-panel-form__footer px-5 py-4 border-t border-gray-200 flex justify-end gap-2">
      <button
        type="button"
        onClick={onClose}
        className="px-4 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100"
      >
        {cancelLabel}
      </button>
      <button
        type="submit"
        disabled={isSubmitting || submitDisabled}
        className="db-slide-panel-form__submit inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-70"
        style={{ backgroundColor: accentColors[500] }}
      >
        {isSubmitting && <Spinner size="xs" />}
        {submitLabel}
      </button>
    </div>
  )

  return (
    <div className="fixed inset-0 z-[60] overflow-hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 transition-opacity"
        onClick={onClose}
      />

      {/* Panel */}
      <aside
        ref={panelRef}
        tabIndex={-1}
        className={`db-slide-panel-form absolute top-0 right-0 h-full w-full ${width} bg-white/95 backdrop-blur border-l border-gray-200 shadow-xl transform transition-transform animate-slide-in-right ${panelClassName || ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel || title}
      >
        {onSubmit ? (
          <form className="h-full flex flex-col" onSubmit={onSubmit}>
            {header}
            {content}
            {footer}
          </form>
        ) : (
          <div className="h-full flex flex-col">
            {header}
            {content}
            {footer}
          </div>
        )}
      </aside>
    </div>
  )
}
