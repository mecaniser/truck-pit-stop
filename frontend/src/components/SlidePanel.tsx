import { ReactNode, useEffect, useLayoutEffect, useRef } from 'react'
import { ArrowLeft, ChevronLeft, ChevronRight, X } from 'lucide-react'

type HeaderVariant = 'amber' | 'slate' | 'blue' | 'green' | 'minimal' | 'dark'

const headerGradients: Record<Exclude<HeaderVariant, 'minimal' | 'dark'>, string> = {
  amber: 'from-amber-500 to-amber-600',
  slate: 'from-slate-700 to-slate-800',
  blue: 'from-blue-500 to-blue-600',
  green: 'from-green-500 to-green-600',
}

// iPadOS reports itself as macOS when a keyboard or trackpad is attached, so
// the touch-point check is required in addition to the legacy iPad user agent.
function isIPadOS() {
  return /iPad/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
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
  const pointerGesture = useRef<{
    pointerId: number
    startX: number
    startY: number
    startedAt: number
    axis: 'horizontal' | 'vertical' | null
  } | null>(null)
  const suppressNextClick = useRef(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const swipeFrame = useRef<number | null>(null)
  const pendingSwipeOffset = useRef(0)
  const openAnimation = useRef<Animation | null>(null)

  const canSwipe = onPrev !== undefined || onNext !== undefined

  const paintSwipe = (offset: number) => {
    pendingSwipeOffset.current = offset
    if (swipeFrame.current !== null) return
    swipeFrame.current = window.requestAnimationFrame(() => {
      swipeFrame.current = null
      const panel = panelRef.current
      if (!panel) return
      // A still-running open animation composites over inline styles and would
      // swallow the drag.
      openAnimation.current?.cancel()
      const nextOffset = pendingSwipeOffset.current
      panel.style.transition = 'none'
      panel.style.transform = `translate3d(${nextOffset}px, 0, 0)`
      panel.style.opacity = String(Math.max(0.82, 1 - Math.abs(nextOffset) / 600))
    })
  }

  const resetSwipe = () => {
    pointerGesture.current = null
    if (swipeFrame.current !== null) {
      window.cancelAnimationFrame(swipeFrame.current)
      swipeFrame.current = null
    }
    pendingSwipeOffset.current = 0
    const panel = panelRef.current
    if (!panel) return
    panel.style.transition = 'transform 150ms ease-out, opacity 150ms ease-out'
    panel.style.transform = ''
    panel.style.opacity = ''
  }

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!canSwipe || !['touch', 'pen'].includes(event.pointerType) || !event.isPrimary) return
    const target = event.target as HTMLElement
    if (target.closest('input, textarea, select, [contenteditable="true"], [data-no-swipe]')) {
      pointerGesture.current = null
      return
    }
    pointerGesture.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startedAt: performance.now(),
      axis: null,
    }
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch {
      // Some older WebKit builds do not expose pointer capture consistently.
    }
  }

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const gesture = pointerGesture.current
    if (!gesture || gesture.pointerId !== event.pointerId) return

    const deltaX = event.clientX - gesture.startX
    const deltaY = event.clientY - gesture.startY
    if (gesture.axis === null && Math.max(Math.abs(deltaX), Math.abs(deltaY)) >= 8) {
      gesture.axis = Math.abs(deltaX) > Math.abs(deltaY) * 1.1 ? 'horizontal' : 'vertical'
    }
    if (gesture.axis !== 'horizontal') return

    event.preventDefault()
    const canMoveInDirection = deltaX < 0 ? onNext && !nextDisabled : onPrev && !prevDisabled
    const resistedOffset = canMoveInDirection ? deltaX : deltaX * 0.18
    paintSwipe(Math.max(-120, Math.min(120, resistedOffset)))
  }

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const gesture = pointerGesture.current
    if (!gesture || gesture.pointerId !== event.pointerId) return

    const deltaX = event.clientX - gesture.startX
    const deltaY = event.clientY - gesture.startY
    const elapsedMs = Math.max(performance.now() - gesture.startedAt, 1)
    const velocityX = Math.abs(deltaX) / elapsedMs
    const isHorizontalSwipe =
      gesture.axis === 'horizontal' &&
      Math.abs(deltaX) > Math.abs(deltaY) * 1.1 &&
      (Math.abs(deltaX) >= 52 || (Math.abs(deltaX) >= 28 && velocityX >= 0.35))

    try {
      event.currentTarget.releasePointerCapture(event.pointerId)
    } catch {
      // Pointer capture may already have been released by the browser.
    }

    if (isHorizontalSwipe) {
      if (deltaX < 0 && onNext && !nextDisabled) {
        suppressNextClick.current = true
        window.setTimeout(() => { suppressNextClick.current = false }, 400)
        onNext()
      } else if (deltaX > 0 && onPrev && !prevDisabled) {
        suppressNextClick.current = true
        window.setTimeout(() => { suppressNextClick.current = false }, 400)
        onPrev()
      }
    }
    resetSwipe()
  }

  const handleClickCapture = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!suppressNextClick.current) return
    suppressNextClick.current = false
    event.preventDefault()
    event.stopPropagation()
  }

  const handlePointerCancel = () => {
    resetSwipe()
  }

  useEffect(() => () => {
    if (swipeFrame.current !== null) {
      window.cancelAnimationFrame(swipeFrame.current)
    }
  }, [])

  // A drawer that traps neither focus nor Escape is a drawer only a mouse can
  // use: focus stayed on the page behind it, and every background control
  // remained tabbable underneath.
  useEffect(() => {
    if (!isOpen) return
    const panel = panelRef.current
    const restoreFocusTo = document.activeElement as HTMLElement | null

    const focusables = () => Array.from(
      panel?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      ) || []
    ).filter((el) => el.offsetParent !== null)

    // Move focus in without stealing the caret from an autofocused field.
    const first = focusables()[0]
    if (panel && !panel.contains(document.activeElement)) (first || panel).focus?.()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !panel) return
      const items = focusables()
      if (!items.length) return
      const firstItem = items[0]
      const lastItem = items[items.length - 1]
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault()
        lastItem.focus()
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault()
        firstItem.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      restoreFocusTo?.focus?.()
    }
  }, [isOpen, onClose])

  // Layout effect, not effect: pinning the body relayouts the page and drops
  // the scrollbar. Run after paint and that lands one frame into the panel's
  // slide-in, whose translateX(100%) is re-resolved against the element's own
  // width every frame — so the animation's origin moves mid-flight and the
  // panel travels sideways before snapping home. Settle the layout first.
  useLayoutEffect(() => {
    if (!isOpen) return

    const body = document.body
    const root = document.documentElement
    const scrollY = window.scrollY
    const previousBodyStyles = {
      position: body.style.position,
      top: body.style.top,
      left: body.style.left,
      right: body.style.right,
      width: body.style.width,
      overflow: body.style.overflow,
    }
    const previousRootOverflow = root.style.overflow

    // `overflow: hidden` alone is not reliable on iOS/iPadOS. Fixing the body
    // preserves the current page position while preventing the exposed drawer
    // backdrop from dragging the dashboard behind it.
    body.style.position = 'fixed'
    body.style.top = `-${scrollY}px`
    body.style.left = '0'
    body.style.right = '0'
    body.style.width = '100%'
    body.style.overflow = 'hidden'
    root.style.overflow = 'hidden'

    return () => {
      body.style.position = previousBodyStyles.position
      body.style.top = previousBodyStyles.top
      body.style.left = previousBodyStyles.left
      body.style.right = previousBodyStyles.right
      body.style.width = previousBodyStyles.width
      body.style.overflow = previousBodyStyles.overflow
      root.style.overflow = previousRootOverflow
      window.scrollTo(0, scrollY)
    }
  }, [isOpen])

  // The slide-in used to be a CSS animation from translateX(100%). A percentage
  // transform re-resolves against the element's own width on every frame, so any
  // relayout while it runs moves the animation's origin and the panel travels
  // sideways before snapping home. The pin above removes one cause of that
  // relayout, but not all of them: an iPad reports no scrollbar to drop, and the
  // fleet board never scrolls the document at all, so pinning changes nothing
  // there and the travel survives.
  //
  // Measure the distance once, after the pin has settled the layout, and animate
  // in pixels — a length with nothing left to re-resolve against, whatever the
  // viewport does mid-flight.
  //
  // This effect must stay below the pin: React runs layout effects in order, and
  // measuring first would capture the pre-pin width.
  useLayoutEffect(() => {
    if (!isOpen) return
    const panel = panelRef.current
    if (!panel || typeof panel.animate !== 'function') return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    // WebKit can still jitter a fixed, backdrop-blurred panel while it is
    // compositing a horizontal Web Animations API transform. The Sidekick is
    // used repeatedly on a fleet manager's iPad, where a stable immediate open
    // is better than a spatial cue that can visibly fail. Keep the slide for
    // desktop browsers, whose compositor handles this animation reliably.
    if (isIPadOS()) return

    const distance = panel.getBoundingClientRect().width
    if (!distance) return

    const animation = panel.animate(
      [
        { transform: `translate3d(${distance}px, 0, 0)` },
        { transform: 'translate3d(0, 0, 0)' },
      ],
      { duration: 300, easing: 'ease-out', fill: 'backwards' }
    )
    openAnimation.current = animation

    return () => {
      animation.cancel()
      openAnimation.current = null
    }
  }, [isOpen])

  if (!isOpen) return null

  const isMinimal = headerVariant === 'minimal'
  const isDark = headerVariant === 'dark' || dark

  // Dark theme panel
  if (isDark) {
    return (
      <div className="fixed inset-0 z-[60] overflow-hidden overscroll-none">
        {/* Backdrop */}
        <div
          className="absolute inset-0 touch-none overscroll-none bg-black/60 backdrop-blur-sm transition-opacity"
          onClick={onClose}
        />

        {/* Panel */}
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-label={title}
          tabIndex={-1}
          className={`absolute inset-y-0 right-0 w-full ${width} bg-zinc-900 shadow-2xl flex flex-col border-l border-zinc-700/50 touch-pan-y`}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
          onClickCapture={handleClickCapture}
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
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain scrollbar-dark">{children}</div>

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
    <div className="fixed inset-0 z-[60] overflow-hidden overscroll-none">
      {/* Backdrop */}
      <div
        className="absolute inset-0 touch-none overscroll-none bg-black/40 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={`absolute inset-y-0 right-0 w-full ${width} bg-white shadow-2xl flex flex-col touch-pan-y`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onClickCapture={handleClickCapture}
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
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{children}</div>

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
