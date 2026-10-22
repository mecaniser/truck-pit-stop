'use strict';
// No network client. Each signing-key lookup reopens one directory-bound public snapshot.
const assert=require('node:assert/strict'),fs=require('node:fs');
const base=require('/run/clone/auth0_cached_jwks.cjs');
const DIRECTORY='/run/clone/auth0-public-keys';
function readSnapshot(directory=DIRECTORY){
 assert.equal(directory,DIRECTORY);
 const dir=fs.lstatSync(directory);assert.ok(dir.isDirectory()&&!dir.isSymbolicLink()&&(dir.mode&0o777)===0o755);
 const path=directory+'/current.json',fd=fs.openSync(path,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
 try {
  const before=fs.fstatSync(fd);assert.ok(before.isFile()&&before.nlink===1&&(before.mode&0o777)===0o644&&before.size<=65536);
  const raw=fs.readFileSync(fd),after=fs.fstatSync(fd);assert.ok(raw.length<=65536);
  for(const key of ['dev','ino','size','mtimeMs','ctimeMs','mode'])assert.equal(before[key],after[key]);
  return JSON.parse(raw);
 } finally {fs.closeSync(fd);}
}
function makeResolver(read=readSnapshot,now=()=>Date.now()){
 return options=>{
  assert.equal(options.jwksUri,base.URL);
  return {getSigningKey(kid,callback){
   try {base.resolver(read(),now)(options).getSigningKey(kid,callback);}
   catch(_){callback(new Error('Mac signing-key cache unavailable; refresh required'));}
  }};
 };
}
function install(nativeRequire){
 assert.equal(process.env.REAL_DATA_CLONE,'true');assert.equal(process.env.AUTH0_DOMAIN,base.DOMAIN);
 assert.equal(process.env.AUTH0_AUDIENCE,base.AUDIENCE);
 // Validate a current complete snapshot at startup, and again on every lookup.
 base.resolver(readSnapshot());
 const id=nativeRequire.resolve('jwks-rsa');nativeRequire.cache[id]={id,filename:id,loaded:true,exports:makeResolver()};
 base.constrainClient(nativeRequire('jsonwebtoken'));
}
module.exports={readSnapshot,makeResolver,install};
