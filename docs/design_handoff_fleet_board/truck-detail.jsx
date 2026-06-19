// ============================================================
// TruckDetail — single truck record
// props: truck, trucks, onBack, onOpen(truck)
// ============================================================
(function () {
  const { STATUS_META, fmt, money } = window.FleetData;
  const I = window.Icons;

  function pmState(t) {
    const r = t.pmRemaining;
    if (r <= 0) return { label: "OVERDUE by " + fmt(Math.abs(r)) + " mi", cls: "pm-over" };
    if (r < 2500) return { label: "Due in " + fmt(r) + " mi", cls: "pm-soon" };
    return { label: fmt(r) + " mi remaining", cls: "pm-ok" };
  }

  function Stat({ label, value, mono }) {
    return React.createElement("div", { className: "id-cell" },
      React.createElement("div", { className: "id-k" }, label),
      React.createElement("div", { className: "id-v" + (mono ? " mono" : "") }, value));
  }

  function Section({ title, icon, count, right, children }) {
    const Ico = I[icon];
    return React.createElement("section", { className: "dsec" },
      React.createElement("div", { className: "dsec-head" },
        React.createElement("div", { className: "dsec-title" },
          React.createElement(Ico, { size: 17 }),
          React.createElement("h3", null, title),
          count != null ? React.createElement("span", { className: "dsec-count" }, count) : null),
        right || null),
      children);
  }

  function TruckDetail({ truck: t, trucks, onBack, onOpen }) {
    const meta = STATUS_META[t.status];
    const pm = pmState(t);
    const totalSpend = t.history.reduce((a, h) => a + h.cost, 0);
    const FleetMap = window.FleetMap;

    return React.createElement("div", { className: "detail" },
      // header
      React.createElement("div", { className: "dhead" },
        React.createElement("button", { className: "dback", onClick: onBack },
          React.createElement(I.arrowLeft, { size: 16 }), "Fleet board"),
        React.createElement("div", { className: "dhead-main" },
          React.createElement("div", { className: "dhead-l" },
            React.createElement("div", { className: "dhead-unit-row" },
              React.createElement("h1", { className: "dhead-unit" }, t.unit),
              React.createElement("span", { className: "dbadge", style: { "--st": meta.dot } },
                React.createElement("i", { className: (t.pos.moving ? "is-moving" : "") }), meta.label)),
            React.createElement("div", { className: "dhead-sub" }, t.year + " " + t.make + " " + t.model + " · " + t.type)),
          React.createElement("div", { className: "dhead-r" },
            React.createElement("a", { className: "dbtn dbtn-ghost", href: "#" },
              React.createElement(I.clipboard, { size: 15 }), "New work order"),
            React.createElement("a", { className: "dbtn dbtn-yellow", href: "#" },
              React.createElement(I.calendar, { size: 15 }), "Schedule PM"))
        )
      ),

      // top metrics
      React.createElement("div", { className: "dmetrics" },
        React.createElement(MetricCard, { icon: "gauge", label: "Odometer", value: fmt(t.odometer), unit: "mi" }),
        React.createElement(MetricCard, { icon: "calendar", label: "Next PM", value: fmt(t.nextPm), unit: "mi", note: pm.label, noteCls: pm.cls }),
        React.createElement(MetricCard, { icon: "wrench", label: "Lifetime service spend", value: money(totalSpend) }),
        React.createElement(MetricCard, { icon: "alert", label: "Incidents on record", value: t.incidents.length, note: t.incidents.length ? "see log" : "clean" }),
      ),

      React.createElement("div", { className: "dgrid" },
        // LEFT column
        React.createElement("div", { className: "dcol dcol-main" },
          // service history
          Section({ title: "Service history", icon: "history", count: t.history.length, children:
            React.createElement("div", { className: "timeline" },
              t.history.map((h, i) =>
                React.createElement("div", { key: i, className: "tl-item tl-" + h.kind.toLowerCase() },
                  React.createElement("div", { className: "tl-marker" }),
                  React.createElement("div", { className: "tl-body" },
                    React.createElement("div", { className: "tl-row1" },
                      React.createElement("span", { className: "tl-kind tl-kind-" + h.kind.toLowerCase() }, h.kind),
                      React.createElement("span", { className: "tl-date" }, fmtDate(h.date)),
                      React.createElement("span", { className: "tl-odo" }, fmt(h.odo) + " mi")),
                    React.createElement("div", { className: "tl-summary" }, h.summary),
                    React.createElement("div", { className: "tl-meta" },
                      React.createElement("span", null, React.createElement(I.user, { size: 12 }), " ", h.mechanic),
                      React.createElement("span", { className: "tl-cost" }, money(h.cost))))
                ))
            )
          }),
          // incidents
          Section({ title: "Incidents on the road", icon: "alert", count: t.incidents.length, children:
            t.incidents.length
              ? React.createElement("div", { className: "inc-list" },
                  t.incidents.map((inc, i) =>
                    React.createElement("div", { key: i, className: "inc inc-" + inc.sev },
                      React.createElement("div", { className: "inc-sev" }),
                      React.createElement("div", { className: "inc-body" },
                        React.createElement("div", { className: "inc-row1" },
                          React.createElement("b", null, inc.type),
                          React.createElement("span", { className: "inc-date" }, fmtDate(inc.date))),
                        React.createElement("div", { className: "inc-loc" },
                          React.createElement(I.pin, { size: 12 }), " ", inc.location),
                        React.createElement("div", { className: "inc-note" }, inc.note))))
                )
              : React.createElement("div", { className: "empty-note" },
                  React.createElement(I.shield, { size: 16 }), "No incidents recorded for this unit.")
          }),
        ),

        // RIGHT column
        React.createElement("div", { className: "dcol dcol-side" },
          // identity
          Section({ title: "Truck identity", icon: "truck", children:
            React.createElement("div", { className: "id-grid" },
              React.createElement(Stat, { label: "VIN", value: t.vin, mono: true }),
              React.createElement(Stat, { label: "Plate", value: t.plate, mono: true }),
              React.createElement(Stat, { label: "Year", value: t.year, mono: true }),
              React.createElement(Stat, { label: "Body type", value: t.type }),
              React.createElement(Stat, { label: "Make", value: t.make }),
              React.createElement(Stat, { label: "Model", value: t.model }),
            )
          }),
          // driver + crew
          Section({ title: "Driver & crew", icon: "user", children:
            React.createElement("div", null,
              React.createElement("div", { className: "person person-driver" },
                React.createElement("div", { className: "avatar" }, initials(t.driver)),
                React.createElement("div", null,
                  React.createElement("div", { className: "person-name" }, t.driver),
                  React.createElement("div", { className: "person-role" }, "Assigned driver")),
                React.createElement("a", { className: "person-call", href: "#" }, React.createElement(I.phone, { size: 15 }))),
              React.createElement("div", { className: "person" },
                React.createElement("div", { className: "avatar avatar-mech" }, initials(t.assignedMechanic)),
                React.createElement("div", null,
                  React.createElement("div", { className: "person-name" }, t.assignedMechanic),
                  React.createElement("div", { className: "person-role" }, "Lead mechanic on file"))),
              crewFromHistory(t).map((m, i) =>
                React.createElement("div", { key: i, className: "person person-sm" },
                  React.createElement("div", { className: "avatar avatar-sm" }, initials(m)),
                  React.createElement("div", null,
                    React.createElement("div", { className: "person-name" }, m),
                    React.createElement("div", { className: "person-role" }, "Worked on this truck"))))
            )
          }),
          // parts & warranty
          Section({ title: "Parts & warranty", icon: "box", count: t.parts.length, children:
            React.createElement("div", { className: "parts" },
              t.parts.map((p, i) =>
                React.createElement("div", { key: i, className: "part" },
                  React.createElement("div", { className: "part-main" },
                    React.createElement("div", { className: "part-name" }, p.name),
                    React.createElement("div", { className: "part-meta" }, fmtDate(p.date) + " · " + fmt(p.odo) + " mi · " + p.mechanic)),
                  React.createElement("span", { className: "part-w " + (p.active ? "w-on" : "w-off") },
                    p.active ? "Warranty to " + fmtDate(p.warrantyUntil) : "Expired")))
            )
          }),
        )
      ),

      // location + map (full width)
      Section({ title: "Current location & nearby units", icon: "map",
        right: React.createElement("div", { className: "loc-now" },
          React.createElement("i", { className: "loc-dot" + (t.pos.moving ? " is-moving" : ""), style: { background: meta.dot } }),
          t.location.label,
          t.mph ? React.createElement("span", { className: "loc-mph" }, " · " + t.mph + " mph " + t.heading) : React.createElement("span", { className: "loc-mph" }, " · parked " + t.location.since)),
        children:
        React.createElement("div", { className: "dmap-wrap" },
          React.createElement(FleetMap, { trucks, focusId: t.id, onSelect: (tr) => tr.id !== t.id && onOpen(tr) }),
          React.createElement("div", { className: "dmap-side" },
            React.createElement("div", { className: "dmap-side-h" }, "Nearest units"),
            window.FleetData.nearest(t, trucks, 5).map((n, i) =>
              React.createElement("button", { key: i, className: "near-row", onClick: () => onOpen(n.truck) },
                React.createElement("i", { className: "near-dot", style: { background: STATUS_META[n.truck.status].dot } }),
                React.createElement("span", { className: "near-unit" }, n.truck.unit),
                React.createElement("span", { className: "near-loc" }, n.truck.location.city),
                React.createElement("span", { className: "near-mi" }, n.miles + " mi"))))
        )
      })
    );
  }

  function MetricCard({ icon, label, value, unit, note, noteCls }) {
    const Ico = I[icon];
    return React.createElement("div", { className: "metric" },
      React.createElement("div", { className: "metric-ic" }, React.createElement(Ico, { size: 18 })),
      React.createElement("div", { className: "metric-tx" },
        React.createElement("div", { className: "metric-lbl" }, label),
        React.createElement("div", { className: "metric-val" }, value,
          unit ? React.createElement("span", { className: "metric-unit" }, " " + unit) : null),
        note ? React.createElement("div", { className: "metric-note " + (noteCls || "") }, note) : null));
  }

  function initials(name) {
    return name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  }
  function crewFromHistory(t) {
    const set = [...new Set(t.history.map((h) => h.mechanic))].filter((m) => m !== t.assignedMechanic);
    return set.slice(0, 3);
  }
  function fmtDate(s) {
    const d = new Date(s + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  window.TruckDetail = TruckDetail;
})();
