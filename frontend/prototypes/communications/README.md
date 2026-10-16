# Communication prototype

Isolated fixture surface for DB-COMMS-001B. Not imported by the production app.

From `frontend/`:

```sh
npm ci
npx vite --config prototypes/communications/vite.config.ts
```

Open http://127.0.0.1:5186/. This config has no API proxy. Do not substitute a
production API target. Uses installed project React/Lucide dependencies.

Try contact/message/order search, channel filters, open/unread/mine/resolved,
assignment, resolve/reopen, saved replies, hide/show service updates and failure
details. SMS Send preview adds a local queued sample only. WhatsApp/Telegram and
opted-out recipients remain blocked. Contact/channel switching preserves separate
drafts in memory; reload resets all data. On a phone, open a conversation and use
Back to conversations; the info button opens the context panel.

```sh
npx vitest run src/features/communications/communications.test.tsx
npx tsc --noEmit
npx eslint src/features/communications --ext ts,tsx --max-warnings 0
npx vite build --config prototypes/communications/vite.config.ts
```

The standalone build goes to ignored `frontend/dist-communications/`.
Shared backend contracts, migration/outbox and provider integration are proposed
in `docs/communications/SHARED_INBOX_CONTRACT.md`, not implemented by this preview.
SMS callback correction is independently reviewed in draft PR559.
