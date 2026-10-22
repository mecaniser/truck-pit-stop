'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const {resolver,constrainClient,canonical,URL,DOMAIN,AUDIENCE,CLIENT}=require('./auth0_cached_jwks.cjs');
const {publicKey,privateKey}=crypto.generateKeyPairSync('rsa',{modulusLength:2048});
const jwk={...publicKey.export({format:'jwk'}),kid:'test-only-public-key',alg:'RS256',use:'sig'};
const now=Date.now();
function snapshot(keys=[jwk]){const jwks={keys};return {version:1,url:URL,fetched_at:new Date(now-1000).toISOString(),valid_until:new Date(now+3600000).toISOString(),jwks,jwks_sha256:crypto.createHash('sha256').update(JSON.stringify(canonical(jwks))).digest('hex')};}
function resolve(factory,kid){return new Promise((resolve,reject)=>factory({jwksUri:URL}).getSigningKey(kid,(e,k)=>e?reject(e):resolve(k)));}
test('exact trusted public key verifies real RSA signature; no signing key supplied',async()=>{const key=await resolve(resolver(snapshot(),()=>now),jwk.kid);const message=Buffer.from('local fixture only');assert.ok(crypto.verify('RSA-SHA256',message,key.publicKey,crypto.sign('RSA-SHA256',message,privateKey)));});
test('unknown kid fails closed',async()=>assert.rejects(resolve(resolver(snapshot(),()=>now),'other')));
test('expired cache refuses startup',()=>assert.throws(()=>resolver(snapshot(),()=>now+7200000)));
test('cache expires after startup without network fallback',async()=>{let clock=now;const f=resolver(snapshot(),()=>clock);clock+=7200000;await assert.rejects(resolve(f,jwk.kid));});
test('wrong origin, algorithm, private keys and duplicate ids refused',()=>{for(const s of [snapshot([{...jwk,alg:'HS256'}]),snapshot([{...jwk,d:'private'}]),snapshot([jwk,jwk]),{...snapshot(),url:'https://example.com/keys'}])assert.throws(()=>resolver(s,()=>now));});
test('cache fingerprint and lifetime tampering refused',()=>{assert.throws(()=>resolver({...snapshot(),jwks_sha256:'0'.repeat(64)},()=>now));assert.throws(()=>resolver({...snapshot(),valid_until:new Date(now+2*86400000).toISOString()},()=>now));});
test('unexpected JWKS URL never receives keys',()=>assert.throws(()=>resolver(snapshot(),()=>now)({jwksUri:'http://127.0.0.1/'})));
test('wrong client rejected only after native verifier succeeds',async()=>{let nativeCalls=0;const jwt={verify(t,k,o,cb){nativeCalls++;cb(null,{azp:'wrong'});}};constrainClient(jwt);await assert.rejects(new Promise((resolve,reject)=>jwt.verify('fixture',null,{issuer:`https://${DOMAIN}/`,audience:AUDIENCE,algorithms:['RS256']},(e,d)=>e?reject(e):resolve(d))));assert.equal(nativeCalls,1);});
test('native verification failure preserved and manager verification unchanged',()=>{const error=new Error('signature failed');const jwt={verify(t,k,o,cb){return cb(error);}};constrainClient(jwt);jwt.verify('fixture',null,{issuer:`https://${DOMAIN}/`,audience:AUDIENCE,algorithms:['RS256']},e=>assert.equal(e,error));jwt.verify('fixture',null,{issuer:'rstc-manager-auth'},e=>assert.equal(e,error));});
test('exact client accepted only with native successful decoded claims',()=>{const jwt={verify(t,k,o,cb){cb(null,{azp:CLIENT,role:'fixture'});}};constrainClient(jwt);jwt.verify('fixture',null,{issuer:`https://${DOMAIN}/`,audience:AUDIENCE,algorithms:['RS256']},(e,d)=>{assert.ifError(e);assert.equal(d.azp,CLIENT);});});
const nativeModules=process.env.TPH_NATIVE_NODE_MODULES;
test('native jsonwebtoken verifies signed fixture and rejects issuer/audience/expiry/client/signature failures',{skip:!nativeModules},async()=>{
 const native=require(nativeModules+'/jsonwebtoken');const jwt={verify:native.verify};constrainClient(jwt);
 const keys=resolver(snapshot(),()=>now)({jwksUri:URL});
 const getKey=(header,callback)=>keys.getSigningKey(header.kid,(e,key)=>callback(e,key?.publicKey));
 const options={issuer:`https://${DOMAIN}/`,audience:AUDIENCE,algorithms:['RS256']};
 const make=(claims={},extra={})=>native.sign({azp:CLIENT,...claims},privateKey,{algorithm:'RS256',issuer:options.issuer,audience:AUDIENCE,expiresIn:60,keyid:jwk.kid,...extra});
 const verify=token=>new Promise((resolve,reject)=>jwt.verify(token,getKey,options,(e,d)=>e?reject(e):resolve(d)));
 assert.equal((await verify(make())).azp,CLIENT);
 for(const token of [make({azp:'other'}),make({}, {issuer:'https://wrong.invalid/'}),make({}, {audience:'wrong'}),make({}, {expiresIn:-10}),make().replace(/.$/,'!')]) await assert.rejects(verify(token));
});
