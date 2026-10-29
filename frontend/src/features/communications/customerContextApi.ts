import api from "../../lib/api";

export interface CustomerSummary { id: string; company_name: string; display_name: string }
export interface ContactSummary { id: string; first_name: string; last_name: string; role: string | null; phone: string | null; email: string | null }
export interface CustomerContext {
  version: number; link_state: "unlinked" | "linked" | "unavailable"; can_manage: boolean;
  customer: CustomerSummary | null; contact: ContactSummary | null; default_scope: "contact"; fleet_available: boolean;
}
export interface VehicleSummary { id: string; unit_number: string | null; make: string | null; model: string | null; year: number | null }
export interface RepairSummary { id: string; order_number: string; status: string; created_at: string; description: string | null; vehicle: VehicleSummary | null; linked_to_contact: boolean }
export interface ContextPage<T> { items: T[]; has_more: boolean; next_cursor: string | null }
export type RepairScope = "contact" | "fleet";
export type RepairStatus = "active" | "history" | "all";
export interface ContactInput { first_name: string; last_name: string; role: string; phone: string | null; email: string | null }
export type ContextMutation = { expected_version: number } & (
  { action: "link"; customer_id: string; contact_id: string } |
  { action: "create_contact"; customer_id: string; contact: ContactInput } |
  { action: "create_customer"; customer: { company_name: string; first_name: string; last_name: string; email: string; phone: string | null }; contact: ContactInput }
);
const root = (id: string) => `/communications/conversations/${encodeURIComponent(id)}`;
export const customerContextApi = {
  context: async (id: string, signal: AbortSignal) => (await api.get<CustomerContext>(`${root(id)}/customer-context`, { signal })).data,
  customers: async (id: string, q: string, signal: AbortSignal) => (await api.get<{items: CustomerSummary[]}>(`${root(id)}/customer-options`, { params: {q, limit: 20}, signal })).data,
  contacts: async (id: string, customer: string, signal: AbortSignal) => (await api.get<{items: ContactSummary[]; has_more: boolean}>(`${root(id)}/customer-options/${encodeURIComponent(customer)}/contacts`, { signal })).data,
  save: async (id: string, payload: ContextMutation, key: string) => (await api.put<CustomerContext>(`${root(id)}/customer-context`, payload, { headers: {"Idempotency-Key": key} })).data,
  repairs: async (id: string, scope: RepairScope, status: RepairStatus, signal: AbortSignal, cursor?: string) => (await api.get<ContextPage<RepairSummary>>(`${root(id)}/repairs`, { params: {scope, status, limit: 10, cursor}, signal })).data,
  vehicles: async (id: string, scope: RepairScope, signal: AbortSignal, cursor?: string) => (await api.get<ContextPage<VehicleSummary>>(`${root(id)}/vehicles`, { params: {scope, limit: 10, cursor}, signal })).data,
  linkRepair: async (id: string, repair: string, version: number, key: string) => (await api.put<{linked: boolean}>(`${root(id)}/repairs/${encodeURIComponent(repair)}/contact-link`, {expected_version: version}, {headers: {"Idempotency-Key": key}})).data,
};
