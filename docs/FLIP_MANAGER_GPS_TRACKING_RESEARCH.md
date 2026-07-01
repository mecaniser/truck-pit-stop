# Flip Manager GPS Tracking Research

Date: 2026-06-29

## Goal

Add live truck visibility to the Flip Manager/Fleet Manager board so dispatch can:

- See every active unit on a real map.
- Identify trucks that are down, in-shop, PM-due, awaiting parts, or on the road.
- Locate the nearest available unit to a breakdown.
- Show route, distance, ETA, and turn-by-turn directions when a unit is dispatched.
- Preserve enough truck context for operations: unit number, driver, speed/heading, odometer, fuel/DEF/battery when available, last update timestamp, and whether the device is stale/offline.

## Recommended Architecture

Do not build against one vendor's map UI. Use a vendor-neutral location layer:

1. Telematics provider collects GPS/vehicle data from installed hardware or OEM feeds.
2. TruckPitStop backend ingests vendor data by API polling, webhook, or stream.
3. Backend normalizes all vendors into one `fleet_locations` model.
4. Backend stores latest location plus a short history for replay/audit.
5. Flip Manager map reads from our backend, not directly from the telematics vendor.
6. Routing/ETA provider computes travel time from candidate helper units to the breakdown location.
7. Dispatch action writes an incident/dispatch record tied to the unit, driver, truck, trailer, work order, and ETA.

This keeps the board portable if the fleet changes GPS vendors later.

## Data Contract for the Board

Minimum live location shape:

```ts
type FleetLocation = {
  unitId: string;
  unitNumber: string;
  vendor: "samsara" | "motive" | "geotab" | "wialon" | "verizon" | "manual";
  vendorVehicleId: string;
  lat: number;
  lon: number;
  locatedAt: string;
  receivedAt: string;
  stale: boolean;
  speedMph?: number;
  headingDeg?: number;
  ignitionState?: "on" | "off" | "idle" | "unknown";
  driverId?: string;
  driverName?: string;
  odometerMiles?: number;
  fuelPercent?: number;
  defPercent?: number;
  batteryVoltage?: number;
  faultCodes?: string[];
  assetType: "tractor" | "trailer" | "service_truck" | "equipment";
  dispatchEligible: boolean;
};
```

Nearest-unit dispatch should filter out units that are not eligible:

- Already in-shop, PM-due, awaiting parts, disabled, or off-duty.
- Device stale beyond a threshold, for example `locatedAt > 5 minutes old`.
- Driver unavailable by HOS/shift status when that data is available.
- Tractor/trailer mismatch for the rescue task.

## Provider Shortlist

### 1. Samsara

Best fit when the fleet wants a modern all-in-one telematics platform with strong public APIs.

Useful API support:

- `GET /fleet/vehicles/locations` returns the last known location for vehicles and can filter by tag or vehicle ID.
- `GET /fleet/vehicles/stats` can return `gps`, engine state, odometer, fuel, DEF, fault codes, battery, EV state, and more.
- Webhooks and event subscriptions cover alert and event workflows such as geofence alerts, vehicle updates, engine faults, route stop events, and DVIR events.
- Kafka streaming exists for higher-volume streaming use cases.

Flip Manager fit:

- Strong for live map, stale-device detection, engine/fault context, PM odometer sync, and maintenance triggers.
- Good vendor to pilot if TruckPitStop is choosing from scratch.
- Watch contract terms and confirm API/webhook access in the quote.

Sources:

- Samsara vehicle locations API: https://developers.samsara.com/reference/getvehiclelocations
- Samsara vehicle stats API: https://developers.samsara.com/reference/getvehiclestats
- Samsara webhooks: https://developers.samsara.com/docs/webhooks

### 2. Motive

Best fit when dispatch/ELD workflows are central and the team wants explicit vehicle-location APIs.

Useful API support:

- `GET /v2/vehicle_locations` returns company vehicles with current location, driver, VIN, fuel type, speed, bearing, battery voltage, engine hours, fuel, odometer, and timestamp.
- `GET /v1/vehicle_locations/{id}` returns a specific vehicle location.
- Freight Visibility includes `GET /v1/freight_visibility/vehicle_association`, which is specifically designed to return nearby available vehicles for a provided latitude/longitude.
- API reference also includes vehicle/asset locations, dispatches, geofences, HOS logs, messages, inspections, fault codes, and webhooks.

Flip Manager fit:

- Very strong conceptual match for "truck broke down, find nearby units."
- The nearby vehicle endpoint could accelerate the first version, though I would still calculate nearest units in our backend so eligibility rules are controlled by TruckPitStop.
- Good option if the fleet already uses Motive for ELD/HOS.

Sources:

- Motive Open API overview: https://developer.gomotive.com/
- Motive vehicle locations API: https://developer.gomotive.com/reference/fetch-a-list-of-all-the-vehicles-and-their-locations-v2
- Motive vehicle location by ID: https://developer.gomotive.com/reference/fetch-a-vehicles-location-using-its-id
- Motive nearby vehicles API: https://developer.gomotive.com/reference/fetch-all-the-nearby-vehicles-as-per-the-specified-location

