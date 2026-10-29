import { describe, expect, it } from 'vitest'
import { hybridLayout } from '../hybridLayout'

describe('local badge placement',()=>{
 it('keeps isolated labels immediately above their own anchors',()=>{
  const cards=hybridLayout([{id:'728',x:100,y:100},{id:'8',x:400,y:300}],600,500)
  expect(cards.find(c=>c.id==='728')).toMatchObject({x:100,y:76})
  expect(cards.find(c=>c.id==='8')).toMatchObject({x:400,y:272})
 })
 it('retains coincident units without overlapping cards or hiding their dot',()=>{
  const anchors=['03','532','610','70','26','4'].map(id=>({id,x:220,y:220}))
  const cards=hybridLayout(anchors,500,500)
  expect(cards).toHaveLength(anchors.length)
  for(const a of cards){
   expect(a.path.length).toBeGreaterThan(1)
   expect(a.path[0]).toMatchObject({x:220,y:220})
   for(const b of cards.filter(b=>b.id!==a.id))expect(Math.abs(a.x-b.x)>=(a.width+b.width)/2||Math.abs(a.y-b.y)>=(a.height+b.height)/2).toBe(true)
  }
 })
})

it('anchors a cluster in place and reserves its space for nearby labels',()=>{
 const cards=hybridLayout([{id:'cluster',x:200,y:200,width:68,height:42,fixed:true},{id:'70',x:210,y:210}],500,500)
 const cluster=cards.find(c=>c.id==='cluster')!,unit=cards.find(c=>c.id==='70')!
 expect(cluster).toMatchObject({x:200,y:200,path:[]})
 expect(Math.abs(unit.x-cluster.x)>=(unit.width+cluster.width)/2||Math.abs(unit.y-cluster.y)>=(unit.height+cluster.height)/2).toBe(true)
})
