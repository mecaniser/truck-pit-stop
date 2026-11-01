import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { Dialog, DialogPanel, DialogTitle } from "@headlessui/react";
import InboxSelect from "./InboxSelect";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { ArrowUpRight, Link2, Loader2, Plus, Truck, X } from "lucide-react";
import { errorMessage } from "./api";
import { customerContextApi as client, type ContactSummary, type ContextMutation, type ContextPage, type CustomerContext, type CustomerSummary, type RepairScope, type RepairStatus, type RepairSummary, type VehicleSummary } from "./customerContextApi";
import type { Conversation } from "./model";
import "./customerContext.css";

interface PendingContextIntent {payload: ContextMutation; key: string}
function readPending(key: string): PendingContextIntent | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || "null") as PendingContextIntent | null;
    return value && typeof value.key === "string" && value.payload && ["link", "create_contact", "create_customer"].includes(value.payload.action) && typeof value.payload.expected_version === "number" ? value : null;
  } catch {return null;}
}
const vehicleLabel = (v: VehicleSummary) => [v.unit_number ? `Unit ${v.unit_number}` : null, v.make, v.model].filter(Boolean).join(" · ") || "Truck";
const personLabel = (p: ContactSummary) => [p.first_name, p.last_name].filter(Boolean).join(" ");
const statusLabel = (value: string) => value.replace(/_/g, " ");

/** CRM association is deliberately separate from the conversation's delivery identity. */
export default function CustomerRepairContext({ conversation, beforeNavigate, sessionKey, children, onLinked }: {conversation: Conversation; beforeNavigate: () => void; sessionKey: string; children?: ReactNode; onLinked?: () => void}) {
  const [context, setContext] = useState<CustomerContext | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const storageKey = `inbox-customer-intent:${sessionKey}:${conversation.id}`;
  const [editing, setEditing] = useState<"link" | "create" | null>(() => readPending(storageKey) ? "link" : null);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    void client.context(conversation.id, controller.signal).then(value => { if (!controller.signal.aborted) setContext(value); }).catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)); });
    return () => controller.abort();
  }, [conversation.id, retry]);
  return <section className="crm-context" aria-label="Customer and repair history">

    {error ? <div role="alert" className="crm-error">{error}<ControlButton type="button" onClick={() => setRetry(n => n + 1)}>Retry</ControlButton></div> : !context ? <p role="status" className="crm-muted"><Loader2 size={14} className="crm-spin" /> Loading customer…</p> : <>
      <div className="crm-contact-card"><div className="crm-heading"><strong className="crm-person">{context.contact ? personLabel(context.contact) : conversation.customerName}</strong>{context.can_manage && context.contact && <ControlButton type="button" className="crm-text-button" onClick={() => setEditing("link")}>Change link</ControlButton>}</div>
      {context.customer && <p className="crm-company">{context.customer.company_name || context.customer.display_name}</p>}
      {context.contact?.role && <p className="crm-role">{context.contact.role}</p>}
      <p className="crm-contact-number">{conversation.identityLabel}</p>
      {conversation.sendPolicy.reason === "opted_out" && <p className="context-warning">SMS opted out</p>}
      {!context.contact && <p className="crm-muted">{context.link_state === "unavailable" ? "Linked customer unavailable." : context.customer ? "Choose the person for this conversation." : "No customer linked."}</p>}
      {context.can_manage && !context.contact && <div className="crm-actions"><ControlButton type="button" onClick={() => setEditing("link")}><Link2 size={14} />Link customer</ControlButton>{conversation.conversationKind === "inquiry" && <ControlButton type="button" onClick={() => setEditing("create")}><Plus size={14} />Add customer</ControlButton>}</div>}
      {children}</div>
      <RepairLists key={`${context.version}:${context.contact?.id ?? "none"}`} id={conversation.id} context={context} beforeNavigate={beforeNavigate} refreshContext={() => setRetry(n => n + 1)} />
    </>}
    {editing && context && <LinkCustomerDialog storageKey={storageKey} conversation={conversation} context={context} initialMode={editing} close={() => setEditing(null)} saved={value => {setContext(value); setEditing(null); onLinked?.();}} refresh={() => setRetry(n => n + 1)} />}
  </section>;
}

