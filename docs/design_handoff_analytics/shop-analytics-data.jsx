// ============================================================
// Mock data shaped exactly like the real Reports* response types
// ============================================================
(function(){
  function mulberry32(a){return function(){a|=0;a=(a+0x6D2B79F5)|0;let t=Math.imul(a^(a>>>15),1|a);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296;};}
  const rnd = mulberry32(90210);
  const between = (lo,hi)=>lo+Math.floor(rnd()*(hi-lo+1));
  const betweenF = (lo,hi)=>lo+rnd()*(hi-lo);
  const pick = (a)=>a[Math.floor(rnd()*a.length)];

  function trend(n, base, vol){
    const labels = n<=8 ? ["W1","W2","W3","W4","W5","W6","W7","W8"].slice(0,n) : Array.from({length:n}).map((_,i)=>"D"+(i+1));
    let v = base;
    return labels.map(label=>{ v = Math.max(0, v*betweenF(1-vol,1+vol)); return { label, value: String(Math.round(v*100)/100) }; });
  }

  function dashboard(range){
    const n = range==="this_week"||range==="last_week" ? 7 : 8;
    return {
      range_start:"2026-06-01", range_end:"2026-07-10",
      revenue: { value: String(between(38000,72000)), trend: trend(n,6500,0.28) },
      labor_revenue: { value: String(between(14000,28000)), trend: trend(n,2800,0.3) },
      part_revenue: { value: String(between(16000,32000)), trend: trend(n,3200,0.3) },
      fees_revenue: { value: String(between(1200,3400)), trend: trend(n,320,0.35) },
      parts_profit: { value: String(between(6000,14000)), trend: trend(n,1200,0.32) },
      inventory_value: { value: String(between(48000,86000)), trend: [] },
      invoiced_hours: { value: String(between(320,640)), trend: trend(n,68,0.25) },
      part_sales_finalized: { value: String(between(180,420)), trend: trend(n,42,0.3) },
      services_finalized: { value: String(between(140,320)), trend: trend(n,32,0.28) },
    };
  }

  const CUSTOMERS = ["Elis Logistica","Palmetto Freight Co.","Redline Trucking","Carolina Bulk Haul","Anchor Line Transport","Blue Ridge Freightways","Summit Fleet Services","Iron Horse Carriers"];
  function sales(){
    const rows = CUSTOMERS.map((name,i)=>{
      const labor = betweenF(1800,9200), parts = betweenF(2200,11000), fees = betweenF(80,340);
      const salesTax = (labor+parts+fees)*0.07;
      const discounts = betweenF(0,600);
      const net = labor+parts+fees+salesTax-discounts;
      return { group_key:"c"+i, group_label:name, labor:labor.toFixed(2), parts:parts.toFixed(2), fees:fees.toFixed(2), sales_tax:salesTax.toFixed(2), discounts:discounts.toFixed(2), net_sales:net.toFixed(2) };
    }).sort((a,b)=>parseFloat(b.net_sales)-parseFloat(a.net_sales));
    const sum=(k)=>rows.reduce((a,r)=>a+parseFloat(r[k]),0);
    return { summary:{ net_sales:sum("net_sales").toFixed(2), labor:sum("labor").toFixed(2), parts:sum("parts").toFixed(2), discounts:sum("discounts").toFixed(2), fees:sum("fees").toFixed(2), sales_tax:sum("sales_tax").toFixed(2) }, rows };
  }

  const FEE_NAMES = ["Shop Supplies Fee","Hazmat Disposal","Diagnostic Fee","Environmental Fee","Rush Service Fee"];
  function fees(){
    const rows = FEE_NAMES.map(name=>{
      const times = between(8,64); const avg = betweenF(12,55);
      return { fee_name:name, times_added:times, average_charge:avg.toFixed(2), total_charged:(times*avg).toFixed(2) };
    });
    return { times_added: rows.reduce((a,r)=>a+r.times_added,0), average_charge:(rows.reduce((a,r)=>a+parseFloat(r.average_charge),0)/rows.length).toFixed(2), total_charged: rows.reduce((a,r)=>a+parseFloat(r.total_charged),0).toFixed(2), rows };
  }

  function tax(){
    const rows = [
      {rate_label:"NC State Sales Tax", percentage:"4.75", },
      {rate_label:"Mecklenburg County", percentage:"2.00"},
      {rate_label:"Local Transit Tax", percentage:"0.50"},
    ].map(r=>({...r, tax_collected: betweenF(1200,4800).toFixed(2)}));
    return { rows };
  }

  function parts(){
    const rows = Array.from({length:14}).map((_,i)=>{
      const revenue = betweenF(180,2400); const cost = revenue*betweenF(0.55,0.75); const profit = revenue-cost;
      return { invoice_number:"INV-"+(5100+i), revenue:revenue.toFixed(2), cost:cost.toFixed(2), profit:profit.toFixed(2), margin_pct:(profit/revenue*100).toFixed(1) };
    }).sort((a,b)=>parseFloat(b.revenue)-parseFloat(a.revenue));
    const revenue = rows.reduce((a,r)=>a+parseFloat(r.revenue),0);
    const cost = rows.reduce((a,r)=>a+parseFloat(r.cost),0);
    const profit = revenue-cost;
    return { revenue:revenue.toFixed(2), cost:cost.toFixed(2), profit:profit.toFixed(2), margin_pct:(profit/revenue*100).toFixed(1), rows };
  }

  const PART_NAMES = ["Oil Filter","Brake Pads (Set)","Air Dryer Cartridge","Alternator","Water Pump","DEF Fluid (2.5gal)","Wiper Blades","U-Joint","Fuel Filter","Turbo Seal Kit","Wheel Bearing","Clutch Kit","Radiator","ABS Sensor","Shock Absorber","Air Bag Spring","Starter Motor","EGR Cooler","Belt Tensioner","Fan Clutch"];
  function inventory(){
    const rows = PART_NAMES.map((name,i)=>{
      const qty = between(2,48); const unitCost = betweenF(8,340);
      return { sku:"SKU-"+(1000+i), name, quantity:String(qty), unit_cost:unitCost.toFixed(2), total_value:(qty*unitCost).toFixed(2) };
    }).sort((a,b)=>parseFloat(b.total_value)-parseFloat(a.total_value));
    const total = rows.reduce((a,r)=>a+parseFloat(r.total_value),0);
    return { part_value: total.toFixed(2), total_value: total.toFixed(2), rows };
  }

  const SERVICE_NAMES = ["PM Service — Level A","PM Service — Level B","Brake Job","Engine Diagnostic","Electrical Repair","Tire & Wheel Service","Cooling System Service","Transmission Service","DOT Inspection","Clutch Replacement"];
  function serviceTypes(){
    const rows = SERVICE_NAMES.map(name=>{
      const qty = between(4,58); const hrs = qty*betweenF(0.8,3.2);
      return { name, quantity:qty, hours_billed:hrs.toFixed(1), total_charged:(hrs*betweenF(95,130)).toFixed(2) };
    }).sort((a,b)=>parseFloat(b.total_charged)-parseFloat(a.total_charged));
    return { service_items: rows.reduce((a,r)=>a+r.quantity,0), hours_billed: rows.reduce((a,r)=>a+parseFloat(r.hours_billed),0).toFixed(1), total_charged: rows.reduce((a,r)=>a+parseFloat(r.total_charged),0).toFixed(2), rows };
  }

  function fleetInvoices(){
    return Array.from({length:9}).map((_,i)=>({
      id:"fi"+i, invoice_number:"INT-"+(2200+i), repair_order_id:"ro"+i, order_number:"RO-"+(4000+i),
      status: pick(["completed","invoiced","paid"]), total_amount: betweenF(120,1800),
      created_at: new Date(2026,5,between(1,30)).toISOString(),
      unit_number:"TPS-"+(101+i), vehicle_label: pick(["Freightliner Cascadia","Volvo VNL 760","Kenworth T680","Peterbilt 579"]),
    }));
  }

  window.ShopAnalyticsData = { dashboard, sales, fees, tax, parts, inventory, serviceTypes, fleetInvoices };
})();
