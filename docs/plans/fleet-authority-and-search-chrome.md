# Fleet membership follows authority, and two search-field fixes

Branch: `feat/fleet-authority`, off `main` at `d2a37545`.

## Context

Two separate pieces of work, bundled because they land in the same two files.

### 1. A truck is on the Fleet Board because a company runs it

Removing `77C-603` from its fleet reported success, ended the membership, and
left the truck on the board. Nothing was broken in the removal — the board
simply admits a truck on either of two grounds:

```python
or_(
    FleetMembership.id.is_not(None),        # a company has authority over it
    Customer.is_internal_fleet.is_(True),   # the generic "House Account" owns it
)
```

The second branch is the one the operator says is not a real relationship: the
shop owning a truck is not what puts it on a fleet board — a company with
operating authority over it is. The shop's own trucks qualify because the
transport company that runs them is owned by the same people, and that company
is the fleet's member.

**Production agrees.** Of 23 trucks on fleet boards, 22 arrive through a real
membership. Exactly one — `77C-603`, 0 open memberships — arrives through the
house-account branch alone, and it is the truck that would not go away.

| Tenant | via membership | via house account only |
|---|---|---|
| Truck Pit Stop | 21 | 0 |
| Truck Pit Stop Wisconsin | 1 | **1** ← `77C-603` |

**The join path already works the way the operator describes.** Adding a truck
requires an operating authority and calls `ensure_fleet_membership`; linking an
existing one posts a membership. So membership-only visibility does not strand
new trucks. Only pre-existing data lacking a membership is affected, and
production holds exactly one such truck.

Outcome: removing a truck from a fleet removes it from the board, and a truck
is on a board because a company is answerable for it.

### 2. Two composed search fields render a border inside a border

The operating-authority picker draws a box inside its own box, and the VIN
field's underline sits tight against an input that should not have had a border
at all. Both are the same defect.

`.dsec input:not([type="radio"]):not([type="checkbox"])` (fleet.css:811) gives
every input in the shell a border and a 46px height. Two composed controls try
to reset that for their inner input:

| Selector | Specificity |
|---|---|
| `.dsec input:not([type=radio]):not([type=checkbox])` (811) | **(0,4,1)** |
| `.dsec .authority-combobox input` (202) | (0,3,1) |
| `.dsec .vin-autofill-control input` (826) | (0,3,1) |

Each `:not()` contributes its argument's specificity, so the generic rule wins
and both resets are dead code. The inner input keeps its own 46px bordered box
inside the 46px container.

`.dsec .driver-profile-search input` (489) already hit this and fixed it by
carrying the same `:not()` guards. That is the precedent to follow.

## Approach

### A. One fleet-scope predicate, membership-only

The `or_(...)` above is copy-pasted in six places:

| Line | Function |
|---|---|
| 178 | `_get_fleet_vehicle` |
| 474 | `list_fleet_vehicles` |
| 1407 | `_fleet_vehicles` |
| 1430 | `_fleet_board_vehicle_ids` |
| 1659 | `_fleet_board_from_projection` |
| 2507 | `_load_fleet_ro_or_404` |

Extract it to a single helper in `backend/app/api/v1/endpoints/fleet.py` and
change it there once:

```python
def fleet_scope_clause():
    """A truck is on a fleet board because a company has authority over it.

    Ownership by the tenant's house account is not a second route in: the
    shop's own trucks reach the board the same way every other truck does,
    through a membership naming the company that runs them.
    """
    return FleetMembership.id.is_not(None)
```

Keep the `Vehicle.id.is_(None)` migration-restore branch in
`_fleet_board_from_projection` — it is unrelated.

**Pricing does not change.** `internal_fleet.py` keys off `is_internal_fleet`
to decide at-cost parts and the internal labor rate. Who pays and who is
answerable are different questions; only the second one moves.

### B. Do not strand the truck that loses its route in

`list_fleet_vehicle_candidates` (the "Link existing truck" search) scopes to
`Vehicle.tenant_id` and **not** to fleet scope, so a removed truck stays
findable and re-linkable. Verify this holds — it is what makes removal
reversible rather than a trap.

`77C-603` will leave the Wisconsin board on deploy. That is the requested
outcome; it remains in the tenant, keeps its history, and can be re-linked to
an operating authority at any time.

### C. Surface the fleet authority that is half-configured

`Tenant.fleet_company_name` and `default_fleet_authority_customer_id` exist so a
real carrier is the fleet's authority. In production only the name is set, and
only on one tenant:

| Tenant | fleet company | authority customer |
|---|---|---|
| Truck Pit Stop | 77 Cargo | **not set** |
| Truck Pit Stop Wisconsin | not set | not set |
| Right Solution | not set | not set |

`AuthorityPicker` already reads `default_fleet_authority_customer_id` to sort the
house authority first, so setting it improves the add-truck flow immediately.

Scope here is deliberately small: **surface it, do not automate it.** Show the
configured authority in fleet settings and say when it is unset. Assigning a
customer to a fleet company is an operator decision about who is answerable for
the trucks, not something to infer from a name match.

### D. The two search fields

Follow the `.driver-profile-search` precedent exactly — add the `:not()` guards
so the resets outrank the generic rule:

```css
.fleet-root .dsec .authority-combobox input:not([type="radio"]):not([type="checkbox"]),
.fleet-root .dsec .authority-combobox input:not([type="radio"]):not([type="checkbox"]):focus { … }
```

Same for `.vin-autofill-control`. Zero blast radius: raising two dead rules to
the specificity they always needed changes nothing else.

