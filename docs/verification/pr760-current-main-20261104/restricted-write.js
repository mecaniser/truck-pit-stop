async(page)=>{
 const result=await page.evaluate(async()=>{const{default:api}=await import('/src/lib/api.ts');try{const r=await api.put('/admin/tax-fee-settings',{sales_tax_rate:11,shop_supplies_rate:12,service_fee_rate:13,labor_rate:1000,internal_labor_rate:100,fleet_company_name:'RESTRICTED MUST NOT SAVE',default_fleet_authority_customer_id:null});return{status:r.status,data:r.data}}catch(e){return{status:e.response?.status,detail:e.response?.data?.detail}}});if(result.status!==403)throw new Error('Expected restricted403');return result;
}
