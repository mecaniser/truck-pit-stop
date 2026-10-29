import { expect,it } from 'vitest'
import { geographicClusters, milesBetween, type LocatedUnit } from '../geographicClusters'
const unit=(id:string,miles:number):LocatedUnit=>({id,point:[0,miles/3958.7613*180/Math.PI]})
it('clusters within three miles but separates units outside the threshold',()=>{
 expect(geographicClusters([unit('a',0),unit('b',2.99)]).map(g=>g.length)).toEqual([2])
 expect(geographicClusters([unit('a',0),unit('b',3.01)]).map(g=>g.length)).toEqual([1,1])
})
it('does not chain nearby trucks into a group wider than three miles',()=>{
 const input=[unit('a',0),unit('b',2),unit('c',4)]
 const groups=geographicClusters(input)
 expect(groups.map(g=>g.length)).toEqual([2,1])
 for(const g of groups)for(const a of g)for(const b of g)expect(milesBetween(a,b)).toBeLessThanOrEqual(3)
 expect(geographicClusters([...input].reverse())).toEqual(groups)
})
it('retains every coincident identity',()=>{
 expect(geographicClusters([unit('03',0),unit('532',0),unit('610',0)])[0].map(u=>u.id)).toEqual(['03','532','610'])
})
