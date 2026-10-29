export interface LocatedUnit { id:string; point:[number,number] }
export function milesBetween(a:LocatedUnit,b:LocatedUnit){
 const rad=Math.PI/180,lat=(b.point[1]-a.point[1])*rad,lng=(b.point[0]-a.point[0])*rad
 const h=Math.sin(lat/2)**2+Math.cos(a.point[1]*rad)*Math.cos(b.point[1]*rad)*Math.sin(lng/2)**2
 return 3958.7613*2*Math.asin(Math.sqrt(Math.min(1,h)))
}
/** Complete-link membership prevents a chain from spanning more than three miles. */
export function geographicClusters<T extends LocatedUnit>(units:T[]):T[][]{
 const groups:T[][]=[]
 for(const unit of [...units].sort((a,b)=>a.id.localeCompare(b.id))){
  const group=groups.find(g=>g.every(other=>milesBetween(unit,other)<=3))
  if(group)group.push(unit);else groups.push([unit])
 }
 return groups
}
