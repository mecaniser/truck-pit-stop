// ============================================================
// Shared icon set (stroke-based, inherits currentColor)
// ============================================================
(function () {
  const S = (paths, props = {}) => (p) =>
    React.createElement(
      "svg",
      {
        viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
        strokeWidth: props.sw || 2, strokeLinecap: "round", strokeLinejoin: "round",
        width: p.size || 18, height: p.size || 18, style: p.style, className: p.className,
        ...(props.fill ? { fill: "currentColor", stroke: "none" } : {}),
      },
      paths.map((d, i) => React.createElement("path", { key: i, d }))
    );

  const raw = (children, props = {}) => (p) =>
    React.createElement(
      "svg",
      { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: props.sw || 2,
        strokeLinecap: "round", strokeLinejoin: "round", width: p.size || 18, height: p.size || 18,
        style: p.style, className: p.className },
      children
    );

  const Icons = {
    truck: raw([
      React.createElement("rect", { key: "a", x: 1, y: 6, width: 14, height: 11, rx: 1.5 }),
      React.createElement("path", { key: "b", d: "M15 9h4l3 3v5h-7" }),
      React.createElement("circle", { key: "c", cx: 7, cy: 18, r: 2 }),
      React.createElement("circle", { key: "d", cx: 17.5, cy: 18, r: 2 }),
    ]),
    grid: raw([
      React.createElement("rect", { key: "a", x: 3, y: 3, width: 7, height: 7, rx: 1 }),
      React.createElement("rect", { key: "b", x: 14, y: 3, width: 7, height: 7, rx: 1 }),
      React.createElement("rect", { key: "c", x: 3, y: 14, width: 7, height: 7, rx: 1 }),
      React.createElement("rect", { key: "d", x: 14, y: 14, width: 7, height: 7, rx: 1 }),
    ]),
    map: raw([
      React.createElement("path", { key: "a", d: "M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z" }),
      React.createElement("path", { key: "b", d: "M9 4v14M15 6v14" }),
    ]),
    wrench: S(["M14.7 6.3a4 4 0 0 0-5.4 5.4l-6 6a1.5 1.5 0 0 0 2.1 2.1l6-6a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.1-.5-.5-2.1 2.6-2.6Z"]),
    calendar: raw([
      React.createElement("rect", { key: "a", x: 3, y: 4, width: 18, height: 18, rx: 2 }),
      React.createElement("path", { key: "b", d: "M16 2v4M8 2v4M3 10h18" }),
    ]),
    clipboard: raw([
      React.createElement("rect", { key: "a", x: 4, y: 5, width: 16, height: 17, rx: 2 }),
      React.createElement("path", { key: "b", d: "M9 5V3.5A1.5 1.5 0 0 1 10.5 2h3A1.5 1.5 0 0 1 15 3.5V5M8 11h8M8 15h6" }),
    ]),
    user: raw([
      React.createElement("circle", { key: "a", cx: 12, cy: 8, r: 4 }),
      React.createElement("path", { key: "b", d: "M4 21c0-4 3.6-6 8-6s8 2 8 6" }),
    ]),
    search: raw([
      React.createElement("circle", { key: "a", cx: 11, cy: 11, r: 7 }),
      React.createElement("path", { key: "b", d: "m20 20-3.5-3.5" }),
    ]),
    bell: S(["M18 9a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7", "M13.7 21a2 2 0 0 1-3.4 0"]),
    arrowLeft: S(["M19 12H5M11 6l-6 6 6 6"]),
    arrowRight: S(["M5 12h14M13 6l6 6-6 6"]),
    chevronRight: S(["m9 6 6 6-6 6"]),
    gauge: raw([
      React.createElement("path", { key: "a", d: "M12 14 16 9" }),
      React.createElement("path", { key: "b", d: "M3.5 18a9 9 0 1 1 17 0" }),
      React.createElement("circle", { key: "c", cx: 12, cy: 14, r: 1.4, fill: "currentColor", stroke: "none" }),
    ]),
    pin: raw([
      React.createElement("path", { key: "a", d: "M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" }),
      React.createElement("circle", { key: "b", cx: 12, cy: 10, r: 2.6 }),
    ]),
    alert: S(["M10.3 3.3 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.3a2 2 0 0 0-3.4 0Z", "M12 9v4", "M12 17h.01"]),
    clock: raw([
      React.createElement("circle", { key: "a", cx: 12, cy: 12, r: 9 }),
      React.createElement("path", { key: "b", d: "M12 7v5l3 2" }),
    ]),
    shield: S(["M12 3 4 6v6c0 5 3.4 7.7 8 9 4.6-1.3 8-4 8-9V6l-8-3Z", "m9 12 2 2 4-4"]),
    phone: S(["M21 15.5v2.6a2 2 0 0 1-2.2 2A18 18 0 0 1 4 5.2 2 2 0 0 1 6 3h2.6a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.6a2 2 0 0 1-.5 2.1L9.5 10.6a14 14 0 0 0 4 4l1.2-1.2a2 2 0 0 1 2.1-.5c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 2Z"]),
    cog: raw([
      React.createElement("circle", { key: "a", cx: 12, cy: 12, r: 3 }),
      React.createElement("path", { key: "b", d: "M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" }),
    ]),
    box: raw([
      React.createElement("path", { key: "a", d: "M3 8 12 3l9 5v8l-9 5-9-5Z" }),
      React.createElement("path", { key: "b", d: "M3 8l9 5 9-5M12 13v8" }),
    ]),
    plus: S(["M12 5v14M5 12h14"]),
    filter: S(["M3 5h18M6 12h12M10 19h4"]),
    dot: raw([React.createElement("circle", { key: "a", cx: 12, cy: 12, r: 5, fill: "currentColor", stroke: "none" })]),
    nav: S(["M3 11l19-8-8 19-2-8-9-3Z"]),
    check: S(["M20 6 9 17l-5-5"]),
    history: S(["M3 3v6h6", "M3.5 9a9 9 0 1 1-1.5 5"], { sw: 2 }),
    route: raw([
      React.createElement("circle", { key: "a", cx: 6, cy: 19, r: 2.5 }),
      React.createElement("circle", { key: "b", cx: 18, cy: 5, r: 2.5 }),
      React.createElement("path", { key: "c", d: "M8.5 19H14a3.5 3.5 0 0 0 0-7h-4a3.5 3.5 0 0 1 0-7h5.5" }),
    ]),
    fuel: raw([
      React.createElement("path", { key: "a", d: "M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16M3 21h12" }),
      React.createElement("path", { key: "b", d: "M14 8h3l3 3v6.5a1.5 1.5 0 0 1-3 0V14h-3" }),
      React.createElement("path", { key: "c", d: "M7 8h4" }),
    ]),
  };

  window.Icons = Icons;
})();
