import { ControlInput, ControlButton } from '@/components/ui/Controls'
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import './checklists.css'
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
        <label className="block text-xs font-medium !text-[#4b5563]">Task {index + 1}
          <ControlInput aria-label={`Task ${index + 1}`} value={item.label} maxLength={300} disabled={disabled}
            onChange={event => onChange(items.map((value, i) => i === index ? { ...value, label: event.target.value } : value))}
            className="mt-1 w-full min-w-0 rounded-lg border border-gray-300 bg-white px-3  text-sm !text-[#111827] [caret-color:#111827] [-webkit-text-fill-color:#111827]" />
        </label>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <label className="flex min-h-10 items-center gap-2 whitespace-nowrap text-xs !text-[#374151]">
            <input type="checkbox" checked={item.required} disabled={disabled} aria-label={`Task ${index + 1} required`}
              onChange={event => onChange(items.map((value, i) => i === index ? { ...value, required: event.target.checked } : value))} />Required
          </label>
          <div className="flex gap-1">
            <ControlButton controlKind="icon" type="button" aria-label={`Move task ${index + 1} up`} disabled={disabled || index === 0} onClick={() => move(index, -1)} className="rounded p-2 !text-[#4b5563] disabled:opacity-30"><ArrowUp size={18} /></ControlButton>
            <ControlButton controlKind="icon" type="button" aria-label={`Move task ${index + 1} down`} disabled={disabled || index === items.length - 1} onClick={() => move(index, 1)} className="rounded p-2 !text-[#4b5563] disabled:opacity-30"><ArrowDown size={18} /></ControlButton>
            <ControlButton controlKind="icon" type="button" aria-label={`Remove task ${index + 1}`} disabled={disabled} onClick={() => onChange(items.filter((_, i) => i !== index))} className="rounded p-2 !text-[#b91c1c] disabled:opacity-30"><Trash2 size={18} /></ControlButton>
          </div>
        </div>
      </li>)}
    </ol>
    <ControlButton type="button" disabled={disabled || items.length >= 50} onClick={() => onChange([...items, { label: '', required: true }])}
      className="inline-flex  items-center gap-1 whitespace-nowrap text-sm font-semibold !text-[#374151] disabled:opacity-40"><Plus size={16} />Add task</ControlButton>
    {items.length === 50 && <p className="text-xs !text-[#4b5563]">50 tasks maximum.</p>}
  </div>
}
