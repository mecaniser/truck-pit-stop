import { routeLeader, type Point } from './mapLeaderRouting'

export interface HybridAnchor extends Point { id:string; width?:number; height?:number; fixed?:boolean }
export interface HybridCard extends HybridAnchor { width:number; height:number; path:Point[] }

/** Keep each badge at its own anchor. Search outward only when local space is occupied. */
export function hybridLayout(anchors:HybridAnchor[],width:number,height:number,obstacles:{x:number;y:number;width:number;height:number}[]=[]):HybridCard[]{
 const cards:HybridCard[]=anchors.filter(a=>a.fixed).map(a=>({...a,width:a.width??68,height:a.height??42,path:[]}))
 const density=(a:HybridAnchor)=>anchors.filter(b=>b!==a&&Math.hypot(a.x-b.x,a.y-b.y)<80).length
 // Reserve naturally clear positions before packing dense groups around their dots.
 const ordered=anchors.filter(a=>!a.fixed).sort((a,b)=>density(a)-density(b)||a.id.localeCompare(b.id))
 for(const a of ordered){
  const w=a.width??(a.id.length===1?36:28+a.id.length*8),h=a.height??(a.id.length===1?36:28)
  if(a.x<0||a.x>width||a.y<0||a.y>height){cards.push({...a,width:w,height:h,y:a.y-h/2-10,path:[]});continue}
  const candidate=(x:number,y:number):HybridCard=>({id:a.id,x:Math.max(w/2,Math.min(width-w/2,x)),y:Math.max(h/2,Math.min(height-h/2,y)),width:w,height:h,path:[]})
  const clear=(c:HybridCard)=>![...cards,...obstacles].some(b=>Math.abs(c.x-b.x)<(w+b.width)/2+8&&Math.abs(c.y-b.y)<(h+b.height)/2+8)
   &&!anchors.some(b=>Math.abs(c.x-b.x)<w/2+8&&Math.abs(c.y-b.y)<h/2+8)
  let best=candidate(a.x,a.y-h/2-10)
  if(!clear(best)){
   const choices:HybridCard[]=[]
   for(let radius=h/2+10;radius<=Math.hypot(width,height);radius+=6){
    for(let step=0;step<24;step++){
     const angle=-Math.PI/2+step*Math.PI/12
     const c=candidate(a.x+Math.cos(angle)*radius,a.y+Math.sin(angle)*radius)
     if(clear(c))choices.push(c)
    }
    if(choices.length)break
   }
   // Distance first; prefer above the anchor when distances are equal.
   choices.sort((b,c)=>Math.hypot(b.x-a.x,b.y-a.y)-Math.hypot(c.x-a.x,c.y-a.y)||b.y-c.y)
   if(choices.length)best=choices[0]
  }
  cards.push(best)
 }
 return cards.map(card=>({...card,path:card.fixed?[]:routeLeader(anchors.find(a=>a.id===card.id)!,card,[...obstacles,...cards.filter(c=>c.id!==card.id)])}))
}
