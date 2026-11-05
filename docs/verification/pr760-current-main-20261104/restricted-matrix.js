async(page)=>{
 const reads=[];const onRequest=r=>{if(r.method()==='GET'&&/tax-fee-settings|fleet\/companies|stripe\/connect|quickbooks\/status/.test(r.url()))reads.push(new URL(r.url()).pathname)};page.on('request',onRequest);const rows=[];
 try{
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:width===390?844:1000});await page.goto('http://127.0.0.1:5284/dashboard/settings?section=fleet');await page.getByText('Fleet configuration requires Taxes & Fees access. Ask the shop owner to grant access.',{exact:true}).waitFor();await page.reload();await page.getByText('Fleet configuration requires Taxes & Fees access. Ask the shop owner to grant access.',{exact:true}).waitFor();const c=page.locator('.db-settings-fleet-config');rows.push({width,url:page.url(),unlock:await c.getByRole('button',{name:'Unlock',exact:true}).count(),notSet:await c.getByText('Not set',{exact:true}).count(),overview:await page.getByText('Fleet Overview',{exact:true}).count(),noOverflow:await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)});
  }
  const denied=[];for(const search of ['section=payments','section=fees','section=integrations','section=unknown','stripe=return','quickbooks=connected']){await page.goto('http://127.0.0.1:5284/dashboard/settings?'+search);await page.getByRole('button',{name:'Settings section: Profile',exact:true}).waitFor();denied.push({search,profile:true})}
  await page.goto('http://127.0.0.1:5284/dashboard/settings?section=fleet');await page.getByText('Fleet configuration requires Taxes & Fees access. Ask the shop owner to grant access.',{exact:true}).waitFor();await page.screenshot({path:'/tmp/pr760-current-runtime/restricted-mobile.png',fullPage:true,animations:'disabled'});return{rows,denied,protectedReads:reads};
 }finally{page.off('request',onRequest)}
}
