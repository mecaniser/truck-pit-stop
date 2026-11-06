import { useRef } from 'react'
import { Description, Dialog, DialogBackdrop, DialogPanel, DialogTitle } from '@headlessui/react'
import { ControlButton } from '@/components/ui/Controls'

interface AccountConfirmationDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  cancelLabel: string
  onConfirm: () => void
  onCancel: () => void
}

/** Shared account confirmation: Headless UI owns inert background, focus trap,
 * Escape/outside dismissal and restoration to the invoking control. */
export default function AccountConfirmationDialog({
  open, title, description, confirmLabel, cancelLabel, onConfirm, onCancel,
}: AccountConfirmationDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  return <Dialog open={open} onClose={onCancel} initialFocus={cancelRef} role="alertdialog" className="fixed inset-0 z-[100]">
    <DialogBackdrop className="fixed inset-0 bg-black/70" />
    <div className="fixed inset-0 flex items-center justify-center overflow-y-auto p-4">
      <DialogPanel transition data-db-touch-controls className="max-h-[calc(100dvh-2rem)] w-full max-w-md overflow-y-auto rounded-2xl border border-[#30384b] bg-[#161a26] p-5 text-[#eceef4] shadow-xl sm:p-6">
        <DialogTitle className="text-xl font-semibold">{title}</DialogTitle>
        <Description className="mt-3 text-sm leading-6 text-[#b5bdcf]">{description}</Description>
        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-end">
          <ControlButton ref={cancelRef} type="button" onClick={onCancel} className="rounded-lg border border-[#434c63] bg-[#12161f] px-4 text-sm font-semibold text-[#eceef4] hover:bg-[#232939]">{cancelLabel}</ControlButton>
          <ControlButton type="button" onClick={onConfirm} className="rounded-lg bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-500">{confirmLabel}</ControlButton>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
}
