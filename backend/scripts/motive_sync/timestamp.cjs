// Only normalize after the visible account timezone has been verified.
function normalize(raw, zoneVerified) {
  if (!zoneVerified) return {observed_at:null,reason:'timezone_unverified'};
  const numeric=raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4}), (\d{1,2}):(\d{2}):(\d{2}) (AM|PM)$/);
  const named=raw.match(/^([A-Z][a-z]{2}) (\d{1,2}), (\d{4}), (\d{1,2}):(\d{2}) (AM|PM)$/);
  const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  if (!numeric && !named) return {observed_at:null,reason:'unsupported_format'};
  const m=numeric||named;
  const month=numeric?Number(m[1]):months.indexOf(m[1])+1;
  const day=Number(m[2]),year=Number(m[3]),hour=Number(m[4]),minute=Number(m[5]);
  const second=numeric?Number(m[6]):0,ampm=numeric?m[7]:m[6];
  if(month<1||month>12||day<1||day>31||hour<1||hour>12||minute>59||second>59) return {observed_at:null,reason:'invalid_time'};
  const h=hour%12+(ampm==='PM'?12:0);
  const local=Date.UTC(year,month-1,day,h,minute,second);
  const fmt=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'numeric',day:'numeric',hour:'numeric',minute:'numeric',second:'numeric',hourCycle:'h23'});
  const candidates=[4,5].map(offset=>local+offset*3600000).filter(ms=>{
    const parts=Object.fromEntries(fmt.formatToParts(ms).map(p=>[p.type,p.value]));
    return +parts.year===year&&+parts.month===month&&+parts.day===day&&+parts.hour===h&&+parts.minute===minute&&+parts.second===second;
  });
  if(candidates.length!==1)return {observed_at:null,reason:'ambiguous_or_nonexistent_time'};
  const from=new Date(candidates[0]).toISOString();
  return numeric?{observed_at:from,precision:'second',timezone:'America/New_York'}:{observed_at:null,observed_minute_start:from,observed_minute_end:new Date(candidates[0]+60000).toISOString(),precision:'minute',timezone:'America/New_York'};
}
module.exports={normalize};
