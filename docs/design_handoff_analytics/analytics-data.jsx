// ============================================================
// Analytics — mock data layer (deterministic)
// ============================================================
(function(){
  function mulberry32(a){return function(){a|=0;a=(a+0x6D2B79F5)|0;let t=Math.imul(a^(a>>>15),1|a);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296;};}
  const rnd = mulberry32(77241);
  const pick = (a)=>a[Math.floor(rnd()*a.length)];
  const between = (lo,hi)=>lo+Math.floor(rnd()*(hi-lo+1));
  const betweenF = (lo,hi)=>lo+rnd()*(hi-lo);

  const TODAY = new Date(2026,6,10);
  function dayLabel(d){return d.toLocaleDateString("en-US",{month:"short",day:"numeric"});}
  function monthLabel(d){return d.toLocaleDateString("en-US",{month:"short"});}

  // ---------- 1. Daily revenue/cost series, 120 days ----------
  const DAYS = 120;
  const daily = [];
  let basePartsRev = 1400, baseLaborRev = 1100;
  for(let i=DAYS-1;i>=0;i--){
    const d = new Date(TODAY); d.setDate(d.getDate()-i);
    const dow = d.getDay();
    const wkdWeight = (dow===0||dow===6) ? 0.35 : 1;
    const seasonal = 1 + 0.18*Math.sin((DAYS-i)/18);
    const noise = betweenF(0.75,1.28);
    const partsRevenue = Math.round(basePartsRev*wkdWeight*seasonal*noise);
    const laborRevenue = Math.round(baseLaborRev*wkdWeight*seasonal*noise*betweenF(0.85,1.15));
    const partsCost = Math.round(partsRevenue*betweenF(0.58,0.68));
    const laborCost = Math.round(laborRevenue*betweenF(0.38,0.48));
    const revenue = partsRevenue+laborRevenue;
    const cost = partsCost+laborCost;
    const profit = revenue-cost;
    daily.push({ date:d.toISOString().slice(0,10), label:dayLabel(d), partsRevenue, laborRevenue, revenue, partsCost, laborCost, cost, profit, marginPct: revenue? Math.round(profit/revenue*1000)/10 : 0 });
    // slow upward drift
    if(i%14===0){ basePartsRev *= 1.015; baseLaborRev *= 1.012; }
  }
  function rollup(range){
    const n = range==="7d"?7:range==="30d"?30:range==="90d"?90:120;
    const slice = daily.slice(-n);
    const bucket = n<=30 ? "day" : n<=90 ? "week" : "month";
    let groups;
    if(bucket==="day") groups = slice.map(d=>({label:d.label, ...d}));
    else {
      const size = bucket==="week"?7:30;
      groups=[];
      for(let i=0;i<slice.length;i+=size){
        const chunk = slice.slice(i,i+size);
        const sum=(k)=>chunk.reduce((a,c)=>a+c[k],0);
        const revenue=sum("revenue"), profit=sum("profit");
        groups.push({label: bucket==="week" ? ("Wk "+(Math.floor(i/size)+1)) : monthLabel(new Date(chunk[0].date+"T00:00:00")),
          partsRevenue:sum("partsRevenue"), laborRevenue:sum("laborRevenue"), revenue, profit,
          marginPct: revenue? Math.round(profit/revenue*1000)/10:0 });
      }
    }
    return groups;
  }
  function totals(range){
    const n = range==="7d"?7:range==="30d"?30:range==="90d"?90:120;
    const slice = daily.slice(-n);
    const sum=(k)=>slice.reduce((a,c)=>a+c[k],0);
    const revenue=sum("revenue"), profit=sum("profit"), cost=sum("cost");
    const prevSlice = daily.slice(-2*n,-n);
    const prevRevenue = prevSlice.reduce((a,c)=>a+c.revenue,0) || revenue;
    return { revenue, profit, cost, marginPct: revenue? Math.round(profit/revenue*1000)/10:0,
      revChangePct: Math.round(((revenue-prevRevenue)/Math.max(1,prevRevenue))*1000)/10 };
  }

  // ---------- 2. Repair orders (labor vs parts profitability bubbles) ----------
  const RO_TYPES = ["PM Service","Brake Job","Engine Diagnostic","Electrical","Tire & Wheel","Cooling System","Transmission","DOT Inspection"];
  const ROS = Array.from({length:70}).map((_,i)=>{
    const hours = betweenF(0.5,9);
    const subtotal = Math.round(hours*100 + between(60,1400));
    const marginPct = Math.round(betweenF(8,52));
    return { id:"RO-"+(4000+i), type:pick(RO_TYPES), subtotal, hours:Math.round(hours*10)/10, marginPct };
  });

  // ---------- 3. Technicians ----------
  const TECHS = [
    {name:"Mike Doyle"}, {name:"Stas Ruban"}, {name:"Roman Lutz"},
    {name:"Danny Cho"}, {name:"Greg Olsen"}, {name:"Ivan Petrenko"},
  ].map(t=>{
    const available = 84; // 2-week
    const billed = Math.round(available*betweenF(0.52,0.97));
    return { ...t, available, billed, eff: Math.round(billed/available*1000)/10 };
  }).sort((a,b)=>b.eff-a.eff);

  // ---------- 4. Fleet cost per truck + trend ----------
  const TRUCK_UNITS = Array.from({length:14}).map((_,i)=>"TPS-"+(101+i));
  const TRUCKS_COST = TRUCK_UNITS.map(u=>{
    const ytd = between(2200,15800);
    const miles = between(38000,96000);
    return { unit:u, ytd, miles, perMile: Math.round((ytd/miles)*1000)/1000 };
  }).sort((a,b)=>b.ytd-a.ytd);
  const fleetCostPerMileTrend = Array.from({length:12}).map((_,i)=>{
    const d = new Date(2025,6+i,1);
    const drift = 0.18 + i*0.006;
    return { label: monthLabel(d), value: Math.round((drift+betweenF(-0.015,0.02))*1000)/1000 };
  });

  // ---------- 5. PM vs unplanned repair cost, monthly ----------
  const pmVsUnplanned = Array.from({length:8}).map((_,i)=>{
    const d = new Date(2025,10+i,1);
    const pm = between(4200,7200);
    const unplanned = Math.round(pm*betweenF(0.35, i>5?0.95:0.55));
    return { label: monthLabel(d), pm, unplanned };
  });

  // ---------- 6. Parts markup & turnover (quadrant) ----------
  const PART_NAMES = ["Oil Filter","Brake Pads","Air Dryer Cart.","Alternator","Water Pump","DEF Fluid","Wiper Blades","U-Joint","Fuel Filter","Turbo Seal Kit","Wheel Bearing","Clutch Kit","Radiator","ABS Sensor","Shock Absorber","Air Bag Spring","Starter Motor","EGR Cooler","Belt Tensioner","Fan Clutch"];
  const PARTS_QUAD = PART_NAMES.map(n=>({
    name:n, turnover: betweenF(0.4,9.5), markup: Math.round(betweenF(8,85)),
  }));

  // ---------- 7. Quote funnel ----------
  const funnel = { sent: 214, viewed: 176, approved: 132, invoiced: 121, avgApproveHrs: 6.4 };

  // ---------- 8. Customer / fleet accounts ----------
  const ACCOUNTS = [
    "Elis Logistica","Palmetto Freight Co.","Redline Trucking","Carolina Bulk Haul","Anchor Line Transport",
    "Blue Ridge Freightways","Summit Fleet Services","Iron Horse Carriers","Coastal Express Lines","Piedmont Haulers",
  ].map(name=>{
    const revenue = between(3200,48000);
    const marginPct = between(14,44);
    const trend = Array.from({length:8}).map(()=>between(60,100));
    return { name, revenue, marginPct, trend };
  }).sort((a,b)=>b.revenue-a.revenue);
  const acctTotal = ACCOUNTS.reduce((a,c)=>a+c.revenue,0);
  let cum=0;
  ACCOUNTS.forEach(a=>{ cum+=a.revenue; a.cumPct = Math.round(cum/acctTotal*1000)/10; });

  window.AnalyticsData = {
    daily, rollup, totals, ROS, TECHS, TRUCKS_COST, fleetCostPerMileTrend,
    pmVsUnplanned, PARTS_QUAD, funnel, ACCOUNTS,
    money:(n)=> "$"+Math.round(n).toLocaleString("en-US"),
    moneyK:(n)=> "$"+(n/1000).toFixed(1)+"k",
    fmt:(n)=>Math.round(n).toLocaleString("en-US"),
  };
})();