### 3. Geotab / MyGeotab

Best fit when flexibility, analytics, marketplace ecosystem, and reseller/integrator support matter.

Useful API support:

- MyGeotab API uses HTTPS JSON-RPC.
- `DeviceStatusInfo` represents current vehicle state and exposes latitude, longitude, bearing, speed, driver, active exception events, driving state, latest status timestamp, and whether the device is communicating.
- API has `Get` and `GetFeed` methods and documented rate limits; `DeviceStatusInfo` supports 900 `Get` requests per minute and 60 `GetFeed` requests per minute.

Flip Manager fit:

- Strong for a robust fleet data backbone, especially if the fleet has mixed assets and wants analytics.
- More engineering work than Samsara/Motive because the API is JSON-RPC and object-model based rather than simple REST endpoints.
- Very viable if a Geotab reseller can support hardware, installation, API access, and account setup.

Sources:

- Geotab concepts/API transport: https://developers.geotab.com/myGeotab/guides/concepts/
- Geotab `DeviceStatusInfo`: https://developers.geotab.com/myGeotab/apiReference/objects/DeviceStatusInfo/
- Geotab `Get` method: https://developers.geotab.com/myGeotab/apiReference/methods/Get/

### 4. Wialon

Best fit when the business wants hardware-agnostic GPS tracking through a telematics integrator.

Useful API support:

- Wialon is a telematics platform distributed through partners/integrators.
- Remote API supports searching `avl_unit` units and subscribing to item events with data flags.
- Useful if TruckPitStop wants a lower-level GPS tracking platform that can work with many third-party tracker devices.

Flip Manager fit:

- Strong if hardware flexibility and integrator pricing are priorities.
- Less turnkey than Samsara/Motive/Geotab for U.S. trucking operations unless a local integrator packages the hardware, SIMs, installation, and API support.
- Consider if the main need is fast GPS points and not full ELD/compliance/maintenance.

Sources:

- Wialon search items API: https://sdk.wialon.com/wiki/en/sidebar/remoteapi/apiref/core/search_items
- Wialon item event management: https://sdk.wialon.com/wiki/en/sidebar/remoteapi/apiref/core/update_data_flags
- Wialon unit API section: https://sdk.wialon.com/wiki/en/sidebar/remoteapi/apiref/unit/unit

### 5. Verizon Connect Reveal

Best fit for larger enterprise fleets that already use Verizon Connect or need its workforce/fleet suite.

Observed fit:

- Current public documentation for exact vehicle-location API endpoints is harder to verify than Samsara/Motive/Geotab.
- Industry reviews describe near-real-time GPS, route replay, geofencing, vehicles/trailer/equipment tracking, and strong compliance features.
- Treat API access as a sales/procurement question: ask for developer docs, sandbox, location endpoint, webhooks, rate limits, and permission model before committing.

Flip Manager fit:

- Good if the fleet already has Verizon Connect installed.
- I would not choose it first for a custom Flip Manager integration unless Verizon provides clear API access during sales.

Source:

- TechRadar Verizon Connect review, June 2026: https://www.techradar.com/reviews/verizon-connect

## Other Vendors Worth Checking

These may be viable, especially if the fleet already uses them, but API access should be verified before any product decision:

- Teletrac Navman TN360: mature compliance-heavy platform, real-time tracking, trailers/equipment support, but API docs and contract terms need confirmation. Source: https://www.techradar.com/reviews/teletrac-navman
- Azuga: easier small/midsize fleet deployment, OBD-II plug-in devices, published lower entry pricing, but check whether the API exposes live location at the freshness required by Flip Manager. Source: https://www.techradar.com/pro/software-services/azuga-review
- GPS Trackit / One Step GPS / US Fleet Tracking: good for simpler GPS tracking and possibly faster update intervals, but generally less attractive if TruckPitStop needs ELD/HOS, diagnostics, maintenance, and dispatch workflows in one system. Source for US Fleet Tracking: https://www.techradar.com/reviews/us-fleet-tracking
- Fleetio: excellent maintenance platform, but not a GPS source. It can integrate with telematics providers and may complement Flip Manager maintenance records. Source: https://www.techradar.com/reviews/fleetio

## Map, ETA, and Directions Layer

Telematics vendors tell us where the trucks are. A routing provider tells us who can arrive fastest and how to get there.

### Google Maps Platform Routes API

Use when the board needs familiar maps, traffic-aware driving ETA, route polylines, and a route matrix.

Fit:

- Excellent general map UX and traffic-aware ETA.
- Good for dispatch board ETA.
- Less ideal if we need strict heavy-truck routing constraints such as low bridges, hazmat, axle limits, and truck-restricted roads.

Source:

- Google Routes API overview: https://developers.google.com/maps/documentation/routes/overview

### Mapbox

Use when the product team wants a highly customizable map UI inside the app.

Fit:

