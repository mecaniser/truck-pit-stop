import { useEffect, useRef, type ComponentPropsWithoutRef } from 'react'

type Props = Omit<ComponentPropsWithoutRef<'a'>, 'onClick' | 'autoFocus' | 'href'> & {
  href: string
  onOpen: () => void
  restoreFocus?: boolean
}

/** Keep record navigation in the current workspace on a normal click.
 * The href also supports copy, middle-click and opening in a new tab. */
export default function WorkspaceRecordLink({ onOpen, restoreFocus, ...props }: Props) {
  const ref = useRef<HTMLAnchorElement>(null)
  useEffect(() => { if (restoreFocus) ref.current?.focus() }, [restoreFocus])
  return <a {...props} ref={ref} onClick={event => {
    if (event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
    event.preventDefault()
    onOpen()
  }} />
}
