// ============================================================
// Truck Pit Stop — Fleet data layer (deterministic mock)
// ============================================================
(function () {
  // --- seeded RNG so the fleet is stable across reloads ---
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const rnd = mulberry32(20260616);
  const pick = (arr) => arr[Math.floor(rnd() * arr.length)];
  const between = (lo, hi) => lo + Math.floor(rnd() * (hi - lo + 1));

  // --- pools ---
  const MAKES = [
    { make: "Freightliner", model: "Cascadia 126", brandShort: "FL" },
    { make: "Volvo", model: "VNL 760", brandShort: "VO" },
    { make: "Kenworth", model: "T680", brandShort: "KW" },
    { make: "Peterbilt", model: "579", brandShort: "PB" },
    { make: "International", model: "LT 625", brandShort: "IN" },
    { make: "Mack", model: "Anthem", brandShort: "MK" },
    { make: "Western Star", model: "49X", brandShort: "WS" },
    { make: "Volvo", model: "VNR 640", brandShort: "VO" },
  ];
  const TYPES = ["Sleeper", "Day Cab", "Reefer", "Dry Van", "Flatbed", "Tanker"];
  const DRIVERS = [
    "Dmitri Kovalenko", "Marcus Reed", "Vitaliy Petrenko", "Sergei Bondar",
    "Andre Wilson", "Oleg Marchuk", "Pavel Sych", "Travis Long",
    "Yuriy Hnatiuk", "Bohdan Tkach", "Carlos Mendez", "Ivan Shevchuk",
    "Roman Dovzhenko", "Keith Barnes", "Mykola Hrytsenko", "Devon Pratt",
    "Anton Kravets", "Luis Romero", "Stepan Boyko", "Jamal Carter",
    "Viktor Lysenko", "Taras Melnyk", "Brian Foley", "Ruslan Zinchenko",
  ];
  const MECHANICS = ["Mike Doyle", "Stas Ruban", "Roman Lutz", "Danny Cho", "Greg Olsen"];
  const CITIES = [
    "Matthews, NC", "Charlotte, NC", "Gastonia, NC", "Concord, NC",
    "Rock Hill, SC", "Statesville, NC", "Salisbury, NC", "Monroe, NC",
    "Greenville, SC", "Spartanburg, SC", "Hickory, NC", "Columbia, SC",
    "Greensboro, NC", "Asheville, NC", "Florence, SC", "Winston-Salem, NC",
  ];
  const ROUTES = ["I-85 N", "I-77 S", "I-485 Outer", "US-74 E", "I-40 W", "I-26 E", "I-95 N"];

  // status distribution for 24 trucks
  const STATUS_PLAN = [
    "active","active","active","active","active","active","active","active",
    "active","active","active","active","active",        // 13 on the road
    "shop","shop","shop","shop",                          // 4 in shop
    "pm","pm","pm","pm",                                  // 4 PM due
    "parts","parts","parts",                              // 3 awaiting parts
  ];

  // shop coordinates on the schematic map (Matthews HQ)
  const HQ = { x: 50, y: 62 };

  const PART_NAMES = [
    "Front brake shoes (steer)", "Air dryer cartridge", "Alternator", "Turbocharger",
    "Clutch assembly", "Water pump", "EGR cooler", "Fuel filter set", "Drag link",
    "Wheel seal (drive)", "Shock absorbers (pair)", "DEF pump", "Starter motor",
    "Radiator", "Slack adjuster", "U-joint", "Cab air spring", "ABS sensor",
  ];
  const REPAIR_SUMMARIES = [
    "Replaced front brake shoes + drums, all axles inspected",
    "Air leak traced to dryer — cartridge + governor replaced",
    "Charging fault — alternator + serpentine belt",
    "Coolant loss — water pump reseal",
    "DEF derate — pump + NOx sensor replaced",
    "Clutch slipping — full assembly + throwout bearing",
    "Check-engine P0401 — EGR cooler service",
    "Wheel-end howl — drive seal + bearing",
  ];

  function makeHistory(odo, status) {
    // PM roughly every 25k miles
    const out = [];
    const n = between(3, 6);
    let m = odo;
    for (let i = 0; i < n; i++) {
      m -= between(18000, 27000);
      if (m < 4000) break;
      const isPm = rnd() > 0.42;
      out.push({
        date: randDate(i),
        kind: isPm ? "PM" : (rnd() > 0.7 ? "Inspection" : "Repair"),
        odo: m,
        summary: isPm ? `Preventive maintenance — Service ${String.fromCharCode(65 + (i % 3))}: oil, filters, lube, ${between(40,120)}-pt inspection`
                       : (rnd() > 0.7 ? "Annual DOT / FMCSA inspection — passed" : pick(REPAIR_SUMMARIES)),
        mechanic: pick(MECHANICS),
        cost: isPm ? between(380, 720) : between(640, 3200),
      });
    }
    return out;
  }
  function randDate(stepsBack) {
    const d = new Date(2026, 5, 16);
    d.setDate(d.getDate() - (stepsBack * between(26, 52) + between(2, 20)));
    return d.toISOString().slice(0, 10);
  }
  function makeParts(history) {
    const out = [];
    const n = between(2, 4);
    for (let i = 0; i < n; i++) {
      const installed = pick(history.filter((h) => h.kind !== "Inspection")) || history[0];
      const installDate = new Date(installed.date);
      const warrantyMonths = pick([6, 12, 12, 24]);
      const until = new Date(installDate);
      until.setMonth(until.getMonth() + warrantyMonths);
      out.push({
        name: pick(PART_NAMES),
        date: installed.date,
        odo: installed.odo,
        mechanic: installed.mechanic,
        warrantyUntil: until.toISOString().slice(0, 10),
        warrantyMiles: warrantyMonths * 10000,
        active: until > new Date(2026, 5, 16),
      });
    }
    return out;
  }
  const INCIDENT_TYPES = [
    { t: "Roadside breakdown", sev: "high" },
    { t: "Minor collision", sev: "high" },
    { t: "Tire blowout", sev: "med" },
    { t: "Overheat warning", sev: "med" },
    { t: "DOT roadside inspection", sev: "low" },
    { t: "Jackknife near-miss", sev: "med" },
    { t: "Def system derate", sev: "med" },
  ];
  function makeIncidents() {
    const n = rnd() > 0.5 ? between(0, 2) : 0;
    const out = [];
    for (let i = 0; i < n; i++) {
      const inc = pick(INCIDENT_TYPES);
      out.push({
        date: randDate(between(0, 4)),
        type: inc.t,
        sev: inc.sev,
        location: pick(CITIES),
        note: pick([
          "Driver pulled to shoulder safely. Towed to shop.",
          "No injuries. Reported to dispatch and insurer.",
          "Resolved roadside by mobile unit, returned to route.",
          "Logged with FMCSA. No violations issued.",
          "Towed in — work order opened on arrival.",
        ]),
      });
    }
    return out;
  }

  const WO_STATUS = ["Awaiting parts", "In progress", "Diagnosing", "Quality check", "Ready for pickup"];
  function makeWorkOrder(status, mechanic) {
    let woStatus;
    if (status === "parts") woStatus = "Awaiting parts";
    else if (status === "shop") woStatus = pick(["In progress", "Diagnosing", "Quality check", "In progress"]);
    else woStatus = pick(WO_STATUS);
    return {
      id: "WO-" + between(4120, 4990),
      opened: randDate(0),
      status: woStatus,
      summary: pick(REPAIR_SUMMARIES),
      mechanic,
      eta: pick(["Today 4:30p", "Tomorrow AM", "Jun 18", "Jun 19", "On parts ETA"]),
      laborHrs: between(2, 14),
    };
  }

  // scatter active trucks around the region; parked ones near HQ
  function placeTruck(status, i) {
    if (status === "active") {
      const angle = rnd() * Math.PI * 2;
      const dist = 14 + rnd() * 34;
      return {
        x: Math.max(6, Math.min(94, HQ.x + Math.cos(angle) * dist)),
        y: Math.max(8, Math.min(92, HQ.y + Math.sin(angle) * dist * 0.78)),
        moving: true,
      };
    }
    // parked at / near the yard
    const jx = (rnd() - 0.5) * 9;
    const jy = (rnd() - 0.5) * 7;
    return { x: HQ.x + jx, y: HQ.y + jy - 2, moving: false };
  }

  function dist(a, b) {
    // schematic units -> miles (~5.4 mi per unit)
    const dx = a.x - b.x, dy = (a.y - b.y) * 0.85;
    return Math.round(Math.sqrt(dx * dx + dy * dy) * 5.4);
  }

  const trucks = STATUS_PLAN.map((status, i) => {
    const m = MAKES[i % MAKES.length];
    const year = between(2018, 2025);
    const odo = between(120000, 760000);
    const pmInterval = 25000;
    let nextPm;
    if (status === "pm") nextPm = odo + between(-1200, 1400); // due now / overdue
    else nextPm = odo + between(3200, 24000);
    const history = makeHistory(odo, status);
    const mechanic = pick(MECHANICS);
    const pos = placeTruck(status, i);
    const onRoute = status === "active";
    return {
      id: "t" + (i + 1),
      unit: "TPS-" + String(101 + i),
      year, make: m.make, model: m.model, brandShort: m.brandShort,
      type: pick(TYPES),
      vin: genVin(),
      plate: genPlate(),
      status,
      driver: DRIVERS[i % DRIVERS.length],
      odometer: odo,
      pmInterval,
      nextPm,
      pmRemaining: nextPm - odo,
      location: onRoute
        ? { label: pick(ROUTES) + " · " + pick(CITIES), city: pick(CITIES), since: between(1, 9) + "h ago" }
        : { label: "TPS Yard · Bay " + between(1, 8), city: "Matthews, NC", since: between(1, 6) + "d" },
      pos,
      mph: onRoute ? between(48, 68) : 0,
      heading: onRoute ? pick(["N", "NE", "E", "SE", "S", "SW", "W", "NW"]) : "—",
      assignedMechanic: mechanic,
      workOrder: status === "active" ? null : makeWorkOrder(status, mechanic),
      history,
      parts: makeParts(history),
      incidents: makeIncidents(),
    };
  });

  function genVin() {
    const chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789";
    let s = "1FUJG";
    for (let i = 0; i < 12; i++) s += chars[Math.floor(rnd() * chars.length)];
    return s;
  }
  function genPlate() {
    const L = "ABCDEFGHJKLMNPRSTUVWXYZ";
    return L[Math.floor(rnd()*23)] + L[Math.floor(rnd()*23)] + L[Math.floor(rnd()*23)] + "-" + between(1000, 9999);
  }

  // distance helper exposed (focused truck -> nearest N others)
  function nearest(truck, all, n) {
    return all
      .filter((t) => t.id !== truck.id)
      .map((t) => ({ truck: t, miles: dist(truck.pos, t.pos) }))
      .sort((a, b) => a.miles - b.miles)
      .slice(0, n);
  }

  const STATUS_META = {
    active: { label: "On the road", short: "On road", color: "var(--st-active)", dot: "#22c55e" },
    shop:   { label: "In the shop", short: "In shop",  color: "var(--st-shop)",   dot: "#38bdf8" },
    pm:     { label: "PM due soon", short: "PM due",   color: "var(--st-pm)",     dot: "#f5b301" },
    parts:  { label: "Awaiting parts", short: "Parts", color: "var(--st-parts)",  dot: "#a78bfa" },
  };

  const fleetStats = {
    total: trucks.length,
    active: trucks.filter((t) => t.status === "active").length,
    shop: trucks.filter((t) => t.status === "shop").length,
    pm: trucks.filter((t) => t.status === "pm").length,
    parts: trucks.filter((t) => t.status === "parts").length,
    openWO: trucks.filter((t) => t.workOrder).length,
    incidents30: trucks.reduce((a, t) => a + t.incidents.length, 0),
  };

  window.FleetData = {
    trucks, HQ, STATUS_META, fleetStats,
    nearest, dist, MECHANICS,
    fmt: (n) => n.toLocaleString("en-US"),
    money: (n) => "$" + n.toLocaleString("en-US"),
  };
})();
