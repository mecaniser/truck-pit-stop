import { describe, expect, it, vi } from 'vitest';
import api from '../../lib/api';
import { inboxApi, mapConversation, type WireConversation } from './api';
vi.mock('../../lib/api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));
describe('inbox wire adapter', () => {
  it('patches explicit sender with optimistic version and maps the returned sender options', async () => {
    vi.mocked(api.patch).mockResolvedValue({ data: { id: 'thread', tenant_id: 'tenant', messages: [], send_policy: { can_send: true, reason: null }, context: { selected_sender_id: 'binding', sms_sender_options: [{ id: 'binding', provider: 'callrail', sender_number: '+19809071896', enabled: false }] }, version: 8 } });
    const row = mapConversation({ id: 'thread', tenant_id: 'tenant', messages: [], send_policy: { can_send: true, reason: null }, context: {}, version: 7 } as unknown as WireConversation);
    const updated = await inboxApi.changeSender(row, 'binding');
    expect(api.patch).toHaveBeenCalledWith('/communications/conversations/thread/sender', { expected_version: 7, binding_id: 'binding' });
    expect(updated.version).toBe(8);
    expect(updated.context).toMatchObject({ selectedSenderId: 'binding', smsSenderOptions: [{ id: 'binding', provider: 'callrail', senderNumber: '+19809071896', enabled: false }] });
    await inboxApi.changeSender(updated, null);
    expect(api.patch).toHaveBeenLastCalledWith('/communications/conversations/thread/sender', { expected_version: 8, binding_id: null });
  });
  it('maps explicit provider and sender metadata with provider send policy', () => {
    const row = mapConversation({ id: 'thread', tenant_id: 'tenant', messages: [], send_policy: { can_send: true, reason: null, max_length: 140 }, context: { sms_provider: 'callrail', sender_number: '+19809071896', enabled: false }, version: 1 } as unknown as WireConversation);
    expect(row.context).toMatchObject({ smsProvider: 'callrail', senderNumber: '+19809071896' });
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