function RepairLists({id, context, beforeNavigate, refreshContext}: {id: string; context: CustomerContext; beforeNavigate: () => void; refreshContext: () => void}) {
  const [scope, setScope] = useState<RepairScope>("contact");
  const [status, setStatus] = useState<RepairStatus>("active");
  const [repairs, setRepairs] = useState<ContextPage<RepairSummary> | null>(null);
  const [vehicles, setVehicles] = useState<ContextPage<VehicleSummary> | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [linkTarget, setLinkTarget] = useState<RepairSummary | null>(null);
  const generation = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const lock = useRef(false);
  const intents = useRef<Record<string, string>>({});
  useEffect(() => {
    const controller = new AbortController(); controllerRef.current = controller;
    const request = ++generation.current;
    setRepairs(null); setVehicles(null); setError(""); setBusy(false);
    void Promise.all([client.repairs(id, scope, status, controller.signal), client.vehicles(id, scope, controller.signal)]).then(([r,v]) => {
      if (request === generation.current && !controller.signal.aborted) {setRepairs(r); setVehicles(v);}
    }).catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)); });
    return () => { controller.abort(); generation.current = request + 1; };
  }, [id, scope, status, retry]);
  async function more(kind: "repairs" | "vehicles") {
    const cursor = kind === "repairs" ? repairs?.next_cursor : vehicles?.next_cursor;
    const controller = controllerRef.current; const request = generation.current;
    if (!cursor || !controller || lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try {
      if (kind === "repairs") {
        const next = await client.repairs(id, scope, status, controller.signal, cursor);
        if (request === generation.current) setRepairs(old => ({...next, items: [...(old?.items ?? []), ...next.items]}));
      } else {
        const next = await client.vehicles(id, scope, controller.signal, cursor);
        if (request === generation.current) setVehicles(old => ({...next, items: [...(old?.items ?? []), ...next.items]}));
      }
    } catch(e) { if (request === generation.current && !controller.signal.aborted) setError(errorMessage(e)); }
    finally { lock.current = false; if (request === generation.current) setBusy(false); }
  }
  async function linkRepair() {
    if (!linkTarget || lock.current) return;
    lock.current = true; setBusy(true); setError("");
    const request = generation.current;
    const key = intents.current[linkTarget.id] ??= crypto.randomUUID();
    try {
      await client.linkRepair(id, linkTarget.id, context.version, key);
      if (request === generation.current) { setLinkTarget(null); setRetry(n => n + 1); }
    } catch(e) { if (request === generation.current) {setError(errorMessage(e)); refreshContext();} }
    finally { lock.current = false; if (request === generation.current) setBusy(false); }
  }
  return <div className="crm-history">
    <div className="crm-tabs" role="group" aria-label="Repair scope">
      <ControlButton controlKind="action" type="button" aria-pressed={scope === "contact"} onClick={() => {setScope("contact"); setStatus("active");}}>Contact</ControlButton>
      <ControlButton controlKind="action" type="button" disabled={!context.fleet_available} aria-pressed={scope === "fleet"} onClick={() => {setScope("fleet"); setStatus("all");}}>Fleet history</ControlButton>
    </div>
    <div className="crm-heading"><h4>{scope === "contact" ? "Contact repairs" : "Fleet repairs"}</h4><InboxSelect label="Repair status" value={status} onChange={value => setStatus(value as RepairStatus)} options={[{value: "active", label: "Active"}, {value: "history", label: "History"}, {value: "all", label: "All"}]} /></div>
    {scope === "fleet" && <p className="crm-muted">All repairs for {context.customer?.company_name || "this customer"}.</p>}
    {error && <div role="alert" className="crm-error">{error}<ControlButton type="button" onClick={() => setRetry(n => n + 1)}>Retry</ControlButton></div>}
    {!repairs && !error && <p role="status" className="crm-muted"><Loader2 size={14} className="crm-spin" />Loading repairs…</p>}
    {repairs && !repairs.items.length && <p className="crm-muted">{scope === "contact" && !context.contact ? "Link a person to see their repairs." : scope === "contact" ? "No linked repairs in this view." : "No fleet repairs in this view."}</p>}
    {repairs?.items.map(order => <article className="crm-repair" key={order.id}>
      <a href={`/dashboard/repair-orders?selected=${encodeURIComponent(order.id)}`} onClick={beforeNavigate}><strong>{order.order_number}</strong><ArrowUpRight size={14} /><span className="sr-only">Open repair</span></a>
      <span className="crm-status">{statusLabel(order.status)}</span>
      {order.vehicle && <p><Truck size={13}/>{vehicleLabel(order.vehicle)}</p>}
      {order.description && <p className="crm-description">{order.description}</p>}
      <time dateTime={order.created_at}>{new Date(order.created_at).toLocaleDateString()}</time>
      {scope === "fleet" && context.contact && context.can_manage && <div>{order.linked_to_contact ? <span className="crm-linked">Linked to contact</span> : <ControlButton type="button" className="crm-text-button" disabled={busy} onClick={() => setLinkTarget(order)}><Link2 size={12}/>Link to contact</ControlButton>}</div>}
    </article>)}
    {repairs?.has_more && <ControlButton type="button" className="crm-more" disabled={busy} onClick={() => void more("repairs")}>Load more repairs</ControlButton>}
    <h4>{scope === "contact" ? "Serviced trucks" : "Fleet trucks"}</h4>
    {!vehicles && !error && <p className="crm-muted">Loading trucks…</p>}
    {vehicles && !vehicles.items.length && <p className="crm-muted">{scope === "contact" ? "No trucks from linked repairs yet." : "No fleet trucks."}</p>}
    {vehicles?.items.map(vehicle => <p className="crm-truck" key={vehicle.id}><Truck size={15}/>{vehicleLabel(vehicle)}</p>)}
    {vehicles?.has_more && <ControlButton type="button" className="crm-more" disabled={busy} onClick={() => void more("vehicles")}>Load more trucks</ControlButton>}
    <Dialog open={!!linkTarget} onClose={() => {if (!busy) setLinkTarget(null);}} className="crm-dialog"><div className="crm-backdrop"/><div className="crm-dialog-position"><DialogPanel className="crm-dialog-panel"><DialogTitle>Link repair to contact</DialogTitle><p>Link {linkTarget?.order_number} to {context.contact ? personLabel(context.contact) : "this contact"}?</p><p className="crm-muted">This adds the repair and its truck to this contact’s history.</p>{error && <p role="alert" className="crm-error">{error}</p>}<div className="crm-dialog-actions"><ControlButton type="button" disabled={busy} onClick={() => setLinkTarget(null)}>Cancel</ControlButton><ControlButton type="button" className="crm-primary" disabled={busy} onClick={() => void linkRepair()}>{busy ? "Linking…" : "Confirm link"}</ControlButton></div></DialogPanel></div></Dialog>
  </div>;
}

