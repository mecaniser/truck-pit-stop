import { ControlInput, ControlButton } from '@/components/ui/Controls'
import { useId, useRef, useState } from 'react'
import { Pencil } from 'lucide-react'

export type OrderIntakePatch = {
  po_number?: string | null
  mileage_in?: number | null
  mileage_in_carried?: false
  mileage_out?: number | null
}

type Props = {
  mileageIn?: number | null
  mileageOut?: number | null
  mileageInCarried?: boolean
  poNumber?: string | null
  orderTypeLabel?: string
  canEdit: boolean
  onSave?: (patch: OrderIntakePatch) => Promise<void>
}

const inputClass = 'mt-1 block min-h-11 w-full min-w-0 rounded-lg border border-gray-300 bg-white px-2.5 text-base text-gray-900 focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500 sm:min-h-9 sm:text-sm'

export default function OrderIntakeDetails({ mileageIn, mileageOut, mileageInCarried, poNumber, orderTypeLabel, canEdit, onSave }: Props) {
  const [draft, setDraft] = useState<{ po: string; in: string; out: string } | null>(null)
  const baseline = useRef({ po: poNumber ?? null, in: mileageIn ?? null, out: mileageOut ?? null })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const editRef = useRef<HTMLButtonElement>(null)
  const errorId = useId()

  const finish = () => {
    setDraft(null)
    setError('')
    requestAnimationFrame(() => editRef.current?.focus())
  }

  const save = async () => {
    if (!draft || !canEdit || !onSave || savingRef.current) return
    const readings = [draft.in.trim(), draft.out.trim()]
    if (readings.some(value => value !== '' && (!/^\d+$/.test(value) || Number(value) > 2147483647))) {
      setError('Mileage must be a whole number from 0 to 2,147,483,647, or blank.')
      return
    }
    if (draft.po.trim().length > 100) {
      setError('PO number must be 100 characters or fewer.')
      return
    }
    const next = { po: draft.po.trim() || null, in: readings[0] === '' ? null : Number(readings[0]), out: readings[1] === '' ? null : Number(readings[1]) }
    const patch: OrderIntakePatch = {}
    if (next.po !== baseline.current.po) patch.po_number = next.po
    if (next.in !== baseline.current.in) {
      patch.mileage_in = next.in
      patch.mileage_in_carried = false
    }
    if (next.out !== baseline.current.out) patch.mileage_out = next.out
    if (!Object.keys(patch).length) { finish(); return }
    savingRef.current = true
    setSaving(true)
    setError('')
    try {
      await onSave(patch)
      finish()
    } catch {
      setError('Could not save intake. Your changes are still here. Try again.')
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  return <section aria-label="Order intake" className="border-t border-gray-200 pt-3 sm:col-span-2">
    {draft && canEdit ? <form onSubmit={event => { event.preventDefault(); void save() }} className="space-y-3">
      <fieldset disabled={saving} aria-describedby={error ? errorId : undefined} className="grid min-w-0 grid-cols-2 gap-3">
        <label className="col-span-2 text-xs font-medium text-gray-600">PO number
          <ControlInput autoFocus className={inputClass} value={draft.po} maxLength={100} onChange={event => setDraft({ ...draft, po: event.target.value })} />
        </label>
        <label className="min-w-0 text-xs font-medium text-gray-600">Mileage in
          <ControlInput className={inputClass} inputMode="numeric" value={draft.in} onChange={event => setDraft({ ...draft, in: event.target.value })} />
        </label>
        <label className="min-w-0 text-xs font-medium text-gray-600">Mileage out
          <ControlInput className={inputClass} inputMode="numeric" value={draft.out} onChange={event => setDraft({ ...draft, out: event.target.value })} />
        </label>
      </fieldset>
      {error && <p id={errorId} role="alert" className="text-sm text-red-700">{error}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        <ControlButton type="button" disabled={saving} onClick={finish} className=" whitespace-nowrap rounded-lg border border-gray-300 px-3 text-sm font-semibold ">Cancel</ControlButton>
        <ControlButton type="submit" disabled={saving} className=" whitespace-nowrap rounded-lg bg-orange-600 px-3 text-sm font-semibold text-white hover:bg-orange-700 disabled:opacity-60 ">{saving ? 'Saving…' : 'Save intake'}</ControlButton>
      </div>
    </form> : <>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div><dt className="text-[11px] uppercase text-gray-400">Mileage In</dt><dd className="font-medium text-gray-800">{mileageIn?.toLocaleString() ?? '—'}</dd>{mileageInCarried && <p className="text-xs text-gray-500">From prior visit</p>}</div>
        <div><dt className="text-[11px] uppercase text-gray-400">Mileage Out</dt><dd className="font-medium text-gray-800">{mileageOut?.toLocaleString() ?? '—'}</dd></div>
        <div className="min-w-0"><dt className="text-[11px] uppercase text-gray-400">PO Number</dt><dd className="break-words font-medium text-gray-800">{poNumber || '—'}</dd></div>
        <div><dt className="text-[11px] uppercase text-gray-400">Type</dt><dd className="font-medium text-gray-800">{orderTypeLabel || 'Standard'}</dd></div>
      </dl>
      {canEdit && onSave && <ControlButton ref={editRef} type="button" onClick={() => {
        baseline.current = { po: poNumber ?? null, in: mileageIn ?? null, out: mileageOut ?? null }
        setDraft({ po: poNumber ?? '', in: mileageIn == null ? '' : String(mileageIn), out: mileageOut == null ? '' : String(mileageOut) })
        setError('')
      }} className="mt-2 inline-flex  items-center gap-1.5 whitespace-nowrap rounded-lg px-2 text-sm font-semibold text-orange-700 hover:bg-orange-50 "><Pencil className="h-3.5 w-3.5" />Edit intake</ControlButton>}
    </>}
  </section>
}
