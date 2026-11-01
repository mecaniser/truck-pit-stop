import { ControlButton } from '@/components/ui/Controls'
import { useEffect, useRef, useState } from 'react'
import api from '@/lib/api'

export interface OriginatingCallOption {
  reference_token: string
  call_id: string
  opportunity_id: string
  started_at: string
  contact_label: string
  service_summary: string
  expires_at: string
}

export default function OriginatingCallPicker({ customerId, value, onChange, disabled = false }: {
  customerId: string
  disabled?: boolean
  value: string | null
  onChange: (reference: string | null) => void
}) {
  const [options, setOptions] = useState<OriginatingCallOption[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [includeOtherCallers, setIncludeOtherCallers] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])

  const load = async (includeOthers = false) => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setIncludeOtherCallers(includeOthers)
    onChange(null)
    setOptions(null)
    setLoading(true)
    setUnavailable(false)
    try {
      const response = await api.post<{ options: OriginatingCallOption[] }>(
        '/repair-orders/originating-call-options', { customer_id: customerId, ...(includeOthers ? { include_other_callers: true } : {}) }, { signal: controller.signal },
      )
      if (!controller.signal.aborted) setOptions(response.data.options)
    } catch {
      if (!controller.signal.aborted) setUnavailable(true)
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  return <div className="space-y-2">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-sm font-medium text-gray-700">Originating call <span className="font-normal text-gray-500">(optional)</span></span>
      <ControlButton type="button" onClick={() => load(includeOtherCallers)} disabled={loading || disabled}
        className=" whitespace-nowrap rounded-lg px-3  text-sm font-semibold text-amber-700 hover:bg-amber-50 disabled:opacity-50">
        {loading ? 'Loading calls…' : options ? 'Refresh calls' : 'Link originating call'}
      </ControlButton>
    </div>
    {unavailable && <p role="status" className="text-sm text-gray-500">Calls are unavailable right now. You can still create this repair order.</p>}
    {options && !unavailable && <fieldset disabled={disabled} className="space-y-2">
      <legend className="sr-only">Choose the call for this repair</legend>
      {options.length === 0 ? <p role="status" className="text-sm text-gray-500">{includeOtherCallers ? 'No available recent calls.' : 'No available calls for this customer.'}</p> : <>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="radio" name="originating-call" checked={!value} onChange={() => onChange(null)} /> Leave unlinked
        </label>
        {options.map(option => <label key={option.reference_token} className="flex items-start gap-3 rounded-lg border border-gray-200 p-3 text-sm text-gray-700">
          <input className="mt-1" type="radio" name="originating-call" checked={value === option.reference_token}
            onChange={() => onChange(option.reference_token)} />
          <span className="min-w-0 break-words"><span className="block font-medium">{option.contact_label}</span>
            <span className="block text-xs text-gray-500">{new Date(option.started_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</span>
            <span className="block">{option.service_summary}</span>
          </span>
        </label>)}
      </>}
    </fieldset>}
    {options && !includeOtherCallers && !unavailable && <div>
      <p className="text-xs text-gray-500">Driver used a different number?</p>
      <ControlButton type="button" disabled={loading || disabled} onClick={() => load(true)}
        className=" whitespace-nowrap rounded-lg px-3  text-sm font-semibold text-amber-700 hover:bg-amber-50 disabled:opacity-50">
        Show other recent calls
      </ControlButton>
    </div>}
  </div>
}
