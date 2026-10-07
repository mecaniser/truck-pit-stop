const assert=require('node:assert/strict');
const {copyFresh}=require('./copy_coordinates.cjs');
(async()=>{
 let clipboard='35,-80',poll=0,clicked=false;
 const pair=await copyFresh({clear:async()=>{clipboard='';},click:async()=>{clicked=true;},read:async()=>{if(clicked&&++poll===3)clipboard='36,-81';return clipboard;},pause:async()=>{}});
 assert.deepEqual(pair,[36,-81]);
 await assert.rejects(copyFresh({clear:async()=>{},click:async()=>{},read:async()=>'35,-80',pause:async()=>{}}),/clipboard_clear_failed/);
 await assert.rejects(copyFresh({clear:async()=>{},click:async()=>{},read:async()=>'',pause:async()=>{}}),/clipboard_write_timeout/);
 let clicked2=false;
 await assert.rejects(copyFresh({clear:async()=>{},click:async()=>{clicked2=true;},read:async()=>clicked2?'not coordinates':'',pause:async()=>{}}),/invalid_coordinates/);
 console.log('4 fresh-copy assertions passed');
})();
