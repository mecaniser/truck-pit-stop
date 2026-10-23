// Seed only the new, empty synthetic source database, never a production database.
const fs=require('fs');const assert=require('node:assert/strict');const mongoose=require('mongoose');
const Parking=require('./backend/models/ParkingSpace');const Pin=require('./backend/models/Pin');const Settings=require('./backend/models/SiteSettings');
async function main(){
 const uri=new URL(process.env.MONGO_URI_DEV);assert.equal(uri.hostname,'mongo');assert.equal(uri.pathname,'/tph_backup_source');
 assert.equal(process.env.LOCAL_TEST_ONLY,'true');assert.equal(process.env.SQUARE_ENVIRONMENT,'sandbox');
 const value=JSON.parse(fs.readFileSync(0,'utf8'));assert.match(value.pin,/^[1-9][0-9]{5}$/);
 await mongoose.connect(process.env.MONGO_URI_DEV,{autoIndex:false});
 assert.equal((await mongoose.connection.db.listCollections().toArray()).length,0,'Source database is not empty');
 await Parking.create([{id:'BACKUP-REHEARSAL-001',title:'SIMULATION Synthetic Backup Parking',address:'100 Synthetic Road, Test City, NC 00000',coordinates:{lat:0,lng:0},publiclyHidden:false,availability:true,openForParking:true,openForDaily:false,openForMonthly:false,monthlySubscriptionMode:'none'},{id:'BACKUP-REHEARSAL-HIDDEN',title:'SIMULATION Hidden Parking',address:'200 Synthetic Road, Test City, NC 00000',coordinates:{lat:0,lng:0},publiclyHidden:true,availability:true,openForParking:true,openForDaily:false,openForMonthly:false,monthlySubscriptionMode:'none'}]);
 await Pin.createPin({type:'client',pin:value.pin,name:'SIMULATION Backup Manager',createdBy:'synthetic-backup-rehearsal'});
 await Settings.create({_id:'global',allowManagerAccess:true});
 // The native monthlySquareLocationId partial index uses unsupported $nin.
 // This synthetic read/PIN rehearsal creates only the valid indexes it exercises.
 await Parking.collection.createIndex({id:1},{unique:true});await Pin.collection.createIndex({type:1,enabled:1});await mongoose.disconnect();console.log(JSON.stringify({synthetic:true,locations:2,pins:1,jobs:0}));
}
main().catch(()=>{console.error('Synthetic backup seed refused');process.exit(1);});
