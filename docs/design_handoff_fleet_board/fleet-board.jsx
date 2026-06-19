// ============================================================
// FleetBoard — KPI strip, filters, truck card grid
// props: trucks, onOpen(truck), filter, setFilter, query, setQuery
// ============================================================
(function () {
  const { STATUS_META, fleetStats, fmt } = window.FleetData;
  const I = window.Icons;

  function pmState(t) {
    const r = t.pmRemaining;
    if (r <= 0) return { label: "OVERDUE " + fmt(Math.abs(r)) + " mi", cls: "pm-over", pct: 100 };
    if (r < 2500) return { label: "Due in " + fmt(r) + " mi", cls: "pm-soon", pct: 100 - (r / t.pmInterval) * 100 };
    return { label: fmt(r) + " mi to PM", cls: "pm-ok", pct: 100 - (r / t.pmInterval) * 100 };
  }

  function Kpi({ icon, value, label, accent, active, onClick }) {
    const Ico = I[icon];
    return React.createElement(
      "button",
      { className: "kpi" + (active ? " is-active" : ""), style: { "--ac": accent }, onClick },
      React.createElement("div", { className: "kpi-ic" }, React.createElement(Ico, { size: 19 })),
      React.createElement("div", { className: "kpi-tx" },
        React.createElement("div", { className: "kpi-val" }, value),
        React.createElement("div", { className: "kpi-lbl" }, label)
      )
    );
  }

  function TruckCard({ t, onOpen }) {
    const meta = STATUS_META[t.status];
    const pm = pmState(t);
    return React.createElement(
      "button",
      { className: "tcard", style: { "--st": meta.dot }, onClick: () => onOpen(t) },
      React.createElement("div", { className: "tcard-top" },
        React.createElement("div", { className: "tcard-id" },
          React.createElement("span", { className: "tcard-unit" }, t.unit),
          React.createElement("span", { className: "tcard-mm" }, t.year + " " + t.make + " " + t.model)
        ),
        React.createElement("span", { className: "tcard-badge" },
          React.createElement("i", { className: "tcard-bdot" + (t.pos.moving ? " is-moving" : "") }),
          meta.short)
      ),
      React.createElement("div", { className: "tcard-type" }, t.type),
      // location row
      React.createElement("div", { className: "tcard-row" },
        React.createElement("span", { className: "tcard-row-ic" }, React.createElement(I.pin, { size: 14 })),
        React.createElement("span", { className: "tcard-row-tx" }, t.location.label),
      ),
      // driver row
      React.createElement("div", { className: "tcard-row" },
        React.createElement("span", { className: "tcard-row-ic" }, React.createElement(I.user, { size: 14 })),
        React.createElement("span", { className: "tcard-row-tx" }, t.driver),
        t.mph ? React.createElement("span", { className: "tcard-mph" }, t.mph + " mph " + t.heading) : null,
      ),
      // odometer
      React.createElement("div", { className: "tcard-odo" },
        React.createElement("span", null, "ODO"),
        React.createElement("b", null, fmt(t.odometer)),
        React.createElement("span", null, "mi")
      ),
      // PM bar
      React.createElement("div", { className: "tcard-pm" },
        React.createElement("div", { className: "tcard-pm-track" },
          React.createElement("div", { className: "tcard-pm-fill " + pm.cls, style: { width: Math.max(4, Math.min(100, pm.pct)) + "%" } })
        ),
        React.createElement("div", { className: "tcard-pm-lbl " + pm.cls }, pm.label)
      ),
      // work order footer
      t.workOrder
        ? React.createElement("div", { className: "tcard-wo" },
            React.createElement(I.wrench, { size: 13 }),
            React.createElement("span", { className: "tcard-wo-id" }, t.workOrder.id),
            React.createElement("span", { className: "tcard-wo-st" }, t.workOrder.status))
        : React.createElement("div", { className: "tcard-wo tcard-wo--clear" },
            React.createElement(I.check, { size: 13 }),
            React.createElement("span", null, "No open work orders")),
      React.createElement("span", { className: "tcard-go" }, React.createElement(I.chevronRight, { size: 16 }))
    );
  }

  function FleetBoard({ trucks, onOpen, filter, setFilter, query, setQuery, sort, setSort }) {
    let list = trucks;
    if (filter !== "all") list = list.filter((t) => t.status === filter);
    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter((t) =>
        (t.unit + " " + t.make + " " + t.model + " " + t.driver + " " + t.vin + " " + t.plate + " " + t.type)
          .toLowerCase().includes(q));
    }
    const sorters = {
      attention: (a, b) => rank(b) - rank(a),
      unit: (a, b) => a.unit.localeCompare(b.unit),
      pm: (a, b) => a.pmRemaining - b.pmRemaining,
      odo: (a, b) => b.odometer - a.odometer,
    };
    list = [...list].sort(sorters[sort] || sorters.attention);

    return React.createElement(
      "div", { className: "board" },
      // KPI strip
      React.createElement("div", { className: "kpis" },
        React.createElement(Kpi, { icon: "truck", value: fleetStats.total, label: "Trucks in fleet", accent: "var(--yellow)", active: filter === "all", onClick: () => setFilter("all") }),
        React.createElement(Kpi, { icon: "nav", value: fleetStats.active, label: "On the road", accent: STATUS_META.active.dot, active: filter === "active", onClick: () => setFilter("active") }),
        React.createElement(Kpi, { icon: "wrench", value: fleetStats.shop, label: "In the shop", accent: STATUS_META.shop.dot, active: filter === "shop", onClick: () => setFilter("shop") }),
        React.createElement(Kpi, { icon: "gauge", value: fleetStats.pm, label: "PM due soon", accent: STATUS_META.pm.dot, active: filter === "pm", onClick: () => setFilter("pm") }),
        React.createElement(Kpi, { icon: "box", value: fleetStats.parts, label: "Awaiting parts", accent: STATUS_META.parts.dot, active: filter === "parts", onClick: () => setFilter("parts") }),
        React.createElement(Kpi, { icon: "clipboard", value: fleetStats.openWO, label: "Open work orders", accent: "var(--muted)", active: false, onClick: () => setFilter("all") }),
      ),
      // toolbar
      React.createElement("div", { className: "board-bar" },
        React.createElement("div", { className: "board-bar-l" },
          React.createElement("div", { className: "fld-search" },
            React.createElement(I.search, { size: 16 }),
            React.createElement("input", {
              value: query, onChange: (e) => setQuery(e.target.value),
              placeholder: "Search unit, VIN, plate, driver, make…" })
          ),
          React.createElement("div", { className: "chips" },
            chip("all", "All", filter, setFilter),
            chip("active", STATUS_META.active.label, filter, setFilter, STATUS_META.active.dot),
            chip("shop", STATUS_META.shop.label, filter, setFilter, STATUS_META.shop.dot),
            chip("pm", STATUS_META.pm.label, filter, setFilter, STATUS_META.pm.dot),
            chip("parts", STATUS_META.parts.label, filter, setFilter, STATUS_META.parts.dot),
          )
        ),
        React.createElement("div", { className: "board-bar-r" },
          React.createElement("span", { className: "board-sort-lbl" }, "Sort"),
          React.createElement("select", { className: "fld-sel", value: sort, onChange: (e) => setSort(e.target.value) },
            React.createElement("option", { value: "attention" }, "Needs attention"),
            React.createElement("option", { value: "unit" }, "Unit number"),
            React.createElement("option", { value: "pm" }, "PM soonest"),
            React.createElement("option", { value: "odo" }, "Highest mileage"),
          )
        )
      ),
      // grid
      React.createElement("div", { className: "tgrid" },
        list.map((t) => React.createElement(TruckCard, { key: t.id, t, onOpen })),
        list.length === 0 && React.createElement("div", { className: "tgrid-empty" }, "No trucks match.")
      )
    );
  }

  function rank(t) {
    if (t.status === "shop") return t.workOrder && t.workOrder.status === "Awaiting parts" ? 4 : 5;
    if (t.status === "parts") return 4.5;
    if (t.status === "pm") return t.pmRemaining <= 0 ? 6 : 3;
    return 1;
  }

  function chip(key, label, filter, setFilter, dot) {
    return React.createElement(
      "button",
      { key, className: "chip" + (filter === key ? " is-on" : ""), onClick: () => setFilter(key) },
      dot ? React.createElement("i", { className: "chip-dot", style: { background: dot } }) : null,
      label
    );
  }

  window.FleetBoard = FleetBoard;
})();
