import { FormEvent, ReactNode } from 'react'
import { X, Loader2 } from 'lucide-react'

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
}: SlidePanelFormProps) {
  if (!isOpen) return null

  const header = (
    <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
      <div>
        {category && (
          <p className="text-xs uppercase text-gray-500 font-semibold">{category}</p>
        )}
        <p className="text-lg font-semibold text-slate-800">{title}</p>
        {subtitle && (
          <p className="text-sm text-gray-500">{subtitle}</p>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        className="p-2 text-gray-500 hover:text-amber-600 rounded-full hover:bg-amber-50"
      >
        <X className="w-5 h-5" />
      </button>
    </div>
  )

  const content = (
    <div className="p-5 space-y-4 overflow-y-auto flex-1">
      {children}
    </div>
  )

  const footer = !hideFooter && (
    <div className="px-5 py-4 border-t border-gray-200 flex justify-end gap-2">
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
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-amber-500 hover:bg-amber-600 disabled:opacity-70"
      >
        {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
        {submitLabel}
      </button>
    </div>
  )

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 transition-opacity"
        onClick={onClose}
      />

      {/* Panel */}
      <aside
        className={`absolute top-0 right-0 h-full w-full ${width} bg-white/95 backdrop-blur border-l border-gray-200 shadow-xl transform transition-transform animate-slide-in-right`}
        role="dialog"
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
