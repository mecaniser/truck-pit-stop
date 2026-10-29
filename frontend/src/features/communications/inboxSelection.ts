import type { Conversation } from "./model";
const storageKey = (tenant: string, user: string) => `inbox-selection:${tenant}:${user}`;
export function restoredConversation(rows: Conversation[], tenant: string, user: string): Conversation | undefined {
  try { const id = sessionStorage.getItem(storageKey(tenant, user)); return rows.find(row => row.id === id) ?? rows[0]; }
  catch { return rows[0]; }
}
export function rememberConversation(id: string, tenant: string, user: string) {
  try { sessionStorage.setItem(storageKey(tenant, user), id); } catch { /* Storage can be unavailable in private sessions. */ }
}