Then give the VIN control breathing room from its underline —
`.vin-autofill-control` is `height:48px` with `border-bottom`, and the input
currently fills it edge to edge. Add bottom padding inside the control so the
text clears the rule.

A comment on both resets should say why the guards are there, or the next person
removes them as redundant and silently reintroduces the double border.

## Files

| File | Change |
|---|---|
| `backend/app/api/v1/endpoints/fleet.py` | extract `fleet_scope_clause()`, apply at the 6 sites, drop the house-account branch |
| `backend/app/api/v1/endpoints/fleet.py` | fleet settings response: expose configured authority + whether it is set |
| `backend/app/schemas/fleet.py` | `FleetSettingsResponse` gains the authority fields |
| `frontend/src/features/fleet/fleet.css` | specificity guards on lines 202 and 826; VIN control padding |
| `frontend/src/features/fleet/FleetApp.tsx` | show the configured authority in fleet settings |
| `backend/tests/test_fleet_workflows.py` | tests below |

No migration. No change to `internal_fleet.py`.

## Verification

**Tests**

- A house-account truck with no membership does **not** appear on the board —
  the regression that started this. Fails before the change.
- Ending a membership removes the truck from the board, for a house-account
  truck and an external one alike.
- A removed truck is still returned by `list_fleet_vehicle_candidates`, so it can
  be re-linked. This is what keeps removal reversible.
- Adding a truck creates a membership to the chosen authority and the truck
  appears on the board.
- **Pricing is untouched:** an internal-fleet order still prices parts at cost
  and labor at the internal rate after the visibility change.

**Manual, at iPad width**

1. Fleet board: `77C-603` is gone from Wisconsin; the other 22 trucks remain.
2. Add or link truck → "Link existing truck" → search `77C-603` → it is findable
   and re-links to an authority, returning to the board.
3. The operating-authority field reads as one search box — icon and text inside a
   single border, no inner box. Focus ring on the container, not the input.
4. The VIN field's underline clears the text.

**Production, read-only, after deploy**

Re-run the board-composition query: expect `via_house_account_only` to be 0 on
every tenant, and the membership counts unchanged at 21 / 1.

## Risks

1. **A truck disappearing is alarming if unexplained.** Exactly one truck is
   affected and it is the one the operator asked about, but the board gives no
   account of why it went. `end_fleet_membership` already records a reason and
   `134_fleet_membership_ended_by` records who — worth confirming that history is
   reachable from the truck before relying on it.
2. **Six call sites, one predicate.** Changing scope in five places and missing
   the sixth produces a board and a detail view that disagree. Extracting the
   helper first is what makes that hard to get wrong.
3. **Another tenant could have house-account trucks without memberships.**
   Production has one today. The check is cheap and belongs in the pre-deploy
   read, not in an assumption.
4. **The specificity guards look like noise.** Without the comment, the next
   cleanup deletes them and the double border returns silently — which is how
   these two rules came to be dead in the first place.

---

## Addendum — what production testing surfaced

Written after the CSS half shipped and the operator exercised the real board.

### The blocker cleared itself

Zero trucks in production now reach a board through the house-account branch
alone. `77C-603` was linked to Elis Logistics and renamed to `603`. Section B's
sequencing concern is resolved: the visibility change can ship without anything
disappearing.

### A truck can sit on a board it is not owned by, and nothing says so

`d3bed256…` is owned by **House Account** and carries an operating authority of
**Elis Logistics**. Both are true at once, by design — but no surface shows both,
so the disagreement is invisible until it bites.

It bites at `DELETE /customers/{customer_id}/vehicles/{vehicle_id}`, which
requires `Vehicle.customer_id == customer_id` and otherwise answers **"Vehicle
not found."** Deleting this truck from the Elis profile returns a 404 that says
the record does not exist, when what is true is that Elis does not own it. The
operator reasonably concluded the truck was missing.

**Decided:** keep two facts. Ownership says whose truck it is; membership says
which board it appears on. That is what lets a carrier own 200 trucks while 12
are fleet-managed, and lets a truck leave a board without changing hands. The
cost is drift, so the fix is to make drift visible rather than to collapse the
model.

**Changes:**

1. `delete_customer_vehicle` — when the vehicle exists in the tenant but is
   owned by someone else, say so and name the owner, instead of claiming it does
   not exist. Distinguish "no such truck" from "not this customer's truck".
2. Show owner and operating authority together wherever a fleet truck is shown,
   so a mismatch reads before it is acted on. The truck-detail view already has
   `TRUCK OWNER / LESSOR` and `OPERATING AUTHORITY` side by side; the gap is the
   customer profile, which shows only what a customer owns.

### Two trucks now share the unit number `603`

| id | VIN | Plate | Odometer | Owner | ROs |
|---|---|---|---|---|---|
| `51c800af…` | 4V4WC9EG**2**LN250022 | VW9328 | 589,745 | Elis Logistics | 15 |
| `d3bed256…` | 4V4WC9EG**9**LN250022 | DD-4019A | 598,456 | House Account | 0 |

Different plates and 8,711 miles apart, so these are two vehicles whose VINs
differ only in the check digit — a typo, not a duplicate. **They must not be
merged:** one carries 15 repair orders of history.

Not a code change. Renaming `d3bed256…` back to something distinct is an
operator action, listed here so the collision is not mistaken for a bug in the
visibility work.

### Revised scope

The plan above stands. Added to it:

| File | Change |
|---|---|
| `backend/app/api/v1/endpoints/customers.py` | `delete_customer_vehicle`: separate "not found" from "not this customer's truck", naming the owner |
| `backend/tests/` | a vehicle owned by another customer returns the owner-specific error, not a bare 404 |

Still one PR, as asked.