function LinkCustomerDialog({conversation, context, initialMode, close, saved, refresh, storageKey}: {storageKey: string; conversation: Conversation; context: CustomerContext; initialMode: "link" | "create"; close: () => void; saved: (value: CustomerContext) => void; refresh: () => void}) {
  const [pending] = useState(() => readPending(storageKey));
  const [mode, setMode] = useState(pending?.payload.action === "create_customer" ? "create" : initialMode);
  const [query, setQuery] = useState("");
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [customer, setCustomer] = useState<CustomerSummary | null>(context.customer);
  const [contacts, setContacts] = useState<ContactSummary[]>([]);
  const [contactsMore, setContactsMore] = useState(false);
  const [contactId, setContactId] = useState("");
  const [newPerson, setNewPerson] = useState(false);
  const [first, setFirst] = useState(""); const [last, setLast] = useState("");
  const [company, setCompany] = useState(""); const [email, setEmail] = useState(""); const [role, setRole] = useState("");
  const [phone, setPhone] = useState(conversation.channel === "sms" ? conversation.identityLabel : "");
  const [confirmed, setConfirmed] = useState(!!pending);
  const [error, setError] = useState(""); const [loading, setLoading] = useState(false); const [busy, setBusy] = useState(false);
  const alive = useRef(true); const lock = useRef(false);
  const intent = useRef<PendingContextIntent | null>(pending);
  const [uncertain, setUncertain] = useState(!!pending);
  useEffect(() => { alive.current = true; return () => {alive.current = false;}; }, []);
  useEffect(() => {
    if (mode !== "link" || (conversation.conversationKind !== "inquiry" && context.customer)) return;
    const controller = new AbortController(); setLoading(true); setError("");
    const timer = setTimeout(() => { void client.customers(conversation.id, query, controller.signal).then(result => {if (!controller.signal.aborted) setCustomers(result.items);}).catch(e => {if (!controller.signal.aborted) setError(errorMessage(e));}).finally(() => {if (!controller.signal.aborted) setLoading(false);}); }, 200);
    return () => {clearTimeout(timer); controller.abort();};
  }, [query, mode, conversation.id, conversation.conversationKind, context.customer]);
  useEffect(() => {
    setContactId(""); setContacts([]); if (!pending) setConfirmed(false); setContactsMore(false);
    if (!customer || mode !== "link") return;
    const controller = new AbortController(); setLoading(true); setError("");
    void client.contacts(conversation.id, customer.id, controller.signal).then(result => {if (!controller.signal.aborted) {setContacts(result.items); setContactsMore(result.has_more);}}).catch(e => {if (!controller.signal.aborted) setError(errorMessage(e));}).finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [conversation.id, customer, mode, pending]);
  const createPerson = mode === "create" || newPerson;
  const ready = !busy && (uncertain || (confirmed && (mode === "create" ? !!company.trim() && !!email.trim() && !!first.trim() && !!last.trim() : !!customer && (newPerson ? !!(first.trim() || last.trim()) : !!contactId))));
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (!ready || lock.current) return;
    if (!uncertain) {
    const person = {first_name: first.trim(), last_name: last.trim(), role: role.trim(), email: email.trim() || null, phone: phone.trim() || null};
    const payload: ContextMutation = mode === "create" ? {action: "create_customer", expected_version: context.version, customer: {company_name: company.trim(), first_name: first.trim(), last_name: last.trim(), email: email.trim(), phone: phone.trim() || null}, contact: person} : newPerson ? {action: "create_contact", expected_version: context.version, customer_id: customer!.id, contact: person} : {action: "link", expected_version: context.version, customer_id: customer!.id, contact_id: contactId};
    const serialized = JSON.stringify(payload);
    if (JSON.stringify(intent.current?.payload) !== serialized) intent.current = {payload, key: crypto.randomUUID()};
    }
    // Persist before dispatch so reopening after an uncertain response replays the same operation.
    try { sessionStorage.setItem(storageKey, JSON.stringify(intent.current)); }
    catch {setError("Browser storage is unavailable. Restore storage access before saving safely."); return;}
    lock.current = true; setBusy(true); setError("");
    try { const result = await client.save(conversation.id, intent.current!.payload, intent.current!.key); sessionStorage.removeItem(storageKey); if (alive.current) saved(result); }
    catch(e) {if (alive.current) {
      const status = (e as {response?: {status?: number}})?.response?.status;
      const unknown = !status || status >= 500;
      setUncertain(unknown);
      setError(unknown ? "Could not confirm the save. Retry this same request before making another change." : errorMessage(e));
      if (!unknown) {sessionStorage.removeItem(storageKey); intent.current = null; refresh(); setConfirmed(false);}
    }}
    finally {lock.current = false; if (alive.current) setBusy(false);}
  }
  return <Dialog open onClose={() => {if (!busy) close();}} className="crm-dialog"><div className="crm-backdrop"/><div className="crm-dialog-position"><DialogPanel className="crm-dialog-panel">
    <div className="crm-heading"><DialogTitle>{mode === "create" ? "Add customer" : "Link customer"}</DialogTitle><ControlButton controlKind="icon" type="button" aria-label="Close customer linking" disabled={busy} onClick={close}><X size={18}/></ControlButton></div>
    {conversation.conversationKind === "inquiry" && <div className="crm-tabs"><ControlButton controlKind="action" type="button" disabled={busy || uncertain} aria-pressed={mode === "link"} onClick={() => {setMode("link"); setConfirmed(false);}}>Existing customer</ControlButton><ControlButton controlKind="action" type="button" disabled={busy || uncertain} aria-pressed={mode === "create"} onClick={() => {setMode("create"); setConfirmed(false);}}>New customer</ControlButton></div>}
    <form noValidate={uncertain} onSubmit={event => void submit(event)}>
      {uncertain && <p role="status" className="crm-muted">A previous save needs confirmation. Retry reuses that exact request.</p>}
      <fieldset disabled={busy || uncertain} onChange={() => setConfirmed(false)}>
        {mode === "link" && <>
          {conversation.conversationKind === "inquiry" && <><label>Find customer<ControlInput value={query} maxLength={200} onChange={e => setQuery(e.target.value)} placeholder="Company or customer name"/></label><div className="crm-options" aria-label="Customer results">{customers.map(item => <ControlButton controlKind="action" type="button" key={item.id} aria-pressed={customer?.id === item.id} onClick={() => {setCustomer(item); setNewPerson(false); setConfirmed(false);}}>{item.company_name}<small>{item.display_name}</small></ControlButton>)}</div></>}
          {customer && <><p className="crm-chosen">Customer: <strong>{customer.company_name || customer.display_name}</strong></p><div className="crm-person-field"><span>Person</span><InboxSelect label="Person" disabled={busy || uncertain} value={newPerson ? "new" : contactId} onChange={value => {setConfirmed(false); setNewPerson(value === "new"); setContactId(value === "new" ? "" : value);}} options={[{value: "", label: "Choose contact"}, ...contacts.map(person => ({value: person.id, label: `${personLabel(person)}${person.role ? ` · ${person.role}` : ""}`})), {value: "new", label: "Add a person"}]} /></div>{contactsMore && <p className="crm-muted">Showing the first 100 contacts. Manage additional contacts in Customers.</p>}</>}
        </>}
        {mode === "create" && <label>Company<ControlInput required maxLength={255} value={company} onChange={e => setCompany(e.target.value)}/></label>}
        {createPerson && <><div className="crm-form-row"><label>First name<ControlInput required={mode === "create"} maxLength={100} value={first} onChange={e => setFirst(e.target.value)}/></label><label>Last name<ControlInput required={mode === "create"} maxLength={100} value={last} onChange={e => setLast(e.target.value)}/></label></div><label>Role<ControlInput maxLength={100} value={role} onChange={e => setRole(e.target.value)} placeholder="Driver, dispatcher, owner…"/></label><label>Email<ControlInput type="email" required={mode === "create"} maxLength={255} value={email} onChange={e => setEmail(e.target.value)}/></label><label>Phone<ControlInput type="tel" maxLength={30} value={phone} onChange={e => setPhone(e.target.value)}/></label><p className="crm-muted">Phone is an editable suggestion, not verified ownership.</p></>}
      </fieldset>
      {loading && <p role="status" className="crm-muted">Loading options…</p>}
      {error && <p role="alert" className="crm-error">{error}</p>}
      <label className="crm-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)}/>I confirm this customer and person belong with this conversation.</label>
      <p className="crm-muted">Reply number, drafts and SMS consent stay unchanged.</p>
      <div className="crm-dialog-actions"><ControlButton type="button" disabled={busy} onClick={close}>Cancel</ControlButton><ControlButton type="submit" className="crm-primary" disabled={!ready}>{busy ? "Saving…" : uncertain ? "Retry save" : mode === "create" ? "Create and link" : "Confirm link"}</ControlButton></div>
    </form>
  </DialogPanel></div></Dialog>;
}
