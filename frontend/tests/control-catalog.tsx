import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Plus, RotateCcw } from 'lucide-react'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '../src/contexts/ThemeContext'
import { ControlButton, ControlInput, ControlGroup } from '../src/components/ui/Controls'
import PlatformSelect from '../src/components/PlatformSelect'
import ShopWorkSelect from '../src/features/dashboard/ShopWorkSelect'
import StaffSearchField from '../src/components/ui/StaffSearchField'
import QuantityStepper from '../src/components/QuantityStepper'
import DatePicker from '../src/components/DatePicker'
import '../src/index.css'
import '../src/features/repair-orders/repairOrderControls.css'
import '../src/features/global-search/ShopSearch.css'
import '../src/features/fleet/fleet.css'
import '../src/features/fleet/proximity.css'
import '../src/features/vehicle-issues/vehicleIssues.css'

function Catalog() {
  const [filter, setFilter] = useState('open')
  const [quantity, setQuantity] = useState(2)
  const [day, setDay] = useState('')
  const [message, setMessage] = useState('No open truck issues.')
  const [dark, setDark] = useState(false)
  return <main className="db-staff-shell db-presentation-new" data-appearance-mode={dark ? 'dark' : 'light'} style={{ ['--shell-field' as string]: dark ? '#0b1728' : '#f6f8fb', display: 'block', gridTemplateColumns: 'none', minHeight: '100vh', padding: 24, background: dark ? '#0b1728' : '#f6f8fb', color: dark ? '#f6f8fb' : '#14243a' }}>
    <div style={{ maxWidth: 1000, margin: 'auto' }}>
      <h1 style={{ fontSize: 24, marginBottom: 12 }}>Shared controls</h1>
      <p style={{ marginBottom: 24 }}>Local component catalog. Actions change this preview only.</p>
      <ControlButton type="button" onClick={() => setDark(!dark)} style={{ marginBottom: 24 }}>Switch appearance</ControlButton>
      <div className="db-staff-content">
        <section className="db-truck-issues" aria-label="Truck issues">
          <header className="db-truck-issues__header"><h3>Truck issues</h3><ControlGroup className="db-truck-issues__controls">
            <ShopWorkSelect label="Issue state" value={filter} onChange={setFilter} options={[{ value: 'open', label: 'Open' }, { value: 'resolved', label: 'Resolved' }]} />
            <ControlButton controlKind="icon" type="button" aria-label="Refresh truck issues" onClick={() => setMessage('Refreshed. No open truck issues.')}><RotateCcw /></ControlButton>
            <ControlButton type="button" onClick={() => setMessage('Add issue selected.')}><Plus />Add issue</ControlButton>
          </ControlGroup></header><p role="status">{message}</p>
        </section>
        <section aria-label="Compound control regression" className="db-repair-orders-controls" style={{ display: 'grid', gap: 12, marginTop: 24 }}>
          <div className="db-repair-orders-new__filters">
            <div data-db-control-shell="proxy" className="db-repair-orders-new__status-select" style={{ display: 'block' }}><ControlButton type="button" aria-label="Legacy status trigger">All statuses</ControlButton></div>
            <ControlButton type="button">Overdue</ControlButton>
          </div>
          {['db-parts-workbench__search', 'db-parts-operations__search', 'db-shop-search-field', 'db-labor-book-time__search', 'fld-search', 'proximity-search', 'driver-profile-search', 'wo-svc-search'].map(name => <label key={name} data-db-control-shell="field" className={name} style={{ display: 'flex', alignItems: 'center', border: '1px solid currentColor' }}><Plus aria-hidden="true" size={16} /><ControlInput aria-label={name} placeholder="Search" style={{ width: '100%', minWidth: 0 }} /></label>)}
        </section>
        <section style={{ marginTop: 28, display: 'grid', gap: 16 }} aria-label="Field controls">
          <h2>Fields and menus</h2>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <StaffSearchField accessibleLabel="Search" placeholder="Search trucks" />
            <PlatformSelect aria-label="Status" value={filter} onChange={e => setFilter(e.target.value)}><option value="open">Open</option><option value="resolved">Resolved</option></PlatformSelect>
            <ControlButton type="button" disabled>Unavailable</ControlButton>
          </div>
          <label>Reference<ControlInput aria-label="Reference" placeholder="Optional reference" style={{ ['--shell-field' as string]: dark ? '#0b1728' : '#f6f8fb', display: 'block', border: '1px solid #94a3b8', paddingInline: 10 }} /></label>
          <QuantityStepper ariaLabel="Quantity" value={quantity} onChange={setQuantity} align="start" />
          <DatePicker label="Follow-up date" value={day} onChange={setDay} />
        </section>
      </div>
    </div>
  </main>
}
createRoot(document.getElementById('root')!).render(<BrowserRouter><ThemeProvider><Catalog /></ThemeProvider></BrowserRouter>)
