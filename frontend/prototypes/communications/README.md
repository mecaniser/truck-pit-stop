# Connected communication prototype

DB-COMMS-002 standalone inbox surface; not imported by the production application.

From `frontend/`:

```sh
npx vite --config prototypes/communications/vite.config.ts
```

Open http://127.0.0.1:5186/. The `/api` proxy targets the isolated backend on
127.0.0.1:8006. Follow the repository runtime instructions before starting services;
do not replace this target with production. Sign in with a seeded synthetic staff
account using the normal authentication endpoint. The banner reports delivery mode
from the backend; simulated SMS does not prove real carrier delivery.

Conversation history, assignment, resolution, read state and send operations use
persisted backend records. Search traverses server message history and the client
consumes conversation pagination. Older messages load explicitly. Delivery states
refresh from the backend. WhatsApp and Telegram remain unavailable.

Drafts persist per tenant, user, conversation, channel, sender and contact identity.
Before sending, the browser persists the original idempotency key and payload.
An unconfirmed request blocks a new send; “Check original send” submits the same
intent. Recovery survives reload and never silently changes the key or body.
This protection applies to the new communications endpoint, not legacy sends.

The fixture-only component remains available to unit tests without API calls.

```sh
npx vitest run src/features/communications
npx tsc --noEmit
npx eslint src/features/communications --max-warnings 0
npx vite build --config prototypes/communications/vite.config.ts
```

The standalone build goes to ignored `frontend/dist-communications/`.
See `docs/communications/IMPLEMENTATION_CONTRACT.md` for backend guarantees and
remaining rollout boundaries. Deployment and real SMS acceptance are separate gates.
