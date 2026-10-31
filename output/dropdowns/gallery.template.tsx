import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import PlatformSelect from './src/components/PlatformSelect'
import './src/index.css'
function Gallery() {
  const dark = new URLSearchParams(location.search).get('mode') === 'dark'
  const [asset, setAsset] = useState('tractor'), [consent, setConsent] = useState('phone'), [disabled, setDisabled] = useState(false), [required, setRequired] = useState('')
  const [modal, setModal] = useState(false), [supplier, setSupplier] = useState('short')
  return <main style={{ background: dark ? '#111827' : '#f8fafc', color: dark ? '#f8fafc' : '#111827', minHeight: '100vh', padding: 20, fontFamily: 'Inter, sans-serif' }}>
    <h1 style={{ fontSize: 22, fontWeight: 700 }}>Dropdown acceptance fixtures</h1>
    <div style={{ display: 'grid', gap: 24, maxWidth: 560, marginTop: 24 }}>
      <label>Equipment type<PlatformSelect value={asset} onChange={e => setAsset(e.target.value)}><option value="tractor">Tractor / Truck</option><option value="trailer">Trailer</option><option value="other">Other equipment</option><option value="unknown">Unclassified</option></PlatformSelect></label>
      <fieldset disabled={disabled}><label>Payment consent<PlatformSelect value={consent} onChange={e => setConsent(e.target.value)}><option value="phone">Phone</option><option value="in_person">In person</option><option disabled value="expired">Previous authorization unavailable</option></PlatformSelect></label></fieldset>
      <button type="button" onClick={() => setDisabled(value => !value)}>Toggle fieldset disabled</button>
      <label>Supplier<PlatformSelect value={supplier} onChange={e => setSupplier(e.target.value)}><option value="short">Shop default</option><option value="long">Long supplier name for fleet equipment maintenance and specialty truck and trailer components</option><option value="unbroken">AReallyLongUnbrokenSupplierIdentificationThatMustNotEscapeItsDropdownContainer</option></PlatformSelect></label>
      <form onSubmit={e => e.preventDefault()}><label>Repeated time occurrence<PlatformSelect value={required} onChange={e => setRequired(e.target.value)} required><option value="">Choose occurrence</option><option value="0">First occurrence</option><option value="1">Second occurrence</option></PlatformSelect></label><button style={{ marginTop: 8 }} type="submit">Validate required field</button></form>
      <button type="button" onClick={() => setModal(true)}>Open high-layer modal</button>
    </div>
    {modal && <div style={{ position: 'fixed', inset: 0, zIndex: 1200, display: 'grid', placeItems: 'center', background: '#0008', padding: 16 }}>
      <section aria-label="High-layer modal" style={{ background: '#fff', color: '#111827', borderRadius: 12, padding: 20, width: '100%', maxWidth: 480, maxHeight: '75vh', overflow: 'auto' }}><label>Modal asset<PlatformSelect value={asset} onChange={e => setAsset(e.target.value)}><option value="tractor">Tractor / Truck</option><option value="trailer">Trailer</option><option value="other">Other equipment</option><option value="unknown">Unclassified</option></PlatformSelect></label><button onClick={() => setModal(false)} style={{ marginTop: 12 }}>Close modal</button></section>
    </div>}
  </main>
}
createRoot(document.getElementById('root')!).render(<Gallery />)
