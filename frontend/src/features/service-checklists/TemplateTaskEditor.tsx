import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import type { TemplateTaskDraft } from './types'

export default function TemplateTaskEditor({ items, onChange, disabled = false }: {
  items: TemplateTaskDraft[]; onChange: (items: TemplateTaskDraft[]) => void; disabled?: boolean
}) {
  const move = (index: number, delta: number) => {
    const next = [...items]
    ;[next[index], next[index + delta]] = [next[index + delta], next[index]]
    onChange(next)
  }
  return <div className="space-y-3">
    <ol className="space-y-2">
      {items.map((item, index) => <li key={item.id ?? index} className="rounded-lg border border-gray-200 bg-gray-50 p-2">
        <label className="block text-xs font-medium text-gray-600">Task {index + 1}
          <input aria-label={`Task ${index + 1}`} value={item.label} maxLength={300} disabled={disabled}
            onChange={event => onChange(items.map((value, i) => i === index ? { ...value, label: event.target.value } : value))}
            className="mt-1 w-full min-w-0 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900" />
        </label>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <label className="flex min-h-10 items-center gap-2 whitespace-nowrap text-xs text-gray-700">
            <input type="checkbox" checked={item.required} disabled={disabled} aria-label={`Task ${index + 1} required`}
              onChange={event => onChange(items.map((value, i) => i === index ? { ...value, required: event.target.checked } : value))} />Required
          </label>
          <div className="flex gap-1">
            <button type="button" aria-label={`Move task ${index + 1} up`} disabled={disabled || index === 0} onClick={() => move(index, -1)} className="rounded p-2 text-gray-600 disabled:opacity-30"><ArrowUp size={18} /></button>
            <button type="button" aria-label={`Move task ${index + 1} down`} disabled={disabled || index === items.length - 1} onClick={() => move(index, 1)} className="rounded p-2 text-gray-600 disabled:opacity-30"><ArrowDown size={18} /></button>
            <button type="button" aria-label={`Remove task ${index + 1}`} disabled={disabled} onClick={() => onChange(items.filter((_, i) => i !== index))} className="rounded p-2 text-red-600 disabled:opacity-30"><Trash2 size={18} /></button>
          </div>
        </div>
      </li>)}
    </ol>
    <button type="button" disabled={disabled || items.length >= 50} onClick={() => onChange([...items, { label: '', required: true }])}
      className="inline-flex min-h-10 items-center gap-1 whitespace-nowrap text-sm font-semibold text-gray-700 disabled:opacity-40"><Plus size={16} />Add task</button>
    {items.length === 50 && <p className="text-xs text-gray-500">50 tasks maximum.</p>}
  </div>
}
