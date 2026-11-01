import { ControlButton } from '@/components/ui/Controls'
import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import SMSSetup from '../../communications/SMSSetup'
import '../../communications/communications.css'

export default function ShopSMSRegistration({ tenantId, shopName, onClose }: {
  tenantId: string; shopName: string; onClose: () => void
}) {
  return <RegistrationDialog key={tenantId} tenantId={tenantId} shopName={shopName} onClose={onClose} />
}
function RegistrationDialog({ tenantId, shopName, onClose }: {
  tenantId: string; shopName: string; onClose: () => void
}) {
  const [dirty, setDirty] = useState(false)
  const [confirmClose, setConfirmClose] = useState(false)
  const dialog = useRef<HTMLElement>(null)
  const requestClose = () => dirty ? setConfirmClose(true) : onClose()
  useEffect(() => {
    const opener = document.activeElement
    dialog.current?.querySelector<HTMLButtonElement>('button')?.focus()
    return () => { if (opener instanceof HTMLElement) opener.focus() }
  }, [])
  return <div className="communications-surface">
    <div className="sheet-backdrop settings-backdrop">
      <section className="connections-sheet message-settings" ref={dialog} role="dialog" aria-modal="true" aria-label={`Repair texting registration for ${shopName}`}
        onKeyDown={event => {
          if (event.key === 'Escape') { event.stopPropagation(); requestClose() }
          if (event.key !== 'Tab') return
          const controls = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href]') ?? [])
          const first = controls[0]; const last = controls[controls.length - 1]
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
          if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
        }}>
        <header><div><h2>{shopName}</h2><p>Platform administration · Repair texting</p></div>
          <ControlButton controlKind="icon" className="icon-button" aria-label="Close registration" onClick={requestClose}><X size={20} /></ControlButton>
        </header>
        {confirmClose && <div role="alert" className="sms-hold"><div>
          <p>Discard unsaved registration changes?</p>
          <ControlButton className="subtle-button" onClick={() => setConfirmClose(false)}>Keep editing</ControlButton>
          <ControlButton className="subtle-button" onClick={onClose}>Discard changes</ControlButton>
        </div></div>}
        <SMSSetup tenantId={tenantId} shopName={shopName} onClose={requestClose} onDirtyChange={setDirty} />
      </section>
    </div>
  </div>
}
