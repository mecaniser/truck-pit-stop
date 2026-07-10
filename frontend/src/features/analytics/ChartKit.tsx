import { ReactNode } from 'react'
import {
  ResponsiveContainer, ComposedChart, BarChart, AreaChart, ScatterChart, FunnelChart,
  Bar, Line, Area, Scatter, Funnel, Cell, LabelList,
  XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
} from 'recharts'
import { useTheme } from '../../contexts/ThemeContext'
import { SERIES, STATUS, CHART, categoricalColor } from './chartTheme'

/**
 * Shared, themed Recharts kit for the analytics surfaces. Every series sets
 * isAnimationActive={false} (renders in final state — required for correct
 * screenshot/PDF export, per the design handoff). Colours come from the
 * validated palette in chartTheme.ts; the primary series follows the user's
 * accent via useTheme().
 */

// ---- Card wrapper (matches GarageAnalyticsPage's card class) ----
export function ChartCard({
  title, subtitle, action, height = 260, fit = false, children,
}: {
  title: string; subtitle?: string; action?: ReactNode; height?: number
  /** When true the plot area grows to fit its content (min-height) instead of a
   *  fixed height — use for content-sized layouts like the ranked bar list, so
   *  the first row isn't clipped by an overflowing fixed-height container. */
  fit?: boolean; children: ReactNode
}) {
  return (
    <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-gray-400">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div style={fit ? { minHeight: height } : { height }}>{children}</div>
    </div>
  )
}

// ---- Shared tooltip ----
// Recharts v3 doesn't cleanly expose payload/label on the custom-content type,
// so we type the runtime shape locally. `content` accepts any element, so this
// is passed as a render function below and cast where needed.
type TipFormatter = (value: number, name: string) => string
type TipEntry = { name?: string; value?: number; color?: string; fill?: string; payload?: unknown }
type TipProps = { active?: boolean; label?: string | number; payload?: TipEntry[] }
function ChartTip({ active, payload, label, formatter }: TipProps & { formatter?: TipFormatter }) {
  if (!active || !payload || !payload.length) return null
  return (
    <div style={{
      background: CHART.tooltipBg, border: CHART.tooltipBorder, borderRadius: 10,
      fontSize: 12.5, color: CHART.tooltipText, padding: '8px 12px',
    }}>
      {label != null && <div style={{ color: CHART.tooltipMuted, marginBottom: 4, fontWeight: 600 }}>{label}</div>}
      {payload.map((p, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 7, marginTop: 2 }}>
          <span style={{ width: 8, height: 8, borderRadius: 99, background: (p.color || p.fill) as string }} />
          <span>{p.name}: <b style={{ color: '#fff' }}>{formatter && p.value != null ? formatter(p.value, p.name ?? '') : p.value}</b></span>
        </div>
      ))}
    </div>
  )
}
// Render-prop wrapper so we can pass our typed tooltip to Recharts' `content`.
const tip = (formatter?: TipFormatter) => (props: object) => <ChartTip {...(props as TipProps)} formatter={formatter} />

const axisTick = { fill: CHART.axis, fontSize: 11 }
const Grid = () => <CartesianGrid stroke={CHART.grid} vertical={false} />
const money = (v: number) => '$' + v.toLocaleString()
const moneyK = (v: number) => '$' + (v / 1000) + 'k'
const pct = (v: number) => v + '%'

