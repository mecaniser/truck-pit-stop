async(page)=>{
 await page.setViewportSize({width:1440,height:1000});const rows=[];
 for(const search of ['section=fees','stripe=return','stripe=refresh','quickbooks=connected']){
  await page.goto('http://127.0.0.1:5284/dashboard/settings?'+search);await page.getByRole('heading',{name:'Payments & Accounting',exact:true}).waitFor();await page.waitForTimeout(150);const resolved=page.url();await page.reload();await page.getByRole('heading',{name:'Payments & Accounting',exact:true}).waitFor();rows.push({search,resolved,reload:page.url()});
 }
 return{rows,providerExchange:false};
}
