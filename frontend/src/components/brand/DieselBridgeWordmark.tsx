import type { CSSProperties } from 'react'

import './DieselBridgeWordmark.css'

const WORDMARK_LETTERS = Array.from('DieselBridge')
const WORDMARK_DROP_MOTION = [
  { y: '-0.42rem', delay: '520ms' },
  { y: '-0.54rem', delay: '380ms' },
  { y: '-0.34rem', delay: '640ms' },
  { y: '-0.49rem', delay: '460ms' },
  { y: '-0.38rem', delay: '340ms' },
  { y: '-0.55rem', delay: '600ms' },
  { y: '-0.44rem', delay: '420ms' },
  { y: '-0.52rem', delay: '680ms' },
  { y: '-0.32rem', delay: '500ms' },
  { y: '-0.5rem', delay: '360ms' },
  { y: '-0.4rem', delay: '660ms' },
  { y: '-0.47rem', delay: '480ms' },
] as const

export default function DieselBridgeWordmark({
  animated = false,
  showBridge = true,
  className = '',
}: {
  animated?: boolean
  showBridge?: boolean
  className?: string
}) {
  return (
    <span
      className={`db-wordmark${animated ? ' db-wordmark--animated' : ''}${showBridge ? '' : ' db-wordmark--type-only'}${className ? ` ${className}` : ''}`}
      aria-label="Diesel Bridge Network"
    >
      {showBridge && (
        <svg className="db-wordmark__bridge" viewBox="0 0 42 30" aria-hidden="true">
          <path className="db-wordmark__bridge-base" d="M8 22h26" />
          <path className="db-wordmark__bridge-pillars" d="M13 22v-7m8 7V11m8 11v-7" />
          <path className="db-wordmark__bridge-arch" d="M4 22C8 7 34 7 38 22" />
        </svg>
      )}
      <span className="db-wordmark__name">
        <span className="db-wordmark__letters" aria-hidden="true">
          {WORDMARK_LETTERS.map((letter, index) => (
            <span
              key={`${letter}-${index}`}
              className={`db-wordmark__letter${index >= 6 ? ' db-wordmark__letter--bridge' : ''}`}
              style={{
                '--letter-drop-y': WORDMARK_DROP_MOTION[index].y,
                '--letter-drop-delay': WORDMARK_DROP_MOTION[index].delay,
              } as CSSProperties}
            >
              {letter}
            </span>
          ))}
        </span>
      </span>
    </span>
  )
}
