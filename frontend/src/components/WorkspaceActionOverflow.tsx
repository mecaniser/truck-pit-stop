import { ControlButton } from '@/components/ui/Controls'
import { type ReactNode } from 'react'
import { useCompactWorkspace } from '@/hooks/useCompactWorkspace'
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { MoreHorizontal, X } from 'lucide-react'
import './workspace-mobile.css'

/** One set of action handlers: inline on desktop, a bounded action panel on phones. */
export default function WorkspaceActionOverflow({ children, label = 'More actions' }: {
  children: ReactNode | ((close: () => void) => ReactNode)
  label?: string
}) {
  const compact = useCompactWorkspace()
  if (!compact) return <>{typeof children === 'function' ? children(() => {}) : children}</>
  return <Popover className="db-workspace-overflow-trigger">
    {({ close }) => <>
      <PopoverButton data-db-control="action" aria-label={label} className="db-workspace-more">
        <MoreHorizontal className="h-5 w-5" aria-hidden="true" /><span>More</span>
      </PopoverButton>
      <PopoverPanel anchor="top end" aria-label={label} className="db-workspace-overflow">
        <div className="db-workspace-overflow__heading">
          <h3>{label}</h3>
          <ControlButton controlKind="icon" type="button" aria-label={`Close ${label.toLowerCase()}`} onClick={() => close()}><X className="h-5 w-5" /></ControlButton>
        </div>
        {typeof children === 'function' ? children(() => close()) : children}
      </PopoverPanel>
    </>}
  </Popover>
}
