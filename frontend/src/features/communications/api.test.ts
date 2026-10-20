import { describe, expect, it, vi } from 'vitest';
import api from '../../lib/api';
import { inboxApi, mapConversation, type WireConversation } from './api';
vi.mock('../../lib/api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));
describe('inbox wire adapter', () => {
  it('maps a null-customer inquiry without company guesses and retains its pinned sender contract', () => {
    const row = mapConversation({ id: 'inquiry', tenant_id: 'tenant', conversation_kind: 'inquiry', customer_id: null, customer_name: 'Unavailable customer', company: 'Unproven company', messages: [], send_policy: { can_send: true, reason: null, max_length: 140 }, context: { sms_provider: 'callrail', sender_number: '+15005550001', sender_selection_allowed: false }, version: 2 } as unknown as WireConversation);
    expect(row).toMatchObject({ conversationKind: 'inquiry', customerId: null, customerName: 'New inquiry', company: null, context: { smsProvider: 'callrail', senderNumber: '+15005550001' } });
  });
  it('maps derived sender modes while discarding legacy sender inventory', () => {
    for (const mode of ['reply', 'initiation', 'unavailable'] as const) {
      const row = mapConversation({ id: 'thread', tenant_id: 'tenant', messages: [], send_policy: { can_send: mode !== 'unavailable', reason: null }, context: { sender_mode: mode, sender_route_reason: 'reply_route_unavailable', sender_selection_allowed: true, sms_sender_options: [{ id: 'legacy', provider: 'callrail', sender_number: '+15005550001' }] }, version: 8 } as unknown as WireConversation);
      expect(row.context).toMatchObject({ senderMode: mode, senderRouteReason: 'reply_route_unavailable' });
      expect(row.context).not.toHaveProperty('smsSenderOptions');
      expect(inboxApi).not.toHaveProperty('changeSender');
    }
    expect(api.patch).not.toHaveBeenCalled();
  });
  it('maps explicit provider and sender metadata with provider send policy', () => {
    const row = mapConversation({ id: 'thread', tenant_id: 'tenant', messages: [], send_policy: { can_send: true, reason: null, max_length: 140 }, context: { sms_provider: 'callrail', sender_number: '+15005550001', enabled: false }, version: 1 } as unknown as WireConversation);
    expect(row.context).toMatchObject({ smsProvider: 'callrail', senderNumber: '+15005550001' });
    expect(row.sendPolicy.maxLength).toBe(140);
  });
  it('consumes every conversation page and sends search to the server', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: { items: [], has_more: true, next_cursor: 'next-page' } }).mockResolvedValueOnce({ data: { items: [], has_more: false, next_cursor: null } });
    expect(await inboxApi.list('older message')).toEqual([]);
    expect(api.get).toHaveBeenNthCalledWith(2, '/communications/conversations', { params: { limit: 100, search: 'older message', cursor: 'next-page' } });
  });
  it('maps missing repair context without synthetic defaults', () => {
    const row = mapConversation({ id: 'thread', tenant_id: 'tenant', messages: [], send_policy: { can_send: false, reason: 'identity_unverified' }, context: {}, version: 9 } as unknown as WireConversation);
    expect(row.context.repairOrderLabel).toBeUndefined(); expect(row.version).toBe(9); expect(row.sendPolicy.canSend).toBe(false);
  });
});
