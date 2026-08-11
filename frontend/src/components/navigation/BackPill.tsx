import { ChevronLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

type BackPillProps = {
  destination: 'History' | 'Dashboard'
  fallbackTo?: string
}

export default function BackPill({
  destination,
  fallbackTo = destination === 'History' ? '/portal/repairs' : '/portal',
}: BackPillProps) {
  const navigate = useNavigate()

  return (
    <button
      type="button"
      onClick={() => {
        const routerHistoryIndex = Number(window.history.state?.idx || 0)
        if (routerHistoryIndex > 0) {
          navigate(-1)
          return
        }
        navigate(fallbackTo, { replace: true })
      }}
      className="inline-flex min-h-[44px] items-center gap-1 rounded-full border border-[#272d3d] bg-[#191d2a] px-3.5 text-[13px] font-bold text-[#c9cdd8] hover:border-[#3a4257] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8b7cf7] focus-visible:ring-offset-2 focus-visible:ring-offset-[#10131c]"
      aria-label={`Back to ${destination}`}
    >
      <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      {destination}
    </button>
  )
}
