import { ReactNode } from 'react'
import { ArrowLeft, X } from 'lucide-react'

type HeaderVariant = 'amber' | 'slate' | 'blue' | 'green' | 'minimal'

const headerGradients: Record<Exclude<HeaderVariant, 'minimal'>, string> = {
  amber: 'from-amber-500 to-amber-600',
  slate: 'from-slate-700 to-slate-800',
  blue: 'from-blue-500 to-blue-600',
  green: 'from-green-500 to-green-600',
}

interface SlidePanelProps {
  isOpen: boolean
  onClose: () => void
  title: string
  subtitle?: string
  /** Header style: gradient colors or 'minimal' for simple white header */
  headerVariant?: HeaderVariant
  /** Avatar/icon element to show in header (gradient variants only) */
  headerIcon?: ReactNode
  /** Extra content in header (e.g., status badge) */
  headerExtra?: ReactNode
  /** Back button config for nested views */
  onBack?: () => void
  backLabel?: string
  /** Main scrollable content */
  children: ReactNode
  /** Footer actions (buttons, etc.) */
  footer?: ReactNode
  /** Width class, defaults to max-w-lg */
  width?: string
}

export default function SlidePanel({
  isOpen,
  onClose,
  title,
  subtitle,
  headerVariant = 'amber',
  headerIcon,
  headerExtra,
  onBack,
  backLabel,
  children,
  footer,
  width = 'max-w-lg',
}: SlidePanelProps) {
  if (!isOpen) return null

  const isMinimal = headerVariant === 'minimal'

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`absolute inset-y-0 right-0 w-full ${width} bg-white shadow-2xl flex flex-col animate-slide-in-right`}
      >
        {/* Header */}
        {isMinimal ? (
          <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
            <div>
              {subtitle && <p className="text-xs uppercase text-gray-500 font-semibold">{subtitle}</p>}
              <p className="text-lg font-semibold text-slate-800">{title}</p>
            </div>
            <button
              onClick={onClose}
              className="p-2 text-gray-500 hover:text-amber-600 rounded-full hover:bg-amber-50"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        ) : (
          <div className={`bg-gradient-to-r ${headerGradients[headerVariant]} px-6 py-8 text-white`}>
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                {onBack && (
                  <button
                    onClick={onBack}
                    className="flex items-center gap-1 text-sm text-white/70 hover:text-white mb-2 transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4" />
                    {backLabel || 'Back'}
                  </button>
                )}
                <div className="flex items-center gap-3">
                  {headerIcon}
                  <div className="min-w-0">
                    {subtitle && !headerIcon && (
                      <p className="text-xs text-white/70 uppercase tracking-wide">{subtitle}</p>
                    )}
                    <h2 className="text-2xl font-bold truncate">{title}</h2>
                    {subtitle && headerIcon && (
                      <p className="text-white/70 text-sm mt-1 truncate">{subtitle}</p>
                    )}
                  </div>
                </div>
                {headerExtra && <div className="mt-4">{headerExtra}</div>}
              </div>
              <button
                onClick={onClose}
                className="p-2 hover:bg-white/20 rounded-lg transition-colors flex-shrink-0 ml-2"
                aria-label="Close"
              >
                <X className="w-6 h-6" />
              </button>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="border-t border-gray-200 px-6 py-4 bg-gray-50">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
