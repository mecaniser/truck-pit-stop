import { Children, Fragment, forwardRef, isValidElement, useId, useLayoutEffect, useRef, useState, type ChangeEvent, type AriaAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import BaseSelect, { type BaseSelectOption } from './BaseSelect'

/** Controlled shared menu with native form serialization, validation and focus refs. */
function textOf(node: ReactNode): string {
  return Children.toArray(node).map(child => typeof child === 'string' || typeof child === 'number'
    ? String(child) : isValidElement<{ children?: ReactNode }>(child) ? textOf(child.props.children) : '').join('').replace(/\s+/g, ' ').trim()
}
function optionsOf(children: ReactNode, groupDisabled = false): BaseSelectOption[] {
  return Children.toArray(children).flatMap(child => {
    if (!isValidElement<{ children?: ReactNode; value?: string | number; disabled?: boolean; label?: string }>(child)) return []
    if (child.type === Fragment || child.type === 'optgroup') return optionsOf(child.props.children, groupDisabled || (child.type === 'optgroup' && Boolean(child.props.disabled)))
    if (child.type !== 'option') return []
    const label = child.props.label ?? textOf(child.props.children)
    return [{ value: String(child.props.value ?? label), label, disabled: groupDisabled || child.props.disabled }]
  })
}

type PlatformSelectProps = Pick<SelectHTMLAttributes<HTMLSelectElement>,
  'children' | 'id' | 'name' | 'disabled' | 'required' | 'autoFocus' | 'className' | 'style' | 'onChange' | 'onBlur' | 'onInvalid' | 'form' | 'title'>
  & AriaAttributes & { value: string | number }

const PlatformSelect = forwardRef<HTMLSelectElement, PlatformSelectProps>(
  function PlatformSelect({ children, value, onChange, onInvalid, 'aria-label': ariaLabel, 'aria-labelledby': ariaLabelledBy, id, className = '', style, autoFocus, ...props }, forwardedRef) {
    const generatedId = useId()
    const fieldId = id ?? `platform-select-${generatedId}`
    const native = useRef<HTMLSelectElement | null>(null)
    const root = useRef<HTMLDivElement>(null)
    const options = optionsOf(children)
    const [label, setLabel] = useState<string>()
    const [variant, setVariant] = useState<'light' | 'dark'>('light')
    const [invalid, setInvalid] = useState('')
    const [effectiveDisabled, setEffectiveDisabled] = useState(Boolean(props.disabled))
    const selectedValue = String(value)
    useLayoutEffect(() => {
      const update = () => setEffectiveDisabled(Boolean(props.disabled || native.current?.matches(':disabled')))
      update()
      const observer = new MutationObserver(update)
      for (let ancestor = root.current?.parentElement; ancestor; ancestor = ancestor.parentElement) {
        if (ancestor.tagName === 'FIELDSET') observer.observe(ancestor, { attributes: true, attributeFilter: ['disabled'] })
      }
      return () => observer.disconnect()
    }, [props.disabled])
    // Layout belongs to the containing field; decoration belongs to BaseSelect.
    const layout = className.split(/\s+/).filter(token => /^(?:[\w-]+:)*(?:w-|min-w-|max-w-|flex-|grow|shrink|basis-|self-|col-|row-|m[trblxy]?-)/.test(token)).join(' ')

    useLayoutEffect(() => {
      const element = root.current
      if (!element) return
      const parentLabel = element.closest('label') ?? (element.previousElementSibling?.tagName === 'LABEL' ? element.previousElementSibling : null)
      if (parentLabel) {
        const copy = parentLabel.cloneNode(true) as HTMLElement
        copy.querySelectorAll('input,select,button,.platform-select-field').forEach(control => control.remove())
        setLabel(copy.textContent?.replace(/\s+/g, ' ').trim() || undefined)
      }
      const updateSurface = () => {
      for (let surface: HTMLElement | null = element; surface; surface = surface.parentElement) {
        const color = getComputedStyle(surface).backgroundColor
        const rgb = color.match(/^rgba?\(([^)]+)\)$/)?.[1].split(/[,\s/]+/).filter(Boolean).map(Number)
        if (!rgb || rgb.length < 3 || (rgb.length > 3 && rgb[3] < .5)) continue
        setVariant((rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722) < 128 ? 'dark' : 'light')
        break
      }
      }
      updateSurface()
      const observer = new MutationObserver(updateSurface)
      for (let surface = element.parentElement; surface; surface = surface.parentElement) {
        observer.observe(surface, { attributes: true, attributeFilter: ['class', 'style', 'data-appearance-mode'] })
      }
      return () => observer.disconnect()
    }, [className])

    const change = (next: string) => {
      const control = native.current
      if (!control || control.disabled || control.matches(':disabled')) return
      control.value = next
      control.dispatchEvent(new Event('change', { bubbles: true }))
    }
    return <div ref={root} className={`platform-select-field min-w-0 ${layout}`} style={style}
      onBlur={event => {
        if ((event.target as EventTarget) !== native.current && !event.currentTarget.contains(event.relatedTarget)) {
          native.current?.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
        }
      }}>
      <BaseSelect id={fieldId} options={options} value={selectedValue} onChange={change}
        disabled={effectiveDisabled} searchable={false} variant={variant} heightClass="h-11" optionHeightClass="min-h-11"
        triggerClassName={className} autoFocus={autoFocus} selectOnly
        ariaLabel={ariaLabel ?? label} ariaLabelledBy={ariaLabelledBy}
        ariaDescribedBy={[props['aria-describedby'], invalid ? `${fieldId}-error` : undefined].filter(Boolean).join(' ') || undefined}
        ariaInvalid={invalid ? true : props['aria-invalid']} ariaRequired={props.required} />
      <select {...props} id={`${fieldId}-native`} aria-hidden="true" tabIndex={-1}
        ref={element => { native.current = element; if (typeof forwardedRef === 'function') forwardedRef(element); else if (forwardedRef) forwardedRef.current = element }}
        value={selectedValue} onChange={(event: ChangeEvent<HTMLSelectElement>) => { setInvalid(''); onChange?.(event) }}
        onFocus={() => { document.getElementById(fieldId)?.focus() }}
        onInvalid={event => { event.preventDefault(); setInvalid(event.currentTarget.validationMessage); document.getElementById(fieldId)?.focus(); onInvalid?.(event) }}
        style={{ position: 'fixed', top: 0, left: 0, width: 1, height: 1, opacity: 0, clipPath: 'inset(50%)', pointerEvents: 'none' }}>
        {children}
      </select>
      {invalid && <span id={`${fieldId}-error`} role="alert" className="mt-1 block text-sm text-red-600">{invalid}</span>}
    </div>
  },
)
export default PlatformSelect
