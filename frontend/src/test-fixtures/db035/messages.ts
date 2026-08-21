import { deepFreeze } from './appearance'
export const messagesFixture = deepFreeze({
  threads: [{ id: 'thread-1', customer: 'NorthStar Logistics', unread: 2 }],
  messages: [{ id: 'message-1', direction: 'outbound', body: 'Your repair order is ready for review.', status: 'delivered' }],
})
export const emptyMessagesFixture = deepFreeze({ threads: [], messages: [] })
