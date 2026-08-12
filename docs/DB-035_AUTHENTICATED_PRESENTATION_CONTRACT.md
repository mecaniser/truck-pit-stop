# DB-035 Authenticated Presentation Contract v1

Status: Architecture GO for implementation

Board item: DB-035

Contract owner: Architecture & API Contracts
Implementation owners: Backend & Integrations, then Frontend & UX

## 1. Decision and boundaries

DB-035 translates the source-grounded DieselBridge landing design language into
the authenticated staff application. It is presentation and preference
infrastructure only. It must not change routes, permissions, tenant boundaries,
API business contracts, repair-order behavior, messaging behavior, financial or
operational semantics, payments, WebSocket behavior, or resulting domain state.

The rollout covers authenticated garage-staff Dashboard, Customers, Repair
Orders, Messages, My Shop, and Profile/Settings. It excludes public landing and
authentication pages, quote and invoice links, customer and driver portals, the
standalone fleet and mechanic applications, and platform-admin screens.

Both presentations use one router, route table, navigation model, API client,
query cache, permission system, mutation implementation, WebSocket connection,
and domain state. Presentation adapters may receive an existing view model and
callbacks; they must not call APIs directly or own duplicate business state.

## 2. Source map

`frontend/src/components/layout/DashboardLayout.tsx` owns the staff shell,
navigation, mobile navigation, product/tenant identity, and nested routes.
`frontend/src/App.tsx` owns the single `ThemeProvider`, router, authenticated
route guard, and shared toaster. No second router or presentation-specific route
tree is permitted.

| Surface | Existing route | Existing component | Existing icon |
|---|---|---|---|
| Dashboard | `/dashboard` | `DashboardHome` | Lucide `Home` |
| Customers | `/dashboard/customers` | `CustomersPage` | Lucide `Users` |
| Repair Orders | `/dashboard/repair-orders` | `RepairOrdersPage` | Lucide `ClipboardList` |
| Messages | `/dashboard/messages` | `MessagesInboxPage` | Lucide `MessageSquare` |
| My Shop | `/dashboard/garage/*` | `MyGaragePage` | Lucide `Building2` |
| Profile/Settings | `/dashboard/settings` | `UnifiedSettingsPage` | Existing profile monogram |

Messages retains its current role/grant and tenant feature-switch checks. My
Shop retains its current nested mechanics, services, labor-book-time, inventory,
suppliers, reviews, review-settings, and analytics routes.

`frontend/src/contexts/ThemeContext.tsx` currently owns local-only accent, font,
font-size, and notification choices. `frontend/src/index.css` currently exposes
only partial accent/font roots and must become the shared layered token source.
`frontend/src/features/dashboard/UnifiedSettingsPage.tsx` remains the staff
Appearance UI. `frontend/src/stores/authStore.ts` supplies the authenticated
session identity and epoch used to isolate caches.

`backend/app/db/models/user.py` currently has no presentation preference state.
The legacy and WorkOS `GET /api/v1/auth/me` implementations must use the same
bootstrap response builder and contract.

## 3. Product identity

DieselBridge is always the primary authenticated product identity. The shell
shows the DieselBridge logo/wordmark and accessible product name first. The
tenant logo and shop name are smaller, subordinate workspace context; tenant
state/location is optional tertiary context.

Tenant branding cannot replace the DieselBridge accessible name, document or
browser identity, primary shell logo, navigation identity, loading identity, or
error identity. The current tenant-first shell rendering must be corrected while
retaining `useTenantBranding()` as the shop-context source.

## 4. Presentation rollout

### 4.1 Values and precedence

The only presentation values are `legacy` and `new`. The backend resolves the
effective value in this exact order:

1. Global emergency `force_legacy`.
2. User override for the active user and active tenant.
3. Active tenant default.
4. Product default `legacy`.

Missing, malformed, unavailable, or unsupported rollout data resolves to
`legacy`. Users cannot change rollout assignment from Appearance settings.
Product & Delivery and Release & Reliability own rollout; Appearance controls
only personalization inside the resolved presentation.

### 4.2 Storage and administration

