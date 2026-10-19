import { describe, expect, it, vi } from 'vitest';
import api from '../../lib/api';
import { inboxApi, mapConversation, type WireConversation } from './api';
vi.mock('../../lib/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
describe('inbox wire adapter', () => {
  it('maps explicit provider and sender metadata with provider send policy', () => {
    const row = mapConversation({ id: 'thread', tenant_id: 'tenant', messages: [], send_policy: { can_send: true, reason: null, max_length: 140 }, context: { sms_provider: 'callrail', sender_number: '+19809071896' }, version: 1 } as unknown as WireConversation);
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
