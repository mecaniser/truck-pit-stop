// ============================================================
// Recharts chart components — dark BlueNoir theme
// ============================================================
(function(){
  const R = Recharts;
  const D = window.AnalyticsData;

  function useAccent(){
    return React.useContext(window.__AccentCtx);
  }

  const GRID = "rgba(255,255,255,0.06)";
  const AXIS = "#6b7280";
  const TIP_STYLE = { background:"#151b26", border:"1px solid rgba(255,255,255,0.1)", borderRadius:10, fontSize:12.5, color:"#e5e7eb", padding:"8px 12px" };

  function Tip({active,payload,label,formatter}){
    if(!active || !payload || !payload.length) return null;
    return (
      <div style={TIP_STYLE}>
        <div style={{color:"#9ca3af",marginBottom:4,fontWeight:600}}>{label}</div>
        {payload.map((p,i)=>(
          <div key={i} style={{display:"flex",alignItems:"center",gap:7,marginTop:2}}>
            <span style={{width:8,height:8,borderRadius:99,background:p.color||p.fill}}></span>
            <span>{p.name}: <b style={{color:"#fff"}}>{formatter?formatter(p.value,p.name):p.value}</b></span>
          </div>
        ))}
      </div>
    );
  }

  // ---- Revenue & Profit combo ----
  function RevenueTrendChart({rows}){
    const accent = useAccent();
    return (
      <R.ResponsiveContainer width="100%" height="100%">
        <R.ComposedChart data={rows} margin={{top:6,right:10,left:-14,bottom:0}}>
          <defs>
            <linearGradient id="gPartsRev" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.9}/>
              <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.55}/>
            </linearGradient>
          </defs>
          <CartesianGridDark/>
          <R.XAxis dataKey="label" tick={{fill:AXIS,fontSize:11}} axisLine={{stroke:GRID}} tickLine={false} interval="preserveStartEnd" />
          <R.YAxis yAxisId="l" tick={{fill:AXIS,fontSize:11}} axisLine={false} tickLine={false} tickFormatter={(v)=>"$"+(v/1000)+"k"} />
          <R.YAxis yAxisId="r" orientation="right" domain={[0,60]} tick={{fill:AXIS,fontSize:11}} axisLine={false} tickLine={false} tickFormatter={(v)=>v+"%"} />
          <R.Tooltip content={<Tip formatter={(v,n)=> n==="Margin %" ? v+"%" : "$"+v.toLocaleString() } />} cursor={{fill:"rgba(255,255,255,0.03)"}} />
          <R.Bar yAxisId="l" dataKey="partsRevenue" name="Parts revenue" stackId="rev" fill="#3b82f6" radius={[0,0,0,0]} maxBarSize={26} isAnimationActive={false} />
          <R.Bar yAxisId="l" dataKey="laborRevenue" name="Labor revenue" stackId="rev" fill={accent.c500} radius={[4,4,0,0]} maxBarSize={26} isAnimationActive={false} />
          <R.Line yAxisId="r" type="monotone" dataKey="marginPct" name="Margin %" stroke="#34d399" strokeWidth={2.5} dot={false} isAnimationActive={false} />
        </R.ComposedChart>
      </R.ResponsiveContainer>
    );
  }

  function CartesianGridDark(){
    return <R.CartesianGrid stroke={GRID} vertical={false} />;
  }

  // ---- Labor vs parts profitability bubble ----
  function ProfitabilityScatter({ros}){
    const byType = {};
    ros.forEach(r=>{ (byType[r.type]=byType[r.type]||[]).push(r); });
    const palette = ["#3b82f6","#f59e0b","#34d399","#a78bfa","#f87171","#22d3ee","#fb923c","#84cc16"];
    const types = Object.keys(byType);
    return (
      <R.ResponsiveContainer width="100%" height="100%">
        <R.ScatterChart margin={{top:6,right:14,left:-8,bottom:0}}>
          <CartesianGridDark/>
          <R.XAxis type="number" dataKey="subtotal" name="RO subtotal" tick={{fill:AXIS,fontSize:11}} axisLine={{stroke:GRID}} tickLine={false} tickFormatter={(v)=>"$"+v} />
          <R.YAxis type="number" dataKey="marginPct" name="Margin %" domain={[0,60]} tick={{fill:AXIS,fontSize:11}} axisLine={false} tickLine={false} tickFormatter={(v)=>v+"%"} />
          <R.ZAxis type="number" dataKey="hours" range={[30,400]} name="Hours" />
          <R.Tooltip cursor={{strokeDasharray:"3 3"}} content={({active,payload})=>{
            if(!active||!payload||!payload.length) return null;
            const p = payload[0].payload;
            return <div style={TIP_STYLE}><b style={{color:"#fff"}}>{p.type}</b><br/>${p.subtotal.toLocaleString()} · {p.marginPct}% margin · {p.hours}h</div>;
          }} />
          <R.Legend wrapperStyle={{fontSize:11.5,color:AXIS}} iconSize={9} />
          {types.map((t,i)=>(
            <R.Scatter key={t} name={t} data={byType[t]} fill={palette[i%palette.length]} fillOpacity={0.75} isAnimationActive={false} />
          ))}
        </R.ScatterChart>
      </R.ResponsiveContainer>
    );
  }

  // ---- ranked horizontal bar ----
  function RankedBar({data, dataKey, nameKey, colorFn, tickFormatter, tooltipFormatter}){
    const accent = useAccent();
    return (
      <R.ResponsiveContainer width="100%" height="100%">
        <R.BarChart data={data} layout="vertical" margin={{top:4,right:20,left:6,bottom:0}}>
          <CartesianGridDark/>
          <R.XAxis type="number" tick={{fill:AXIS,fontSize:11}} axisLine={false} tickLine={false} tickFormatter={tickFormatter} />
          <R.YAxis type="category" dataKey={nameKey} width={78} tick={{fill:"#d1d5db",fontSize:12}} axisLine={false} tickLine={false} />
          <R.Tooltip content={<Tip formatter={tooltipFormatter} />} cursor={{fill:"rgba(255,255,255,0.03)"}} />
          <R.Bar dataKey={dataKey} radius={[0,5,5,0]} maxBarSize={18} isAnimationActive={false}>
            {data.map((d,i)=>(<R.Cell key={i} fill={colorFn ? colorFn(d) : accent.c500} />))}
          </R.Bar>
        </R.BarChart>
      </R.ResponsiveContainer>
    );
  }

  // ---- trend line ----
  function TrendLine({data, dataKey, color, yTick}){
    return (
      <R.ResponsiveContainer width="100%" height="100%">
        <R.AreaChart data={data} margin={{top:6,right:10,left:-14,bottom:0}}>
          <defs>
            <linearGradient id="gTrend" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35}/>
              <stop offset="100%" stopColor={color} stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGridDark/>
          <R.XAxis dataKey="label" tick={{fill:AXIS,fontSize:11}} axisLine={{stroke:GRID}} tickLine={false} />
          <R.YAxis tick={{fill:AXIS,fontSize:11}} axisLine={false} tickLine={false} tickFormatter={yTick} />
          <R.Tooltip content={<Tip formatter={(v)=>yTick?yTick(v):v} />} />
          <R.Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2.5} fill="url(#gTrend)" isAnimationActive={false} />
        </R.AreaChart>
      </R.ResponsiveContainer>
    );
  }

  // ---- stacked bar (PM vs unplanned) ----
  function StackedBar({rows}){
    return (
      <R.ResponsiveContainer width="100%" height="100%">
        <R.BarChart data={rows} margin={{top:6,right:10,left:-14,bottom:0}}>
          <CartesianGridDark/>
          <R.XAxis dataKey="label" tick={{fill:AXIS,fontSize:11}} axisLine={{stroke:GRID}} tickLine={false} />
          <R.YAxis tick={{fill:AXIS,fontSize:11}} axisLine={false} tickLine={false} tickFormatter={(v)=>"$"+(v/1000)+"k"} />
          <R.Tooltip content={<Tip formatter={(v)=>"$"+v.toLocaleString()} />} cursor={{fill:"rgba(255,255,255,0.03)"}} />
          <R.Legend wrapperStyle={{fontSize:11.5,color:AXIS}} iconSize={9} />
          <R.Bar dataKey="pm" name="Preventive" stackId="s" fill="#34d399" radius={[0,0,0,0]} maxBarSize={30} isAnimationActive={false} />
          <R.Bar dataKey="unplanned" name="Unplanned" stackId="s" fill="#f87171" radius={[4,4,0,0]} maxBarSize={30} isAnimationActive={false} />
        </R.BarChart>
      </R.ResponsiveContainer>
    );
  }

  // ---- quadrant scatter (parts markup vs turnover) ----
  function QuadrantScatter({parts}){
    const medT = median(parts.map(p=>p.turnover));
    const medM = median(parts.map(p=>p.markup));
    const colorFor = (p)=> p.turnover>=medT && p.markup>=medM ? "#34d399" : p.turnover<medT && p.markup<medM ? "#f87171" : "#f59e0b";
    return (
      <R.ResponsiveContainer width="100%" height="100%">
        <R.ScatterChart margin={{top:6,right:14,left:-8,bottom:0}}>
          <CartesianGridDark/>
          <R.XAxis type="number" dataKey="turnover" name="Turnover" tick={{fill:AXIS,fontSize:11}} axisLine={{stroke:GRID}} tickLine={false} tickFormatter={(v)=>v.toFixed(1)+"x"} />
          <R.YAxis type="number" dataKey="markup" name="Markup %" tick={{fill:AXIS,fontSize:11}} axisLine={false} tickLine={false} tickFormatter={(v)=>v+"%"} />
          <R.ReferenceLine x={medT} stroke={GRID} strokeDasharray="3 3" />
          <R.ReferenceLine y={medM} stroke={GRID} strokeDasharray="3 3" />
          <R.Tooltip content={({active,payload})=>{
            if(!active||!payload||!payload.length) return null;
            const p = payload[0].payload;
            return <div style={TIP_STYLE}><b style={{color:"#fff"}}>{p.name}</b><br/>{p.turnover.toFixed(1)}x turns · {p.markup}% markup</div>;
          }} />
          <R.Scatter data={parts} isAnimationActive={false}>
            {parts.map((p,i)=>(<R.Cell key={i} fill={colorFor(p)} fillOpacity={0.85} />))}
          </R.Scatter>
        </R.ScatterChart>
      </R.ResponsiveContainer>
    );
  }
  function median(arr){ const s=[...arr].sort((a,b)=>a-b); const m=Math.floor(s.length/2); return s.length%2? s[m] : (s[m-1]+s[m])/2; }

  // ---- Pareto ----
  function ParetoChart({accounts}){
    const accent = useAccent();
    const data = accounts.map(a=>({ name:a.name.split(" ")[0], revenue:a.revenue, cumPct:a.cumPct }));
    return (
      <R.ResponsiveContainer width="100%" height="100%">
        <R.ComposedChart data={data} margin={{top:6,right:10,left:-14,bottom:0}}>
          <CartesianGridDark/>
          <R.XAxis dataKey="name" tick={{fill:AXIS,fontSize:10.5}} axisLine={{stroke:GRID}} tickLine={false} interval={0} angle={-25} textAnchor="end" height={46} />
          <R.YAxis yAxisId="l" tick={{fill:AXIS,fontSize:11}} axisLine={false} tickLine={false} tickFormatter={(v)=>"$"+(v/1000)+"k"} />
          <R.YAxis yAxisId="r" orientation="right" domain={[0,100]} tick={{fill:AXIS,fontSize:11}} axisLine={false} tickLine={false} tickFormatter={(v)=>v+"%"} />
          <R.Tooltip content={<Tip formatter={(v,n)=> n==="cumPct" ? v+"%" : "$"+v.toLocaleString()} />} cursor={{fill:"rgba(255,255,255,0.03)"}} />
          <R.Bar yAxisId="l" dataKey="revenue" name="Revenue" fill={accent.c500} radius={[4,4,0,0]} maxBarSize={30} isAnimationActive={false} />
          <R.Line yAxisId="r" type="monotone" dataKey="cumPct" name="Cumulative %" stroke="#a78bfa" strokeWidth={2.2} dot={{r:3,fill:"#a78bfa"}} isAnimationActive={false} />
        </R.ComposedChart>
      </R.ResponsiveContainer>
    );
  }

  // ---- Funnel (native Recharts) ----
  function QuoteFunnel({funnel}){
    const stages = [
      {name:"Sent", value:funnel.sent, fill:"#6b7280"},
      {name:"Viewed", value:funnel.viewed, fill:"#3b82f6"},
      {name:"Approved", value:funnel.approved, fill:"#f59e0b"},
      {name:"Invoiced", value:funnel.invoiced, fill:"#34d399"},
    ];
    return (
      <R.ResponsiveContainer width="100%" height="100%">
        <R.FunnelChart margin={{top:6,right:20,left:20,bottom:6}}>
          <R.Tooltip content={({active,payload})=>{
            if(!active||!payload||!payload.length) return null;
            const p = payload[0].payload;
            return <div style={TIP_STYLE}><b style={{color:"#fff"}}>{p.name}</b>: {p.value}</div>;
          }} />
          <R.Funnel dataKey="value" data={stages} isAnimationActive={false}>
            <R.LabelList position="right" fill="#e5e7eb" stroke="none" dataKey="name" fontSize={12.5} />
            <R.LabelList position="left" fill="#9ca3af" stroke="none" dataKey="value" fontSize={12.5} />
          </R.Funnel>
        </R.FunnelChart>
      </R.ResponsiveContainer>
    );
  }

  window.RC = {
    RevenueTrendChart, ProfitabilityScatter, RankedBar, TrendLine, StackedBar,
    QuadrantScatter, ParetoChart, QuoteFunnel,
  };
})();
