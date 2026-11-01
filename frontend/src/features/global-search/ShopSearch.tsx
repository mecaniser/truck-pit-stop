import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { createContext, useContext, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from '@headlessui/react'
import { useQueries } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Search, X } from 'lucide-react'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { canSearchShop, MIN_SEARCH_LENGTH, SEARCH_LIMIT, shopSearchSources } from './searchSources'
import './ShopSearch.css'

const SearchContext = createContext<(() => void) | null>(null)

export function ShopSearchButton({ mobile = false }: { mobile?: boolean }) {
  const open = useContext(SearchContext)
  if (!open) return null
  return <ControlButton type="button" onClick={open} aria-label="Search shop" aria-keyshortcuts="Control+k Meta+k" title="Search shop (Ctrl/⌘ K)" className={`db-shop-search-trigger ${mobile ? 'db-shop-search-trigger--mobile' : 'db-staff-nav__utility'}`}>
    <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
    <span className={mobile ? '' : 'db-staff-nav__utility-label'}>Search</span>
  </ControlButton>
}

export function ShopSearchProvider({ children }: { children: ReactNode }) {
  const session = useAuthStore(getAuthenticatedSessionIdentity)
  const user = useAuthStore(state => state.user)
  if (!session || !canSearchShop(user)) return <>{children}</>
  // Remount the controller on logout/login, tenant, account or role changes.
  // Search terms, focus state and results belong only to that live session.
  return <SearchController key={session} session={session} role={user!.role}>{children}</SearchController>
}

function SearchController({ session, role, children }: { session: string; role: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey || event.key.toLowerCase() !== 'k') return
      // Leave shortcuts in another open workflow dialog to that workflow.
      if (!open && document.querySelector('[role="dialog"]')) return
      event.preventDefault()
      setOpen(true)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open])
  return <SearchContext.Provider value={() => setOpen(true)}>
    {children}
    {open && <ShopSearchDialog session={session} role={role} onClose={() => setOpen(false)} />}
  </SearchContext.Provider>
}

function ShopSearchDialog({ session, role, onClose }: { session: string; role: string; onClose: () => void }) {
  const [input, setInput] = useState('')
  const query = input.trim()
  const debouncedQuery = useDebouncedValue(query, 250)
  const inputRef = useRef<HTMLInputElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const ready = query.length >= MIN_SEARCH_LENGTH && query === debouncedQuery
  const moveFocus = (event: KeyboardEvent) => {
    const links = Array.from(panelRef.current?.querySelectorAll<HTMLAnchorElement>('[data-shop-result]') ?? [])
    if (!links.length) return
    const index = links.indexOf(document.activeElement as HTMLAnchorElement)
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      links[Math.min(index + 1, links.length - 1)].focus()
    } else if (event.key === 'ArrowUp' && index >= 0) {
      event.preventDefault()
      if (index === 0) inputRef.current?.focus()
      else links[index - 1].focus()
    }
  }
  return <Dialog open onClose={onClose} initialFocus={inputRef} className="db-shop-search-dialog">
    <DialogBackdrop className="db-shop-search-backdrop" />
    <div className="db-shop-search-position">
      <DialogPanel ref={panelRef} className="db-shop-search-panel" onKeyDown={moveFocus}>
        <header className="db-shop-search-header">
          <DialogTitle>Search shop</DialogTitle>
          <ControlButton controlKind="icon" type="button" onClick={onClose} aria-label="Close search" className="db-shop-search-close"><X className="h-5 w-5" aria-hidden="true" /></ControlButton>
        </header>
        <div data-db-control-shell="field" className="db-shop-search-field">
          <Search className="h-5 w-5 shrink-0" aria-hidden="true" />
          <ControlInput ref={inputRef} aria-label="Search shop records" aria-describedby="shop-search-hint" value={input} maxLength={100} onChange={event => setInput(event.target.value)} autoComplete="off" spellCheck={false} placeholder="Name, unit, VIN, RO number or part" />
        </div>
        <p id="shop-search-hint" className="db-shop-search-hint">{role === 'mechanic' ? 'Customers, vehicles and repair orders' : 'Customers, vehicles, repair orders and inventory'}</p>
        <div className="db-shop-search-results">
          {query.length < MIN_SEARCH_LENGTH ? <p className="db-shop-search-message">Enter at least {MIN_SEARCH_LENGTH} characters to search.</p>
            : !ready ? <p role="status" className="db-shop-search-message">Searching…</p>
            : <SearchResults key={debouncedQuery} session={session} role={role} query={debouncedQuery} onChoose={onClose} />}
        </div>
        <footer className="db-shop-search-footer"><span>↑ ↓ to browse · Enter to open</span><span>Esc to close</span></footer>
      </DialogPanel>
    </div>
  </Dialog>
}

function SearchResults({ session, role, query, onChoose }: { session: string; role: string; query: string; onChoose: () => void }) {
  const sources = shopSearchSources(role)
  const results = useQueries({ queries: sources.map(source => ({
    queryKey: ['shop-search', session, source.id, query],
    queryFn: ({ signal }: { signal: AbortSignal }) => source.search(query, signal),
    retry: false,
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
  })) })
  const searching = results.some(result => result.isPending)
  const count = results.reduce((sum, result) => sum + (result.data?.length ?? 0), 0)
  const failed = results.some(result => result.isError)
  return <>
    <p role="status" className="db-shop-search-status">{searching ? 'Searching…' : count ? `${count} ${count === 1 ? 'result' : 'results'}${failed ? ' · Some sources unavailable' : ''}` : failed ? 'Some sources unavailable' : `No matches for “${query}”`}</p>
    {sources.map((source, index) => {
      const result = results[index]
      return <section key={source.id} aria-labelledby={`shop-search-${source.id}`} className="db-shop-search-group">
        <h3 id={`shop-search-${source.id}`}>{source.label}</h3>
        {result.isError ? <div className="db-shop-search-error"><span>{source.label} unavailable.</span><ControlButton type="button" onClick={() => void result.refetch()}>Retry {source.label.toLowerCase()}</ControlButton></div>
          : result.isPending ? <p className="db-shop-search-group-note">Searching…</p>
          : result.data?.length ? <>
            <ul>{result.data.map(item => <li key={item.id}><Link to={item.href} onClick={onChoose} data-shop-result className="db-shop-search-result">
              <span className="db-shop-search-result-copy"><strong>{item.title}</strong>{item.description && <span>{item.description}</span>}</span>
              <ArrowUpRight className="h-4 w-4 shrink-0" aria-hidden="true" />
            </Link></li>)}</ul>
            {result.data.length === SEARCH_LIMIT && <p className="db-shop-search-group-note">Showing the first {SEARCH_LIMIT} matches. Refine your search for more.</p>}
          </> : <p className="db-shop-search-group-note">No matches</p>}
      </section>
    })}
  </>
}
