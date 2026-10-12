import { Link, useLocation } from 'react-router-dom'
import type { Labor } from '@/types'
import { recommendationLink } from './recommendationConversion'

export default function RecommendationSourceLink({ source }: { source: NonNullable<Labor['recommendation_source']> }) {
  const location = useLocation()
  return <div className="flex min-w-0 flex-wrap items-baseline gap-x-1 px-2 pb-1 text-xs text-slate-600">
    <span>From recommendation</span>
    {source.source_order.available ? <Link
      to={recommendationLink(location.pathname, location.search, source.source_order.id, { recommendation: source.recommendation_id })}
      className="inline-flex items-center whitespace-nowrap rounded px-1 py-1 font-medium text-orange-700 underline underline-offset-2"
      aria-label={`Open source recommendation on ${source.source_order.order_number}`}>
      {source.source_order.order_number}
    </Link> : <span>{source.source_order.order_number} (unavailable)</span>}
    <span className="basis-full break-words">{source.description}</span>
  </div>
}
