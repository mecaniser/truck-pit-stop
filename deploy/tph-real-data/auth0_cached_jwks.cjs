'use strict';
// Clone-only public-key resolver. Native JWT signature/issuer/audience checks remain authoritative.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const DOMAIN = 'dev-wp1mdcmju5ix3zgt.us.auth0.com';
const URL = `https://${DOMAIN}/.well-known/jwks.json`;
const AUDIENCE = 'https://trucksparkinghub.com/api';
const CLIENT = 'vdyn414odhKwyDvsiNCSssA0In0Lc1i2';
const MAX_AGE = 24 * 60 * 60 * 1000;
function canonical(value) {
 if (Array.isArray(value)) return value.map(canonical);
 if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]));
 return value;
}
function resolver(snapshot, now=()=>Date.now()) {
 assert.equal(snapshot.version,1); assert.equal(snapshot.url,URL);
 const start=Date.parse(snapshot.fetched_at), end=Date.parse(snapshot.valid_until);
 assert.ok(Number.isFinite(start) && Number.isFinite(end) && end>start && end-start<=MAX_AGE);
 assert.equal(crypto.createHash('sha256').update(JSON.stringify(canonical(snapshot.jwks))).digest('hex'),snapshot.jwks_sha256);
 assert.ok(snapshot.jwks && Array.isArray(snapshot.jwks.keys) && snapshot.jwks.keys.length>0 && snapshot.jwks.keys.length<=16);
 const keys=new Map();
 for(const jwk of snapshot.jwks.keys) {
  assert.equal(jwk.kty,'RSA'); assert.equal(jwk.use,'sig'); assert.equal(jwk.alg,'RS256');
  assert.ok(typeof jwk.kid==='string' && /^[A-Za-z0-9_+/.=-]{1,256}$/.test(jwk.kid) && !keys.has(jwk.kid));
  assert.ok(typeof jwk.n==='string' && /^[A-Za-z0-9_-]+$/.test(jwk.n));
  assert.ok(typeof jwk.e==='string' && /^[A-Za-z0-9_-]+$/.test(jwk.e));
  for(const privateField of ['d','p','q','dp','dq','qi','oth','k']) assert.ok(!(privateField in jwk));
  const publicKey=crypto.createPublicKey({key:{kty:'RSA',n:jwk.n,e:jwk.e},format:'jwk'});
  assert.ok(publicKey.asymmetricKeyType==='rsa' && publicKey.asymmetricKeyDetails.modulusLength>=2048);
  keys.set(jwk.kid,publicKey.export({type:'spki',format:'pem'}));
 }
 const current=()=>{assert.ok(now()>=start-30000 && now()<end,'cached signing keys expired or not yet valid');};
 current();
 return options=>{
  assert.equal(options.jwksUri,URL);
  return {getSigningKey(kid,callback){
   try {current();assert.ok(typeof kid==='string' && keys.has(kid),'unknown signing key');callback(null,{publicKey:keys.get(kid)});}
   catch(_){callback(new Error('Mac signing-key cache unavailable; operator refresh required'));}
  }};
 };
}
function constrainClient(jwt) {
 const verify=jwt.verify;
 jwt.verify=function(token,key,options,callback){
  if(options && options.issuer===`https://${DOMAIN}/` && options.audience===AUDIENCE) {
   assert.deepEqual(options.algorithms,['RS256']); assert.equal(typeof callback,'function');
   return verify.call(this,token,key,options,(error,decoded)=>{
    if(error)return callback(error);
    if(!decoded || decoded.azp!==CLIENT)return callback(new Error('Wrong Mac login client'));
    return callback(null,decoded);
   });
  }
  return verify.apply(this,arguments);
 };
}
function install(nativeRequire) {
 assert.equal(process.env.REAL_DATA_CLONE,'true');
 assert.equal(process.env.AUTH0_DOMAIN,DOMAIN); assert.equal(process.env.AUTH0_AUDIENCE,AUDIENCE);
 const path='/run/clone/auth0-jwks.json';
 const stat=fs.lstatSync(path);assert.ok(stat.isFile() && !stat.isSymbolicLink() && stat.size<=262144);
 const makeClient=resolver(JSON.parse(fs.readFileSync(path,'utf8')));
 const id=nativeRequire.resolve('jwks-rsa');
 nativeRequire.cache[id]={id,filename:id,loaded:true,exports:makeClient};
 constrainClient(nativeRequire('jsonwebtoken'));
}
module.exports={resolver,constrainClient,install,canonical,DOMAIN,URL,AUDIENCE,CLIENT};