- Strong visual control and good APIs for directions and matrix calculations.
- `mapbox/driving-traffic` factors current/historic traffic and returns durations, distances, congestion, closures, and incidents.
- Has some vehicle-weight support on the driving profile, but validate truck-route coverage for the operating region.

Sources:

- Mapbox Directions API: https://docs.mapbox.com/api/navigation/directions/
- Mapbox Matrix API: https://docs.mapbox.com/api/navigation/matrix/

### TomTom Routing API

Use when truck-specific routing matters.

Fit:

- Supports traffic, route travel time, distance, and commercial vehicle parameters.
- Supports truck-related inputs such as `travelMode=truck`, vehicle weight, axle weight, number of axles, length, width, height, commercial flag, load type, and tunnel restriction code.
- Good candidate for dispatching tractor/trailer moves where clearance and restrictions matter.

Source:

- TomTom Calculate Route API: https://developer.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-route

## Recommended Decision

For TruckPitStop, the practical shortlist is:

1. Samsara if buying a new full telematics stack and we want clean APIs, webhooks, diagnostics, and fleet operations depth.
2. Motive if the operation is trucking/ELD-heavy and nearest-available-vehicle dispatch is a core workflow.
3. Geotab if the business wants a flexible, analytics-heavy platform through a reseller/integrator.
4. Wialon if cost/hardware flexibility matters more than all-in-one U.S. fleet management.

For routing:

- Use Mapbox or Google for the initial live map and ETA UX.
- Use TomTom for dispatch routes when the truck/trailer route must respect commercial vehicle restrictions.
- Keep the routing service behind a backend adapter so it can be swapped.

## Implementation Plan for Flip Manager

Phase 1: Backend model and mock-to-real transition

- Add `fleet_units`, `fleet_location_snapshots`, `fleet_dispatch_incidents`, and `fleet_provider_accounts`.
- Map current mock truck fields from `docs/design_handoff_fleet_board/fleet-data.jsx` to real backend fields.
- Add provider adapter interface:

```ts
interface TelematicsProvider {
  syncVehicles(): Promise<ProviderVehicle[]>;
  syncLatestLocations(vehicleIds?: string[]): Promise<ProviderLocation[]>;
  subscribeWebhooks?(): Promise<void>;
}
```

Phase 2: Provider pilot

- Pick one pilot provider: Samsara or Motive.
- Load 3-5 test units into the provider.
- Pull latest location every 15-30 seconds for active units, or faster if contract/rate limits allow.
- Mark a unit stale if no fresh point arrives within 5 minutes.
- Persist all incoming points with `locatedAt`, `receivedAt`, provider, and raw payload hash.

Phase 3: Map and nearest-unit workflow

- Replace schematic map coordinates with real `lat/lon`.
- On breakdown, store incident location from driver report, GPS point, or manually dropped map pin.
- Query candidate helper units by geospatial distance first, then call routing matrix for top 5-10 units.
- Rank by ETA, dispatch eligibility, truck/trailer compatibility, driver status, and current workload.
- Show:
  - nearest units,
  - distance,
  - ETA,
  - route polyline,
  - phone/message action,
  - dispatch assignment.

Phase 4: Operational polish

- Add geofence alerts for yard, shop, customer lots, and common lanes.
- Add breakdown/roadside incident creation from the truck detail screen.
- Add audit log for dispatch decisions.
- Add stale-device/offline warnings.
- Add HOS/shift availability when the chosen provider exposes it.

## Key Sales Questions Before Choosing a Vendor

Ask each vendor:

- Do you provide API access on the plan being quoted?
- Can we access live vehicle GPS for every tractor and service truck?
- What is the location refresh interval in practice?
- Are webhooks/streams available for location or only for events/alerts?
- Are trailers tracked separately? Powered or battery trackers?
- Can we read odometer, fuel, DEF, battery, engine state, and fault codes?
- Can we read driver assignment and HOS/availability?
- What are API rate limits?
- Is there a sandbox account?
- Are there extra API, webhook, or integration fees?
- What contract length and hardware ownership terms apply?
- Can we export all historical location data if we leave?

## Risks

- "Live" GPS is usually not truly continuous. Some products update every few seconds; others update every 30-120 seconds or only during movement.
- Vendor maps and APIs may not expose the same data. Confirm API fields, not just dashboard screenshots.
- Trailer location often requires separate battery-powered asset trackers.
- Bad cellular coverage creates stale locations. The UI must show last update age.
- Routing ETA from a car-routing API can be unsafe for heavy trucks. Use truck-aware routing for dispatching tractor/trailer moves.
- Driver privacy and labor rules matter. Limit access to staff-only views and audit dispatch/location lookups.

## Review

The integration should be built as a normalized TruckPitStop location service, not a one-off map widget. Samsara and Motive are the best first calls because their public APIs directly cover vehicle location. Geotab is also strong but likely takes more integration effort. For ETA and directions, start with Mapbox or Google for UI speed, and use TomTom when truck restrictions matter.
