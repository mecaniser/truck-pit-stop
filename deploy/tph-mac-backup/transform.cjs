// Rewrite only the accepted synthetic image's exact browser origin.
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
const before='https://tph-test.elisprotech.com';
const after='http://localhost:18310';let count=0;
function walk(dir) {for(const ent of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,ent.name);if(ent.isSymbolicLink())throw Error('symlink_refused');if(ent.isDirectory())walk(file);else if(/\.(js|html|css|json)$/.test(file)){const raw=fs.readFileSync(file,'utf8');if(raw.includes(before)){count+=raw.split(before).length-1;fs.writeFileSync(file,raw.split(before).join(after));}}}}
walk('/usr/src/app/build');assert(count>0,'Expected accepted public API origin');
const file='/usr/src/app/backend/server.js';const raw=fs.readFileSync(file,'utf8');
const marker="origin === 'https://tph-test.elisprotech.com'";
assert.equal(raw.split(marker).length,2,'Expected one guarded test origin');
fs.writeFileSync(file,raw.replace(marker,"origin === 'http://localhost:18310'"));
console.log('Synthetic rehearsal origin adapted');
