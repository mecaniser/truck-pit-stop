import { useRef } from 'react'
import { Description, Dialog, DialogBackdrop, DialogPanel, DialogTitle } from '@headlessui/react'
import { X } from 'lucide-react'
import { ControlButton } from '@/components/ui/Controls'
import './account-confirmation-dialog.css'

interface AccountConfirmationDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  cancelLabel: string
  onConfirm: () => void
  onCancel: () => void
  appearance?: 'dark' | 'light'
}

/** Shared account confirmation: Headless UI owns inert background, focus trap,
 * Escape/outside dismissal and restoration to the invoking control. */
export default function AccountConfirmationDialog({
  open, title, description, confirmLabel, cancelLabel, onConfirm, onCancel, appearance = 'dark',
}: AccountConfirmationDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  return <Dialog open={open} onClose={onCancel} initialFocus={cancelRef} role="alertdialog" className="fixed inset-0 z-[100]">
    <DialogBackdrop className={`cp-confirm-backdrop fixed inset-0 ${appearance === 'light' ? 'bg-[#0D1A33]/30' : 'bg-black/70'}`} />
    <div className="fixed inset-0 flex items-center justify-center overflow-y-auto p-4">
      <DialogPanel transition data-db-touch-controls data-appearance-mode={appearance} className="cp-confirm-panel max-h-[calc(100dvh-2rem)] w-full max-w-md overflow-y-auto rounded-2xl border p-5 sm:p-6">
        <div className="cp-confirm-heading">
          <DialogTitle className="text-xl font-semibold">{title}</DialogTitle>
          <ControlButton controlKind="icon" type="button" aria-label="Close dialog and keep editing" onClick={onCancel} className="cp-confirm-close">
            <X aria-hidden="true" />
          </ControlButton>
        </div>
        <Description className="cp-confirm-caption mt-2 text-sm leading-6">{description}</Description>
        <div className="cp-confirm-actions">
          <ControlButton ref={cancelRef} type="button" onClick={onCancel} className="cp-confirm-cancel rounded-lg border px-4 text-sm font-semibold">{cancelLabel}</ControlButton>
          <ControlButton type="button" onClick={onConfirm} className="cp-confirm-discard rounded-lg px-4 text-sm font-semibold">{confirmLabel}</ControlButton>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
}