Add an additive tenant field `staff_presentation_default`, non-null with server
default `legacy`. Store a nullable user/tenant presentation override separately
from Appearance preferences so rollout operations cannot be changed by the user.
Add global emergency configuration
`AUTHENTICATED_PRESENTATION_FORCE_LEGACY`.

Super-admin-only rollout endpoints:

```http
PUT /api/v1/admin/presentation-rollout/tenants/{tenant_id}
PUT /api/v1/admin/presentation-rollout/tenants/{tenant_id}/users/{user_id}
```

Tenant request:

```json
{"schema_version":1,"presentation":"legacy"}
```

User request, including override removal:

```json
{"schema_version":1,"presentation_override":"new"}
```

```json
{"schema_version":1,"presentation_override":null}
```

The target user must be active and belong to the target tenant. Foreign,
missing, deleted, or mismatched target pairs return the same generic `404`.
Non-super-admin callers return `403` without target-existence disclosure.

### 4.3 Rollback, refresh, observability, and removal

A tenant/user rollback requires no frontend deployment. It applies at bootstrap,
route transition, focus refresh, or a bounded background refresh, with a maximum
open-tab delay of 60 seconds. Global `force_legacy` dominates every stored value.
Rollback changes presentation only and does not delete Appearance preferences.

Record counters for resolved legacy/new source, bootstrap fallback, preference
GET/PUT/DELETE outcomes, revision conflicts, legacy migration outcomes, matching
or rejected cache use, and render errors by presentation/surface. Do not record
preference payloads, logos, emails, tenant names, or free text.

Legacy and new presentations remain compatible for at least two production
releases and 30 days after the first production cohort. Removal requires a
separate board transition and 14 consecutive days without a legacy rollback.
The cleanup removes presentation branching and legacy-only presentation code,
but not the Appearance preference API.

## 5. Appearance persistence and migration

### 5.1 Dedicated table

User-scoped server state is authoritative. Add an additive migration for:

```text
user_appearance_preferences
- id UUID primary key
- tenant_id UUID not null
- user_id UUID not null
- schema_version integer not null default 1
- revision integer not null default 1
- appearance JSONB not null
- legacy_migration_status string not null
- legacy_migrated_at timestamptz null
- created_at / updated_at / deleted_at
- unique active (tenant_id, user_id)
```

All reads and writes use both authenticated `current_user.id` and
`current_user.tenant_id`; request bodies never accept either identifier. The
migration is additive and must preserve a single Alembic head.

### 5.2 Exact localStorage inventory

Only these existing keys are Appearance inputs:

| Legacy key | Existing valid values | v1 target |
|---|---|---|
| `theme-accent` | `cyan`, `indigo`, `emerald`, `rose`, `amber` | `appearance.accent` |
| `theme-font-family` | `geist`, `dm-sans`, `jakarta`, `inter` | `appearance.font_family` |
| `theme-font-size` | `compact`, `default`, `comfortable`, `large` | Mapping below |
| `theme-notification-position` | `top`, `bottom`, `center-top` | `top_right`, `bottom_right`, `top_center` |

Legacy size mapping:

| Legacy value | `font_size` | `density` |
|---|---|---|
| `compact` | `small` | `compact` |
| `default` | `default` | `default` |
| `comfortable` | `large` | `comfortable` |
| `large` | `large` | `large` |

`auth-storage`, `tps_view_prefs`, fleet layout/rail state, timer-panel state,
suggestion-toast state, and customer-portal payment/notification preferences are
not Appearance keys and must not be migrated.

### 5.3 Exactly-once migration and old-client compatibility

`legacy_migration_status` is `pending` or `complete`.

1. An authenticated v1 client receiving `pending` reads only the four keys.
2. It validates and maps each field; invalid values are ignored field-by-field.
3. It sends one revision-checked update with
   `migration_source: "legacy_local_v1"`.
4. The server atomically stores the preference and marks migration complete.
5. If no valid values exist, effective defaults are committed and migration is
   still marked complete.
6. A completed migration is never imported again.

During the compatibility window, new clients mirror successfully committed
compatible values back to the four legacy keys. Old clients may continue using
those values locally, but cannot overwrite server state because v1 never
re-imports after completion. Failed API writes neither mark migration complete
nor delete legacy values.

