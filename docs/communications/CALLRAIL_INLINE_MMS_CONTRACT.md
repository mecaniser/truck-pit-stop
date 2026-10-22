# DB-COMMS-017: authenticated incoming MMS image viewing

Status: implementation contract, 2026-10-22. Accountable owner: Backend & Integrations; contract owner: Architecture & API Contracts. High-risk lane because new sensitive-media retrieval crosses staff authorization, tenant and provider-credential boundaries. Independent QA and Security gates required.

## Outcome and approach

Staff see incoming MMS images inside the existing conversation. Preserve the current reply route, received time, caption, deduplication, consent behavior and notifications. All three SMS automation/routing/recovery flags remain false. No outbound MMS, provider configuration, forwarding changes, OCR, image-content extraction or automatic processing.

Use lazy authenticated retrieval, not ingestion or permanent image storage. Existing messages already retain account, binding, provider message/conversation identities and aliases; existing attachment receipt bodies identify candidates without migrations. `communications_service.message_json` currently returns text only; `CommunicationsPreview.tsx` renders the shared message bubbles. Existing upload data-URI patterns are unsuitable for provider media: they trust declared types and would persist bytes. Use Pillow already installed, following the stronger validation approach in `external_service_receipt.py`.

Provider evidence: [CallRail API documentation](https://apidocs.callrail.com/#retrieving-a-single-text-conversation) documents conversation retrieval with paginated messages, message identity/type and media URLs. Media retrieval requires the API key; returned URLs must not be stored and should be refreshed when needed. This contract relies on fresh conversation retrieval and fails visibly if the provider no longer retains the media. It does not promise indefinite retention.

## Additive inbox contract

Existing message JSON adds `has_attachments: boolean`, default false in frontend compatibility mapping. True only for incoming CallRail messages whose body ends with the exact existing attachment receipt notice and which retain provider binding/account/conversation/message identity. No upstream call during inbox serialization. This is a candidate indicator, not a promise that the image remains available. Do not remove or rewrite persisted caption/notice text.

`GET /api/v1/communications/conversations/{conversation_id}/messages/{message_id}/attachments`

Authenticated manifest response:

```json
{"items":[{"index":0,"kind":"image"}]}
```

Indices are provider attachment slots, integer 0 through 9. The browser receives neither provider identities nor URLs. Empty `items` means no retained media. Manifest discovery must not download image bytes. The frontend constructs local content routes from conversation/message IDs and index, never from provider strings.

`GET /api/v1/communications/conversations/{conversation_id}/messages/{message_id}/attachments/{index}`

Returns bounded, decoded and re-encoded raster bytes with authoritative `Content-Type: image/jpeg` or `image/png`. No redirect, JSON URL, public bucket, data URI or credential-bearing query. Headers on success and failures: `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`. Content-Disposition uses an application-generated inline filename. Do not reuse upstream headers.

Errors use existing `{detail:{code,message}}`: 404 `attachment_not_found` for missing/foreign/deleted message, inconsistent binding/provenance or absent index; 403 existing messaging-access denial; 422 `attachment_unsupported` for unsupported/invalid raster; 413 `attachment_too_large`; 502 `attachment_unavailable` for sanitized provider rejection/invalid response/redirect; 504 `attachment_timeout`. No upstream response body, URL, phone, credential or image contents in errors or logs. Authentication failures follow existing dependency behavior.

## Authorization and identity

On BOTH routes call the same current-user dependency, `authorize` and `thread_for` as existing inbox detail. Select the nondeleted message by tenant + thread + ID; require inbound CallRail and matching nondeleted enabled binding belonging to that tenant/account. Resolve a nondeleted conversation mapping for that message's stored binding and thread, not whichever binding is now selected for sending. Validate mapping/customer/inquiry identity; reading remains allowed for opted-out contacts. Do not call sending policy or require consent to view a received image. Fail closed on changed contact identity or disabled binding; do not mutate routing to repair it.

Retrieve only the stored provider conversation, using the binding's dedicated credential reference. Validate returned conversation ID, company and customer contact against stored context. Identify exactly one provider message using trusted stored numeric/resource aliases; match incoming direction, original timestamp and caption. When matching through a media resource ID, extract it only from an already validated API path and require an exact stored SCI identity. Never match by timestamp or body alone. Never infer a historical receiving number from a conversation's current tracker. The local message's binding/from/to provenance remains authoritative. Support the pre-existing receipt without replay, migration or backfill.

## Network and decoding boundary

Construct conversation request URLs on literal `https://api.callrail.com`; validate account/conversation identifiers before path assembly. Stream JSON with a 2 MiB cap; paginate at most 10 pages of 100 messages, reconstruct page requests locally, and reject inconsistent pagination. Never follow provider pagination URLs. Stop once the unique message is established; fail closed if ambiguity is observed. Cap media slots at 10 and validate their full list before exposing indices.

Every media URL must parse to HTTPS, exact host `api.callrail.com`, default port, no userinfo, fragment or query, and exact `/v3/a/{bound_account}/text-messages/{trusted_SCI}/media/{index}`. Require media SCI to agree with stored resource alias when present. Reject encoded path tricks and mismatched account/index. This is not an arbitrary URL proxy. Provider credentials are sent only to that exact origin. Set `follow_redirects=False` and reject all 3xx, including same-host redirects; do not forward credentials or expose Location. If real provider operation requires a CDN redirect, return failure and revisit this contract with an explicit origin policy; never widen hosts opportunistically.

Use explicit connect/read/pool timeouts and a 20 second overall request budget. A single manifest/content operation has bounded provider requests, no retries or background jobs. For bytes, stream with a hard 5 MiB input limit regardless of Content-Length, including chunked/encoded bodies. Check declared content type and actual raster decode agree: JPEG, PNG, WebP or GIF input only; reject SVG/HTML/PDF/HEIC, malformed files, decompression bombs, dimensions above 8192 per side or 25 million pixels. Decode only frame zero; output a static PNG/JPEG, stripping EXIF/metadata and appended data. Cap encoded output at 10 MiB. Run decoding in a worker thread; no mutable global Pillow limit changes. Do not persist or log bytes, URLs, manifest provider response or keys; no shared media cache.

## Frontend lifecycle

Add optional `hasAttachments` to the shared message model. Render an image area only for candidates in the selected conversation. Fetch manifest and blobs through existing authenticated API client with `responseType: 'blob'` and AbortSignal; never put bearer tokens in image URLs. Load at most two blobs concurrently. Use object URLs for `<img>` and revoke them on replacement, unmount, thread/session change and stale completion. Include auth session epoch in lifecycle isolation; prior-shop responses must never display after account switch. Clear images immediately on session change.

Show loading, inline constrained image thumbnails (`object-fit: contain`) and concise unavailable/unsupported state with a manual Retry action. No automatic infinite retries. Use descriptive generic alt text, never inferred image contents. Preserve caption/timestamp and compose draft. The provider attachment notice may be hidden only in the rendered bubble once media is available; keep it/fallback when unavailable. No sender selector, reply-policy change, outbound upload or consent toggle. Existing plain SMS and non-CallRail bubbles are unchanged. Responsive layout must fit narrow viewports.

## Ownership and acceptance tests

Backend owns new `backend/app/services/callrail_media.py`, attachment endpoints in `backend/app/api/v1/endpoints/communications.py`, additive serialization in `backend/app/services/communications_service.py`, and `backend/tests/test_callrail_media.py`. Avoid changes to ingest/send/routing services unless contract revision proves necessary.

Frontend owns `frontend/src/features/communications/{api.ts,model.ts,CommunicationsPreview.tsx,communications.css}` and a dedicated authenticated-media component/test as needed; extend API/component tests. Parent coordinates board and runtime fixture. This document is contract-owner-only.

Backend tests use mocked HTTP and synthetic raster bytes only: legacy image-only and captioned receipt; multiple media; numeric and SCI aliases; exact timestamp/caption; ambiguous or absent match; pagination bound; disabled/deleted/foreign tenant/customer/binding/message; opted-out viewing; no credential lookup or provider call before authorization; account/SCI/path/index mismatch; userinfo/query/fragment/port/encoded URL rejection; all redirects; absent/wrong declared type; HTML/SVG/malformed raster; oversized/chunked/compressed bodies; dimensions/pixel/decompression limits; animated input static output; metadata stripping; timeouts; sanitized errors and no-store headers. Assert GETs do not change rows, timestamps, body, unread state, routes, send operations or flags.

Frontend tests: authenticated blob request; loading/image/multiple/empty/error/retry states; missing additive field; caption/time preserved; no provider URL/token in DOM; object URL revocation on unmount, retry, late response, conversation/tenant/session switch; abort; concurrency bound; unchanged draft, automatic reply number and plain SMS rendering. Synthetic signed-in runtime acceptance covers desktop and compact layouts without provider sends or real image inspection. Independent security/QA review then protected CI. Merge/deploy authority remains a separate release decision; do not claim live support before deployed-source and signed-in acceptance evidence.
