import { Info } from 'lucide-react'
import { useId } from 'react'

interface SectionInfoTooltipProps {
  text: string
  className?: string
  tooltipClassName?: string
}

export default function SectionInfoTooltip({ text, className = '', tooltipClassName = '' }: SectionInfoTooltipProps) {
  const tooltipId = useId()

  return (
    <span className={`relative inline-flex items-center group ${className}`}>
      <button
        type="button"
        aria-describedby={tooltipId}
        aria-label="Section info"
        title={text}
        className="inline-flex items-center justify-center w-4 h-4 rounded-full text-gray-400 hover:text-gray-200 cursor-help focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      <span
        id={tooltipId}
        role="tooltip"
        className={`pointer-events-none absolute left-1/2 top-[calc(100%+6px)] z-20 hidden w-64 -translate-x-1/2 rounded-md border border-white/10 bg-gray-900 px-2.5 py-2 text-[11px] text-gray-200 shadow-lg group-hover:block group-focus-within:block group-active:block ${tooltipClassName}`}
      >
        {text}
      </span>
    </span>
  )
}