After the compatibility window, the new client stops mirroring, removes the four
keys following a successful authenticated v1 bootstrap, and a later cleanup
removes legacy storage listeners and setters.

## 6. Versioned API

### 6.1 Bootstrap

Both legacy and WorkOS authenticated `me` responses add the same optional
`presentation` object:

```json
{
  "presentation": {
    "schema_version": 1,
    "resolved_variant": "new",
    "source": "user_override",
    "appearance": {
      "accent": "cyan",
      "font_family": "geist",
      "font_size": "default",
      "density": "default",
      "notification_position": "bottom_right",
      "mode": "dark"
    },
    "defaults": {
      "accent": "cyan",
      "font_family": "geist",
      "font_size": "default",
      "density": "default",
      "notification_position": "bottom_right",
      "mode": "dark"
    },
    "revision": 4,
    "legacy_migration_status": "complete",
    "updated_at": "2026-08-11T15:30:00Z"
  }
}
```

`source` is `global_force_legacy`, `user_override`, `tenant_default`, or
`product_default`. Old clients ignore the additive field.

### 6.2 Read, apply, and reset

```http
GET /api/v1/auth/me/appearance
PUT /api/v1/auth/me/appearance
DELETE /api/v1/auth/me/appearance
```

PUT request:

```json
{
  "schema_version": 1,
  "base_revision": 4,
  "appearance": {
    "accent": "indigo",
    "font_family": "inter",
    "font_size": "large",
    "density": "comfortable",
    "notification_position": "top_right",
    "mode": "light"
  },
  "migration_source": null
}
```

Success returns the complete resolved presentation object and incremented
revision. DELETE requires `base_revision`, removes the user's Appearance
override, and restores the effective tenant/product default across devices. It
does not change the presentation rollout flag.

### 6.3 Authorization, validation, and generic errors

- Active authenticated staff user required.
- Customer, driver, public-link, and standalone portal identities do not receive
  or mutate staff Appearance state.
- Missing active tenant context returns `400 TENANT_CONTEXT_REQUIRED`.
- Unsupported schema version, unknown enum, extra field, arbitrary CSS/color,
  malformed body, URL, or numeric scale returns `422` before a write.
- Unauthenticated/expired session returns `401`.
- Inactive or ineligible authenticated role returns `403`.
- Stale `base_revision` returns `409` with current revision only, not payload.
- Store unavailable returns `503`; no server or local commit is claimed.
- Foreign preference rows are never loaded and behave as absent.
- Logs contain only user ID, tenant ID, schema version, revision, operation, and
  outcome category.

### 6.4 Concurrency and idempotency

Optimistic concurrency is authoritative; silent last-write-wins is prohibited.
Each apply/reset supplies the current `base_revision`. A revision is accepted
once; a stale write returns `409`, after which the client refetches and reports
that settings changed elsewhere. It must not silently replay a stale preview.

An identical retry after confirmed success may return the current representation
without another revision increment when it carries the same request ID. The
mutation, migration-complete transition, and revision increment are one
transaction.

## 7. Appearance values and density

```text
accent: cyan | indigo | emerald | rose | amber
font_family: geist | dm-sans | jakarta | inter
font_size: small | default | large
density: compact | default | comfortable | large
notification_position: top_right | bottom_right | top_center
mode: light | dark | high_contrast
```

Arbitrary values are prohibited. Density changes spacing and information rhythm,
not browser zoom:

| Density | Row minimum | Card gap | Section gap | Control minimum |
|---|---:|---:|---:|---:|
| Compact | 48px | 8px | 16px | 44px |
| Default | 52px | 12px | 20px | 44px |
| Comfortable | 56px | 16px | 24px | 44px |
| Large | 64px | 20px | 28px | 48px |

Body font sizes are 14px, 16px, and 18px for small, default, and large.
Touch-first editable controls remain at least 16px. Browser zoom and user-agent
text scaling remain functional. Financial values use tabular numerals, right
alignment, and no character clipping.

## 8. Token ownership

### 8.1 Immutable product and semantic tokens

