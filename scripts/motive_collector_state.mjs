/** Private atomic checkpoints; no browser secrets belong in this state. */
import {mkdir,open,rename,readFile,unlink,lstat} from 'node:fs/promises';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
export async function openState(directory) {
 await mkdir(directory,{recursive:true,mode:0o700});
 const info=await lstat(directory);
 if(!info.isDirectory() || info.isSymbolicLink() || (info.mode & 0o077)) throw new Error('State directory must be private (0700)');
 const lock=join(directory,'collector.lock');
 const handle=await open(lock,'wx',0o600);
 await handle.writeFile(JSON.stringify({pid:process.pid,created_at:new Date().toISOString()}));await handle.close();
 const valid=name=>{if(!/^[a-z0-9][a-z0-9.-]*\.json$/.test(name))throw new Error('Invalid checkpoint name');return join(directory,name);};
 return {
  async read(name){return JSON.parse(await readFile(valid(name),'utf8'));},
  async write(name,value){const target=valid(name),tmp=target+'.'+randomUUID()+'.tmp';const h=await open(tmp,'wx',0o600);try{await h.writeFile(JSON.stringify(value));await h.sync();}finally{await h.close();}await rename(tmp,target);},
  async close(){await unlink(lock);}
 };
}
