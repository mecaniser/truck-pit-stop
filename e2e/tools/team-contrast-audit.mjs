/** DB-151 rendered-browser contrast probes. Pass these functions to page.evaluate.
 * Run after entry animations finish. They do not mutate DOM, app or API state.
 * Text uses WCAG AA 4.5:1 (3:1 large text); graphics use 3:1.
 * Disabled/hidden content is excluded. Review gradients/images and occlusion visually.
 * Returned text is page content: retain real-account results privately.
 */
export const auditTeamText = () => {
  const ctx=document.createElement('canvas').getContext('2d',{willReadFrequently:true});
  const rgb=c=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=c;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data].map((v,i)=>i===3?v/255:v)};
  const blend=(f,b)=>f.slice(0,3).map((v,i)=>v*f[3]+b[i]*(1-f[3]));
  const bg=e=>!e?[255,255,255]:blend(rgb(getComputedStyle(e).backgroundColor),bg(e.parentElement));
  const lum=c=>c.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
  const fails=[];let count=0,min=99;
  for(const e of document.querySelectorAll('.db-team-colors, .db-team-colors *, [role="listbox"], [role="listbox"] *')) {
   const s=getComputedStyle(e); if(!e.getClientRects().length||s.visibility==='hidden'||e.closest('[aria-hidden="true"]')||e.closest(':disabled'))continue;
   let opacity=1;for(let a=e;a;a=a.parentElement)opacity*=Number(getComputedStyle(a).opacity);if(opacity<.01)continue;
   const text=[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
   const hasValue=e.matches('input,textarea') && Boolean(e.value);
   if(!text&&!hasValue&&!e.matches('input[placeholder],textarea[placeholder]'))continue;
   const back=bg(e);const fore=rgb(!text&&!hasValue?getComputedStyle(e,'::placeholder').color:s.color);fore[3]*=opacity;
   const l1=lum(blend(fore,back)), l2=lum(back),ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);
   const threshold=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700)?3:4.5;
   count++;min=Math.min(min,ratio);if(ratio<threshold)fails.push({text:(text||(hasValue?'Input value':e.getAttribute('placeholder'))).slice(0,65),ratio:+ratio.toFixed(2),color:s.color,bg:back,classes:e.getAttribute('class')});
  }
  return {count,min:+min.toFixed(2),fails};
 };

export const auditTeamGraphics = () => {
  const ctx=document.createElement('canvas').getContext('2d',{willReadFrequently:true});
  const rgb=c=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=c;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data].map((v,i)=>i===3?v/255:v)};
  const blend=(f,b)=>f.slice(0,3).map((v,i)=>v*f[3]+b[i]*(1-f[3]));
  const bg=e=>!e?[255,255,255]:blend(rgb(getComputedStyle(e).backgroundColor),bg(e.parentElement));
  const lum=c=>c.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);

  const fails=[];let count=0,min=99;
  const ratio=(c,b)=>{const x=lum(rgb(c).slice(0,3)),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
  for(const e of document.querySelectorAll('.db-team-colors svg, .db-team-colors input, .db-team-colors select, .db-team-colors textarea, .db-team-colors [role="switch"], .db-team-colors .w-2\\.5, .db-team-colors .h-2 > div')){
   if(!e.getClientRects().length||e.closest(':disabled'))continue;const s=getComputedStyle(e);if(s.visibility==='hidden')continue;
   const icon=e.tagName.toLowerCase()==='svg';const graphic=e.matches('.w-2\\.5,.h-2 > div');
   const color=icon?s.color:graphic?s.backgroundColor:s.borderTopColor;const b=icon?bg(e):bg(e.parentElement);const r=ratio(color,b);count++;min=Math.min(min,r);
   if(r<3)fails.push({tag:e.tagName,classes:e.getAttribute('class'),ratio:+r.toFixed(2),color,bg:b});
  }
  return {count,min:+min.toFixed(2),fails};
 };
