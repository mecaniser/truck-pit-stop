'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const base=require('../auth0_cached_jwks.cjs');
const context={module:{exports:{}},require(id){return id==='/run/clone/auth0_cached_jwks.cjs'?base:require(id);},process,Buffer};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'refreshing_jwks.cjs'),'utf8'),context);
const dynamic=context.module.exports;
const now=Date.now();
function snapshot(kid){const {publicKey}=crypto.generateKeyPairSync('rsa',{modulusLength:2048});const key={...publicKey.export({format:'jwk'}),kid,alg:'RS256',use:'sig'};
 const jwks={keys:[key]};return {version:1,url:base.URL,fetched_at:new Date(now-1000).toISOString(),valid_until:new Date(now+100000).toISOString(),jwks_sha256:crypto.createHash('sha256').update(JSON.stringify(base.canonical(jwks))).digest('hex'),jwks};}
function key(client,kid){return new Promise((resolve,reject)=>client.getSigningKey(kid,(e,value)=>e?reject(e):resolve(value)));}
test('same client reloads rotated directory snapshot without application restart',async()=>{let current=snapshot('one');const client=dynamic.makeResolver(()=>current,()=>now)({jwksUri:base.URL});assert.ok((await key(client,'one')).publicKey);current=snapshot('two');await assert.rejects(key(client,'one'));assert.ok((await key(client,'two')).publicKey);});
test('expiry fails closed without extending prior lifetime',async()=>{const current=snapshot('one');let clock=now;const client=dynamic.makeResolver(()=>current,()=>clock)({jwksUri:base.URL});await key(client,'one');clock=Date.parse(current.valid_until);await assert.rejects(key(client,'one'));});
test('missing or malformed snapshots cannot fall back to previously accepted key',async()=>{let current=snapshot('one');const client=dynamic.makeResolver(()=>current,()=>now)({jwksUri:base.URL});await key(client,'one');current={};await assert.rejects(key(client,'one'));});
test('private key and changed algorithm rejected even if snapshot hash recomputed',async()=>{for(const field of [{d:'private'},{alg:'HS256'}]){const current=snapshot('one');Object.assign(current.jwks.keys[0],field);current.jwks_sha256=crypto.createHash('sha256').update(JSON.stringify(base.canonical(current.jwks))).digest('hex');const client=dynamic.makeResolver(()=>current,()=>now)({jwksUri:base.URL});await assert.rejects(key(client,'one'));}});
test('wrong endpoint rejected before lookup',()=>assert.throws(()=>dynamic.makeResolver(()=>snapshot('one'))({jwksUri:'https://other.invalid'})));
