function coordinates(raw){
 const m=raw.trim().match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
 if(!m||Math.abs(+m[1])>90||Math.abs(+m[2])>180)throw new Error('invalid_coordinates');
 return [+m[1],+m[2]];
}
async function copyFresh({clear,click,read,pause}){
 await clear();
 if(await read()!=='')throw new Error('clipboard_clear_failed');
 await click();
 for(let i=0;i<30;i++){
  const raw=await read();
  if(raw.trim())return coordinates(raw);
  await pause(100);
 }
 throw new Error('clipboard_write_timeout');
}
module.exports={coordinates,copyFresh};