// ---- Revenue & Profit combo: stacked parts+labor bars + margin % line ----
export function RevenueTrendChart({ rows }: { rows: { label: string; partsRevenue: number; laborRevenue: number; marginPct: number }[] }) {
  const { accentColors } = useTheme()
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 6, right: 10, left: -14, bottom: 0 }}>
        <Grid />
        <XAxis dataKey="label" tick={axisTick} axisLine={{ stroke: CHART.grid }} tickLine={false} interval="preserveStartEnd" />
        <YAxis yAxisId="l" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={moneyK} />
        <YAxis yAxisId="r" orientation="right" domain={[0, 60]} tick={axisTick} axisLine={false} tickLine={false} tickFormatter={pct} />
        <Tooltip content={tip((v, n) => (n === "Margin %" ? pct(v) : money(v)))} cursor={{ fill: CHART.cursorFill }} />
        <Legend wrapperStyle={{ fontSize: 11.5, color: CHART.axis }} iconSize={9} />
        <Bar yAxisId="l" dataKey="partsRevenue" name="Parts revenue" stackId="rev" fill={SERIES.parts} maxBarSize={26} isAnimationActive={false} />
        <Bar yAxisId="l" dataKey="laborRevenue" name="Labor revenue" stackId="rev" fill={accentColors[500]} radius={[4, 4, 0, 0]} maxBarSize={26} isAnimationActive={false} />
        <Line yAxisId="r" type="monotone" dataKey="marginPct" name="Margin %" stroke={SERIES.margin} strokeWidth={2.5} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ---- Profitability bubble scatter (colour by category, legend = secondary encoding) ----
