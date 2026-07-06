import { ReactNode } from 'react'
import { ArrowLeft, ChevronLeft, ChevronRight, X } from 'lucide-react'

type HeaderVariant = 'amber' | 'slate' | 'blue' | 'green' | 'minimal' | 'dark'

const headerGradients: Record<Exclude<HeaderVariant, 'minimal' | 'dark'>, string> = {
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
  /** Header style: gradient colors, 'minimal' for simple white header, or 'dark' for dark theme */
  headerVariant?: HeaderVariant
  /** Avatar/icon element to show in header (gradient variants only) */
  headerIcon?: ReactNode
  /** Extra content in header (e.g., status badge) */
  headerExtra?: ReactNode
  /** Hide the built-in header when a child component owns the full shell. */
  hideHeader?: boolean
  /** Back button config for nested views */
  onBack?: () => void
  backLabel?: string
  /** Main scrollable content */
  children: ReactNode
  /** Footer actions (buttons, etc.) */
  footer?: ReactNode
  /** Width class, defaults to max-w-lg */
  width?: string
  /** Use dark theme for entire panel */
  dark?: boolean
  /** Prev/next navigation for browsing between items */
  onPrev?: () => void
  onNext?: () => void
  prevDisabled?: boolean
  nextDisabled?: boolean
  /** e.g. "3 / 12" shown between prev/next buttons */
  navigationLabel?: string
}

export default function SlidePanel({
  isOpen,
  onClose,
  title,
  subtitle,
  headerVariant = 'amber',
  headerIcon,
  headerExtra,
  hideHeader = false,
  onBack,
  backLabel,
  children,
  footer,
  width = 'max-w-lg',
  dark = false,
  onPrev,
  onNext,
  prevDisabled,
  nextDisabled,
  navigationLabel,
}: SlidePanelProps) {
  if (!isOpen) return null

  const isMinimal = headerVariant === 'minimal'
  const isDark = headerVariant === 'dark' || dark

  // Dark theme panel
  if (isDark) {
    return (
      <div className="fixed inset-0 z-[60] overflow-hidden">
        {/* Backdrop */}
        <div
          className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
          onClick={onClose}
        />

        {/* Panel */}
        <div
          className={`absolute inset-y-0 right-0 w-full ${width} bg-zinc-900 shadow-2xl flex flex-col animate-slide-in-right border-l border-zinc-700/50`}
        >
          {/* Header */}
          {!hideHeader && <div className="px-6 py-5 border-b border-zinc-800/50 flex items-center justify-between bg-zinc-900/95">
            <div className="flex items-center gap-3 min-w-0">
              {onBack && (
                <button
                  onClick={onBack}
                  className="p-2 -ml-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 rounded-xl transition-colors"
                >
                  <ArrowLeft className="w-5 h-5" />
                </button>
              )}
              {headerIcon && (
                <div className="p-2.5 bg-[var(--accent-500)]/10 rounded-xl border border-[var(--accent-500)]/30 flex-shrink-0">
                  {headerIcon}
                </div>
              )}
              <div className="min-w-0">
                {subtitle && <p className="text-xs text-zinc-500 mb-0.5">{subtitle}</p>}
                <h2 className="text-lg font-semibold text-zinc-100 truncate">{title}</h2>
              </div>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              {(onPrev !== undefined || onNext !== undefined) && (
                <div className="flex items-center gap-0.5 mr-1">
                  <button
                    onClick={onPrev}
                    disabled={prevDisabled}
                    className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    aria-label="Previous"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  {navigationLabel && (
                    <span className="text-xs text-zinc-500 tabular-nums px-1 min-w-[3rem] text-center select-none">
                      {navigationLabel}
                    </span>
                  )}
                  <button
                    onClick={onNext}
                    disabled={nextDisabled}
                    className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    aria-label="Next"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              )}
              <button
                onClick={onClose}
                className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 rounded-xl transition-colors"
                aria-label="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>}

          {!hideHeader && headerExtra && (
            <div className="px-6 py-3 border-b border-zinc-800/50 bg-zinc-900/80">
              {headerExtra}
            </div>
          )}

          {/* Content */}
          <div className="min-h-0 flex-1 overflow-y-auto scrollbar-dark">{children}</div>

          {/* Footer */}
          {footer && (
            <div className="border-t border-zinc-800/50 px-6 py-4 bg-zinc-900/95">
              {footer}
            </div>
          )}
        </div>
      </div>
    )
  }

  // Light theme panel (original)
  return (
    <div className="fixed inset-0 z-[60] overflow-hidden">
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
        {!hideHeader && (isMinimal ? (
          <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
            <div>
              {subtitle && <p className="text-xs uppercase text-gray-500 font-semibold">{subtitle}</p>}
              <p className="text-lg font-semibold text-slate-800">{title}</p>
            </div>
            <div className="flex items-center gap-1">
              {(onPrev !== undefined || onNext !== undefined) && (
                <div className="flex items-center gap-0.5 mr-1">
                  <button
                    onClick={onPrev}
                    disabled={prevDisabled}
                    className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    aria-label="Previous"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  {navigationLabel && (
                    <span className="text-xs text-gray-400 tabular-nums px-1 min-w-[3rem] text-center select-none">
                      {navigationLabel}
                    </span>
                  )}
                  <button
                    onClick={onNext}
                    disabled={nextDisabled}
                    className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    aria-label="Next"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              )}
              <button
                onClick={onClose}
                className="p-2 text-gray-500 hover:text-gray-700 rounded-full hover:bg-gray-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>
        ) : (
          <div className={`bg-gradient-to-r ${headerGradients[headerVariant as keyof typeof headerGradients]} px-6 py-8 text-white`}>
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
              <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                {(onPrev !== undefined || onNext !== undefined) && (
                  <div className="flex items-center gap-0.5 mr-1">
                    <button
                      onClick={onPrev}
                      disabled={prevDisabled}
                      className="p-1.5 hover:bg-white/20 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                      aria-label="Previous"
                    >
                      <ChevronLeft className="w-5 h-5" />
                    </button>
                    {navigationLabel && (
                      <span className="text-xs text-white/70 tabular-nums px-1 min-w-[3rem] text-center select-none">
                        {navigationLabel}
                      </span>
                    )}
                    <button
                      onClick={onNext}
                      disabled={nextDisabled}
                      className="p-1.5 hover:bg-white/20 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                      aria-label="Next"
                    >
                      <ChevronRight className="w-5 h-5" />
                    </button>
                  </div>
                )}
                <button
                  onClick={onClose}
                  className="p-2 hover:bg-white/20 rounded-lg transition-colors"
                  aria-label="Close"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>
            </div>
          </div>
        ))}

        {/* Content */}
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>

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