Personalization cannot change the DieselBridge mark, product identity, shell
semantics, focus structure, minimum contrast, motion ceilings, or semantic
success, warning, destructive, financial, authorization, payment, settlement,
and operational-risk states.

Required independent semantic families:

```text
--semantic-success-*
--semantic-warning-*
--semantic-danger-*
--semantic-info-*
--semantic-financial-positive-*
--semantic-financial-negative-*
--semantic-authorization-*
--semantic-payment-pending-*
--semantic-payment-confirmed-*
--semantic-operational-risk-*
```

Components carrying those meanings must never consume a personal accent token.

### 8.2 Personalizable tokens

```text
--personal-accent-400/500/600
--font-body
--font-display
--font-size-body
--density-row-min
--density-control-min
--density-card-gap
--density-section-gap
--surface-canvas
--surface-raised
--surface-glass
--surface-overlay
--text-primary
--text-secondary
--border-subtle
```

Accent is limited to neutral current-navigation/selection states, neutral links,
focus enhancement in addition to the immutable outline, non-semantic chart
series with legends, and decoration. High contrast and forced colors may replace
authored accents entirely.

## 9. Cache, hydration, preview, and notifications

### 9.1 Identity-bound bootstrap cache

Cache key:

```text
dieselbridge:presentation:v1:{tenant_id}:{user_id}
```

It contains only schema version, Appearance, revision, resolved presentation,
and timestamp. It may be read only after persisted/authenticated identity matches
both user and tenant. WorkOS identity remains untrusted until `/auth/workos/me`
succeeds. User switch, tenant switch, logout, inactivation, role change, or auth
session-epoch change immediately removes the previously applied presentation.

The server response always replaces cache. A matching offline cache may be used
for up to 30 days and marked stale internally. Without a matching cache, use
legacy presentation and product defaults. Never flash another user's or tenant's
identity or appearance. Hydration must preserve route, valid focus target, form
state, and active mutation state.

### 9.2 Reversible live preview

Settings maintains separate committed and draft Appearance values. Control
changes update draft tokens without a network write. Apply persists with current
revision and prevents duplicate submission. Cancel, close, or navigation with
unapplied changes restores the complete committed value.

Failed Apply keeps the draft available in Settings but restores committed values
outside the preview boundary. Reset first previews effective defaults and
persists only after confirmation; reset failure restores the prior committed
preference. Focus remains on the initiating control or resulting status message.
Announcements are polite and atomic.

### 9.3 Notifications

The existing shared toaster remains authoritative. Placement changes only its
container anchor. Toasts respect safe areas and mobile navigation and never cover
the heading, active modal actions, repair-order footer actions, or focused
control. At 320/390px, maximum width is viewport minus 32px. High contrast and
forced colors preserve icon, border, and text differentiation. Notifications
never expose raw preference payloads.

### 9.4 Motion and platform accessibility

No ambient loop is permitted. Presentation transitions use compositor-friendly
opacity/transform and finish within 240ms. Token changes do not animate every
descendant. Reduced motion is immediate or a short crossfade. Reduced
transparency removes blur and uses opaque surfaces. Forced colors uses system
colors and visible borders. Presentation changes do not reset focus or announce
unrelated content. Both presentations preserve landmarks, focus order, keyboard
behavior, accessible names, and at least 44x44 CSS-pixel visible targets.

## 10. Shared import-safe fixtures

Create side-effect-free fixtures under:

```text
frontend/src/test-fixtures/db035/
  staffSession.ts
  tenantBranding.ts
  dashboard.ts
  customers.ts
  repairOrders.ts
  messages.ts
  myShop.ts
  settings.ts
  appearance.ts
```

They may not initialize an API client, router, storage, clock, WebSocket, or
mutation. Required identities and states:

- Garage owner, garage admin, receptionist, assigned mechanic.
- Fleet manager with and without messaging grant.
- Same user identity in a different tenant and a second user in the same tenant.
- Valid, invalid, and missing legacy values.
- Current and stale server revisions.
- Tenant default legacy/new; user override legacy/new/null; global force legacy.
- Matching offline cache and foreign user/tenant cache.
- Loading, empty, error, populated, long-label, long-tenant-name, absent-logo,
  oversized-logo, long-money, and negative-balance data.