export function ProfitabilityScatter({ ros }: { ros: { type: string; subtotal: number; marginPct: number; hours: number }[] }) {
  const byType: Record<string, typeof ros> = {}
  ros.forEach((r) => { (byType[r.type] = byType[r.type] || []).push(r) })
  const types = Object.keys(byType)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 6, right: 14, left: -8, bottom: 0 }}>
        <Grid />
        <XAxis type="number" dataKey="subtotal" name="RO subtotal" tick={axisTick} axisLine={{ stroke: CHART.grid }} tickLine={false} tickFormatter={(v) => '$' + v} />
        <YAxis type="number" dataKey="marginPct" name="Margin %" domain={[0, 60]} tick={axisTick} axisLine={false} tickLine={false} tickFormatter={pct} />
        <ZAxis type="number" dataKey="hours" range={[30, 400]} name="Hours" />
        <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ active, payload }) => {
          if (!active || !payload || !payload.length) return null
          const p = payload[0].payload as typeof ros[number]
          return <div style={{ background: CHART.tooltipBg, border: CHART.tooltipBorder, borderRadius: 10, fontSize: 12.5, color: CHART.tooltipText, padding: '8px 12px' }}>
            <b style={{ color: '#fff' }}>{p.type}</b><br />${p.subtotal.toLocaleString()} · {p.marginPct}% margin · {p.hours}h
          </div>
        }} />
        <Legend wrapperStyle={{ fontSize: 11.5, color: CHART.axis }} iconSize={9} />
        {types.map((t, i) => (
          <Scatter key={t} name={t} data={byType[t]} fill={categoricalColor(i)} fillOpacity={0.78} isAnimationActive={false} />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  )
}

// ---- Ranked horizontal bar ----
/**
 * Ranked horizontal bars as an HTML list: each row is a single-line label on
 * the dark surface (always high-contrast — never white-on-green) above a
 * proportional magnitude bar with its value at the end. Labels never wrap; the
 * full name is in the row's title tooltip. This reads far cleaner than labels
 * painted inside a light-coloured bar, and gives comfortable row spacing.
 */
export function RankedBar<T extends Record<string, unknown>>({
  data, dataKey, nameKey, colorFn, tickFormatter, accent,
}: {
  data: T[]; dataKey: string; nameKey: string
  colorFn?: (d: T) => string; tickFormatter?: (v: number) => string
  /** Bar fill; defaults to the user's theme accent. */
  accent?: string
  /** kept for API compatibility; unused in the HTML variant */
  tooltipFormatter?: TipFormatter
}) {
  const { accentColors } = useTheme()
  const barColor = accent ?? accentColors[500]
  const valueFmt = tickFormatter ?? ((v: number) => String(v))
  const max = Math.max(...data.map((d) => Number(d[dataKey]) || 0), 1)

  return (
    <div className="flex flex-col gap-4">
      {data.map((d, i) => {
        const value = Number(d[dataKey]) || 0
        const name = String(d[nameKey] ?? '')
        const width = Math.max(2, (value / max) * 100)
        const fill = colorFn ? colorFn(d) : barColor
        return (
          <div key={i} title={name} className="min-w-0">
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <span className="truncate text-[12.5px] font-medium text-gray-200">{name}</span>
              <span className="shrink-0 font-['JetBrains_Mono',monospace] text-xs text-gray-400">{valueFmt(value)}</span>
            </div>
            <div className="h-2 w-full rounded-full bg-white/5">
              <div className="h-full rounded-full" style={{ width: `${width}%`, background: fill }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ---- Trend area ----
export function TrendArea({ data, dataKey, color, yTick }: {
  data: { label: string }[]; dataKey: string; color?: string; yTick?: (v: number) => string
}) {
  const { accentColors } = useTheme()
  const stroke = color || accentColors[500]
  const gid = `gTrend-${dataKey}`
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 6, right: 10, left: -14, bottom: 0 }}>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
            <stop offset="100%" stopColor={stroke} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Grid />
        <XAxis dataKey="label" tick={axisTick} axisLine={{ stroke: CHART.grid }} tickLine={false} />
        <YAxis tick={axisTick} axisLine={false} tickLine={false} tickFormatter={yTick} />
        <Tooltip content={tip((v) => (yTick ? yTick(v) : String(v)))} />
        <Area type="monotone" dataKey={dataKey} stroke={stroke} strokeWidth={2.5} fill={`url(#${gid})`} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ---- Stacked bar (e.g. PM vs unplanned) ----
export function StackedBar({ rows }: { rows: { label: string; pm: number; unplanned: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 6, right: 10, left: -14, bottom: 0 }}>
        <Grid />
        <XAxis dataKey="label" tick={axisTick} axisLine={{ stroke: CHART.grid }} tickLine={false} />
        <YAxis tick={axisTick} axisLine={false} tickLine={false} tickFormatter={moneyK} />
        <Tooltip content={tip(money)} cursor={{ fill: CHART.cursorFill }} />
        <Legend wrapperStyle={{ fontSize: 11.5, color: CHART.axis }} iconSize={9} />
        <Bar dataKey="pm" name="Preventive" stackId="s" fill={STATUS.good} maxBarSize={30} isAnimationActive={false} />
        <Bar dataKey="unplanned" name="Unplanned" stackId="s" fill={STATUS.bad} radius={[4, 4, 0, 0]} maxBarSize={30} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}

// ---- Quadrant scatter (median reference lines split into 4; status-coloured) ----
function median(arr: number[]): number {
  const s = [...arr].sort((a, b) => a - b); const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}
export function QuadrantScatter({ parts }: { parts: { name: string; turnover: number; markup: number }[] }) {
  const medT = median(parts.map((p) => p.turnover))
  const medM = median(parts.map((p) => p.markup))
  const colorFor = (p: { turnover: number; markup: number }) =>
    p.turnover >= medT && p.markup >= medM ? STATUS.good
      : p.turnover < medT && p.markup < medM ? STATUS.bad : STATUS.mixed
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 6, right: 14, left: -8, bottom: 0 }}>
        <Grid />
        <XAxis type="number" dataKey="turnover" name="Turnover" tick={axisTick} axisLine={{ stroke: CHART.grid }} tickLine={false} tickFormatter={(v) => v.toFixed(1) + 'x'} />
        <YAxis type="number" dataKey="markup" name="Markup %" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={pct} />
        <ReferenceLine x={medT} stroke={CHART.grid} strokeDasharray="3 3" />
        <ReferenceLine y={medM} stroke={CHART.grid} strokeDasharray="3 3" />
        <Tooltip content={({ active, payload }) => {
          if (!active || !payload || !payload.length) return null
          const p = payload[0].payload as { name: string; turnover: number; markup: number }
          return <div style={{ background: CHART.tooltipBg, border: CHART.tooltipBorder, borderRadius: 10, fontSize: 12.5, color: CHART.tooltipText, padding: '8px 12px' }}>
            <b style={{ color: '#fff' }}>{p.name}</b><br />{p.turnover.toFixed(1)}x turns · {p.markup}% markup
          </div>
        }} />
        <Scatter data={parts} isAnimationActive={false}>
          {parts.map((p, i) => <Cell key={i} fill={colorFor(p)} fillOpacity={0.85} />)}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  )
}

// ---- Pareto: revenue bars + cumulative % line ----
export function ParetoChart({ accounts }: { accounts: { name: string; revenue: number; cumPct: number }[] }) {
  const { accentColors } = useTheme()
  const data = accounts.map((a) => ({ name: a.name.split(' ')[0], revenue: a.revenue, cumPct: a.cumPct }))
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 6, right: 10, left: -14, bottom: 0 }}>
        <Grid />
        <XAxis dataKey="name" tick={{ fill: CHART.axis, fontSize: 10.5 }} axisLine={{ stroke: CHART.grid }} tickLine={false} interval={0} angle={-25} textAnchor="end" height={46} />
        <YAxis yAxisId="l" tick={axisTick} axisLine={false} tickLine={false} tickFormatter={moneyK} />
        <YAxis yAxisId="r" orientation="right" domain={[0, 100]} tick={axisTick} axisLine={false} tickLine={false} tickFormatter={pct} />
        <Tooltip content={tip((v, n) => (n === "Cumulative %" ? pct(v) : money(v)))} cursor={{ fill: CHART.cursorFill }} />
        <Legend wrapperStyle={{ fontSize: 11.5, color: CHART.axis }} iconSize={9} />
        <Bar yAxisId="l" dataKey="revenue" name="Revenue" fill={accentColors[500]} radius={[4, 4, 0, 0]} maxBarSize={30} isAnimationActive={false} />
        <Line yAxisId="r" type="monotone" dataKey="cumPct" name="Cumulative %" stroke={SERIES.cumulative} strokeWidth={2.2} dot={{ r: 3, fill: SERIES.cumulative }} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ---- Quote → approval funnel ----
export function QuoteFunnel({ funnel }: { funnel: { sent: number; viewed?: number; approved: number; invoiced: number } }) {
  // "Viewed" is optional — the app doesn't record a quote-view event yet, so
  // that stage is only shown when the data provides it.
  const stages = [
    { name: 'Sent', value: funnel.sent, fill: SERIES.neutral },
    ...(funnel.viewed != null ? [{ name: 'Viewed', value: funnel.viewed, fill: SERIES.parts }] : []),
    { name: 'Approved', value: funnel.approved, fill: STATUS.mixed },
    { name: 'Invoiced', value: funnel.invoiced, fill: STATUS.good },
  ]
  return (
    <ResponsiveContainer width="100%" height="100%">
      {/* Extra right margin so the in-segment "Name — value" labels never clip. */}
      <FunnelChart margin={{ top: 6, right: 8, left: 8, bottom: 6 }}>
        <Tooltip content={({ active, payload }) => {
          if (!active || !payload || !payload.length) return null
          const p = payload[0].payload as { name: string; value: number }
          return <div style={{ background: CHART.tooltipBg, border: CHART.tooltipBorder, borderRadius: 10, fontSize: 12.5, color: CHART.tooltipText, padding: '8px 12px' }}>
            <b style={{ color: '#fff' }}>{p.name}</b>: {p.value}
          </div>
        }} />
        <Funnel dataKey="value" data={stages} isAnimationActive={false}>
          {/* Name + value together, centred inside the segment — never spills off
              the edge or collides with the funnel taper. */}
          <LabelList
            position="center" stroke="none" fontSize={12.5} fontWeight={600}
            content={(p: object) => {
              const { x = 0, y = 0, width = 0, height = 0, value, index = 0 } =
                p as { x?: number; y?: number; width?: number; height?: number; value?: number; index?: number }
              const stage = stages[index]
              if (!stage) return null
              return (
                <text x={x + width / 2} y={y + height / 2} textAnchor="middle" dominantBaseline="central" fill="#fff" fontSize={12.5} fontWeight={600}>
                  {stage.name} · {value}
                </text>
              )
            }}
          />
        </Funnel>
      </FunnelChart>
    </ResponsiveContainer>
  )
}
