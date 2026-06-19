// ============================================================
// FleetMap — schematic regional map with truck markers
// props: trucks, focusId (optional), onSelect(truck), compact
// ============================================================
(function () {
  const { STATUS_META, HQ, nearest, dist } = window.FleetData;

  // a few schematic "highways" as polylines across the 0..100 field
  const ROADS = [
    { name: "I-77", pts: [[50, 0], [49, 30], [50, 62], [51, 100]] },
    { name: "I-85", pts: [[0, 78], [28, 70], [50, 62], [74, 50], [100, 38]] },
    { name: "I-485", pts: [[50, 62], [70, 64], [80, 50], [74, 34], [54, 30], [34, 38], [28, 56], [40, 68], [50, 62]] },
    { name: "US-74", pts: [[0, 50], [26, 56], [50, 62], [72, 70], [100, 82]] },
    { name: "I-40", pts: [[0, 18], [30, 22], [60, 16], [100, 22]] },
  ];

  function path(pts) {
    return pts.map((p, i) => (i === 0 ? "M" : "L") + p[0] + " " + p[1]).join(" ");
  }

  function FleetMap({ trucks, focusId, onSelect, compact }) {
    const [hover, setHover] = React.useState(null);
    const focus = focusId ? trucks.find((t) => t.id === focusId) : null;
    const near = focus ? nearest(focus, trucks, 3) : [];

    return React.createElement(
      "div",
      { className: "fmap" + (compact ? " fmap--compact" : "") },
      // --- the map field ---
      React.createElement(
        "div",
        { className: "fmap-field" },
        React.createElement(
          "svg",
          { className: "fmap-svg", viewBox: "0 0 100 100", preserveAspectRatio: "none" },
          // grid
          Array.from({ length: 11 }).map((_, i) =>
            React.createElement("line", { key: "gx" + i, x1: i * 10, y1: 0, x2: i * 10, y2: 100, className: "fmap-grid" })
          ),
          Array.from({ length: 11 }).map((_, i) =>
            React.createElement("line", { key: "gy" + i, x1: 0, y1: i * 10, x2: 100, y2: i * 10, className: "fmap-grid" })
          ),
          // roads
          ROADS.map((r, i) =>
            React.createElement("path", { key: "r" + i, d: path(r.pts), className: "fmap-road" })
          ),
          // distance connectors from focus -> nearest
          focus && near.map((n, i) =>
            React.createElement("line", {
              key: "c" + i,
              x1: focus.pos.x, y1: focus.pos.y, x2: n.truck.pos.x, y2: n.truck.pos.y,
              className: "fmap-link",
            })
          )
        ),
        // road labels (HTML, positioned)
        !compact && React.createElement("span", { className: "fmap-rd-label", style: { left: "51%", top: "8%" } }, "I-77"),
        !compact && React.createElement("span", { className: "fmap-rd-label", style: { left: "12%", top: "70%" } }, "I-85"),
        !compact && React.createElement("span", { className: "fmap-rd-label", style: { left: "82%", top: "78%" } }, "US-74"),

        // HQ marker
        React.createElement(
          "div",
          { className: "fmap-hq", style: { left: HQ.x + "%", top: HQ.y + "%" } },
          React.createElement("div", { className: "fmap-hq-diamond" }),
          React.createElement("span", { className: "fmap-hq-label" }, "TPS YARD")
        ),

        // distance pills at link midpoints
        focus && near.map((n, i) => {
          const mx = (focus.pos.x + n.truck.pos.x) / 2;
          const my = (focus.pos.y + n.truck.pos.y) / 2;
          return React.createElement(
            "span",
            { key: "d" + i, className: "fmap-dist", style: { left: mx + "%", top: my + "%" } },
            n.miles + " mi"
          );
        }),

        // truck markers
        trucks.map((t) => {
          const meta = STATUS_META[t.status];
          const isFocus = focus && t.id === focus.id;
          const isNear = near.some((n) => n.truck.id === t.id);
          const dim = focus && !isFocus && !isNear;
          return React.createElement(
            "button",
            {
              key: t.id,
              className: "fmap-mk" + (isFocus ? " is-focus" : "") + (dim ? " is-dim" : ""),
              style: { left: t.pos.x + "%", top: t.pos.y + "%", "--mk": meta.dot },
              onMouseEnter: () => setHover(t.id),
              onMouseLeave: () => setHover(null),
              onClick: () => onSelect && onSelect(t),
              title: t.unit + " · " + meta.label,
            },
            React.createElement("span", { className: "fmap-mk-dot" + (t.pos.moving ? " is-moving" : "") }),
            (isFocus || hover === t.id || !compact) &&
              React.createElement("span", { className: "fmap-mk-tag" }, t.unit.replace("TPS-", "")),
            hover === t.id &&
              React.createElement(
                "span",
                { className: "fmap-tip" },
                React.createElement("b", null, t.unit),
                " · " + meta.label,
                React.createElement("br", null),
                t.location.label,
                focus && t.id !== focus.id
                  ? React.createElement("span", { className: "fmap-tip-d" }, dist(focus.pos, t.pos) + " mi from " + focus.unit)
                  : null
              )
          );
        })
      ),
      // --- legend ---
      React.createElement(
        "div",
        { className: "fmap-legend" },
        Object.keys(STATUS_META).map((k) =>
          React.createElement(
            "span",
            { key: k, className: "fmap-leg" },
            React.createElement("i", { style: { background: STATUS_META[k].dot } }),
            STATUS_META[k].label
          )
        ),
        React.createElement(
          "span",
          { className: "fmap-leg fmap-leg--hq" },
          React.createElement("i", { className: "leg-diamond" }),
          "Shop / yard"
        )
      )
    );
  }

  window.FleetMap = FleetMap;
})();