Old/new browser journeys import identical domain fixtures and differ only in
resolved presentation.

## 11. Acceptance matrix

### 11.1 Exhaustive Appearance render contract

Every Cartesian combination of five accents, four fonts, three font sizes, four
densities, three modes, three notification positions, and all six surfaces must
run through an import-safe render harness. It asserts no exception, no missing
token, no document overflow, minimum target dimensions, table headings and
accessible names, aligned/unclipped money, no semantic use of personal accent,
and valid toast safe-area bounds.

### 11.2 Browser viewport matrix

Both presentations cover all six surfaces at 1440, 1366, 1280, 1120, 960, 390,
and 320 CSS pixels plus 200% browser zoom. Playwright uses pairwise Appearance
coverage plus every minimum/maximum boundary; the exhaustive Cartesian contract
remains in the render harness.

### 11.3 Accessibility and adverse-content matrix

Both presentations cover keyboard-only operation, visible focus, reduced
motion, reduced transparency, high contrast, forced colors, coarse pointer,
44px targets, long labels, long tenant names, missing/oversized logos,
loading/empty/error/populated states, long and negative financial values, and
notifications while modal/footer actions are active.

### 11.4 Persistence and rollout matrix

Verify reload, new tab, cross-tab committed update, second device/session,
matching offline cache, absent/foreign cache, stale server revision, user switch,
tenant switch, logout/login, reset, canceled preview, failed Apply, global and
tenant rollback, user override removal, exactly-once legacy migration, and an
old client unable to overwrite completed server state.

### 11.5 Old/new parity journeys

Against identical fixtures, both presentations must produce identical routes,
requests, permissions, mutation bodies, and resulting domain state for:

1. Dashboard to customer and vehicle/customer detail.
2. Create/edit repair order, labor/parts, and work-first status.
3. Existing additional-work authorization publication.
4. Message list, thread, and reply.
5. My Shop authorized read/update.
6. Profile update.
7. Role-denied Messages route.
8. Tenant switch and session rebootstrap.

Presentation mode may add no business request and alter no business response.

## 12. Negative cases and rollback triggers

Implementation fails acceptance if:

- New mode changes a route, request, permission, mutation, WebSocket, or result.
- Appearance crosses a user or tenant boundary.
- Customer/driver/public identities receive staff preference state.
- Legacy storage overwrites completed server migration.
- Arbitrary CSS, color, font, URL, or numeric scale is accepted.
- Accent recolors financial, payment, authorization, success, warning,
  destructive, or operational-risk meaning.
- Cancel/reset leaves partial draft tokens active.
- Offline startup uses a foreign cache.
- A notification blocks a focal control.
- Compact density produces a visible target below 44px.
- Large type or 200% zoom creates page-level horizontal overflow.
- Tenant identity replaces DieselBridge product identity.
- Rollback requires deleting preferences or shipping a different router.

Any authorization/request parity difference, tenant leak, critical navigation or
mutation divergence, hydration loop, elevated render failure, semantic status
recoloring, or critical accessibility regression triggers scoped or global
rollback to legacy.

## 13. Work split and gates

Backend & Integrations owns the additive migration, models, shared bootstrap
builder, schemas, Appearance endpoints, rollout endpoints, tenant isolation,
optimistic concurrency/idempotency, redacted metrics, and backend/migration
tests. Contract enum, precedence, or compatibility changes return to
Architecture rather than being negotiated during implementation.

Frontend & UX may implement against v1 fixtures after this contract is committed.
It owns the Presentation provider, identity-bound cache, one-time migration,
token layers, shared shell, six surfaces, Appearance UI, reversible preview,
product/tenant hierarchy, responsive/accessibility behavior, component tests,
production build, and parity Playwright evidence.

Independent Security gates user/tenant preference isolation, rollout authority,
cache identity, concurrency, and logging. Independent QA gates old/new parity
and persistence. Independent Impeccable/Emil review gates hierarchy, materials,
typography, density, motion, and finish. Release & Reliability owns cohort
rollout, observability, rollback exercise, compatibility evidence, and release.

No implementing owner may self-approve its independent gate.
