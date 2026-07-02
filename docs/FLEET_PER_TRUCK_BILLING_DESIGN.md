# Fleet Per-Truck Billing — Design Doc

Status: **Draft / not started**. Written 2026-07-02.
Owner: Sergio. Scope: monetize the internal-fleet feature by charging tenants per active truck.

---

## The idea (in one line)

A tenant (garage) that uses the internal-fleet feature is charged a recurring fee scaled to how many trucks are in their fleet. Bigger fleet, bigger bill.

## Why this is a real feature, not a setting

What exists today:
- The internal-fleet feature is **always on** for every tenant. There is no flag to enable/disable it per plan.
- Trucks (vehicles attached to the internal-fleet house account) are added ad hoc. Nothing counts them, limits them, or bills for them.
- Stripe in the codebase is **Stripe Connect** (`stripe_connect.py`, `tenant.stripe_account_id`). That is for the garage to collect money **from its own customers** for repairs. It is NOT a mechanism for you (the platform) to charge the garage a subscription. Those are two different Stripe products on two different accounts.

So per-truck billing needs net-new plumbing in three areas: a feature gate, truck-count tracking/enforcement, and a **platform subscription** billing integration separate from Connect.

---

## The three pieces

### 1. Feature gate — "is fleet enabled for this tenant?"

Add to `Tenant`:
- `fleet_enabled: bool = False` — is the fleet feature turned on for this tenant.
- (already shipped) `fleet_company_name` — display name of the fleet operator.

Behavior:
- When `fleet_enabled = False`: hide the fleet board/nav, block the fleet endpoints (return 402/403), don't count trucks.
- When `True`: fleet feature is live and billable.

Gate enforcement lives in `require_fleet_access` (already exists in `fleet.py`) — extend it to also check `fleet_enabled`.

### 2. Truck count + limit enforcement

"Truck" = a `Vehicle` attached to the tenant's internal-fleet house account (`is_internal_fleet` customer), not soft-deleted. There is already a query for this (`fleet.py` filters vehicles by `customer_id == fleet_customer_id`).

Add:
- `fleet_truck_limit: Optional[int]` on `Tenant` — max trucks the current plan allows (None = unlimited).
- Enforcement at the "add truck to fleet" endpoint: count active fleet trucks; if `count >= fleet_truck_limit`, reject with a clear "upgrade your plan" 402.
- A live `active_fleet_truck_count` helper (single source of truth) used by both enforcement and billing sync.

**Decision needed:** hard limit (block adding truck N+1) vs. soft/metered (allow it, just bill for it). Metered is friendlier and matches "charge per truck as the fleet grows." Hard limits create support friction. Recommend **metered** with an optional cap for plan tiers that want one.

### 3. Platform subscription billing (the actual money)

This is a **new Stripe integration**, separate from Connect:
- Uses **your** platform Stripe account (not the tenant's connected account).
- A Stripe **Product** "Fleet" with a **metered or quantity-based Price** (per truck / month).
- Each tenant gets a Stripe **Customer** (platform-side) and a **Subscription** whose quantity = active fleet truck count.

Add to `Tenant`:
- `platform_stripe_customer_id: Optional[str]` — the tenant as a customer of YOUR platform (distinct from `stripe_account_id`, which is them as a Connect merchant).
- `fleet_subscription_id: Optional[str]` — the Stripe subscription for fleet.

Sync model (quantity-based subscription — simplest, recommended over pure metered/usage-records):
- On truck add/remove (or on a nightly reconcile), set the subscription item quantity = `active_fleet_truck_count`.
- Stripe prorates automatically. Invoices monthly.
- A webhook handler updates local state on `invoice.paid` / `invoice.payment_failed` (e.g. suspend fleet on repeated failure).

**Decision needed:** quantity-based (set quantity = truck count, Stripe prorates) vs. usage-based metered (report usage records). Quantity-based is far simpler and fits "N trucks × price." Recommend **quantity-based**.

---

## Data model summary (new fields)

`Tenant`:
```
fleet_enabled: bool = False
fleet_truck_limit: Optional[int] = None        # None = unlimited
platform_stripe_customer_id: Optional[str]     # tenant as platform's customer
fleet_subscription_id: Optional[str]           # Stripe subscription for fleet
# fleet_company_name — already shipped
```

Pricing itself (price per truck, tiers) lives in **Stripe**, not the DB. Keep the DB thin: it stores IDs and the enabled/limit flags; Stripe is the source of truth for prices.

---

## Open questions (need Sergio's answers before build)

1. **Pricing:** flat $/truck/month? Tiers (1-5 trucks, 6-20, etc.)? Free tier (e.g. first 1 truck free)?
2. **Limit style:** metered (bill for whatever they add) vs. hard cap per plan. Recommend metered.
3. **Who enables fleet?** Self-serve (tenant flips it on, enters card, starts paying) vs. you approve/enable manually (matches the existing `enrollment_status` approval flow).
4. **Failure handling:** on payment failure, grace period then disable fleet? Read-only? Recommend grace period + read-only, never delete data.
5. **Trial?** Free trial period for fleet before first charge.
6. **Proration on removal:** if a truck is removed mid-month, credit them? (Stripe quantity-based prorates by default — usually leave it on.)

---

## Rough build phases (each shippable)

1. **Feature gate** — `fleet_enabled` flag + gate `require_fleet_access` + hide UI. No billing yet. (human: ~1 day / CC: ~30 min)
2. **Truck counting + limit** — `active_fleet_truck_count` helper + limit enforcement + count surfaced in settings. (human: ~1 day / CC: ~30 min)
3. **Platform Stripe subscription** — new Stripe customer + subscription, quantity sync on truck change, webhooks. The heavy one, needs Stripe test-mode setup and careful webhook handling. (human: ~1 week / CC: ~half day + manual Stripe config)
4. **Self-serve enable + billing UI** — tenant turns on fleet, enters card, sees truck count and current bill. (human: ~3 days / CC: ~1 hour)

Phases 1-2 are safe and useful even before billing (they make fleet a real, gateable feature). Phase 3 is where real money moves — do it last, in Stripe test mode, with thorough webhook + failure testing.

---

## What NOT to do

- Don't reuse Stripe Connect (`stripe_account_id`) for this. Different product, different direction of money. Mixing them will cause a mess.
- Don't store prices in the DB. Stripe owns pricing.
- Don't hard-delete fleet data on payment failure. Suspend/read-only only.
- Don't build billing before pricing is decided (question 1). The pricing model shapes the Stripe Price objects and the whole subscription shape.
