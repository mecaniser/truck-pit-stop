"""Fixed isolated TPH rehearsal specification, with no production connection."""
import copy
import os
from pathlib import Path
import re
from urllib.parse import urlunsplit

ROOT=Path.home()/'mac-hosting/tph-backup-rehearsal-v3'
PROJECT='macapps-tph-backup-rehearsal-v3'
SOURCE='b369e9f5e28584ba99f1cbe35d8f65080a51aeda'
BASE='sha256:95df264063f3224f9a2519fd68a99e537f7a8da26d17ff78b5e6a87267a798b0'
MONGO='sha256:c53852c00c23ca9f23fc39690350ffa9a80e3642fe8f96879726d8da0abe80a7'
OWNER='tph-backup-rehearsal-v1'


def specification(images,uid,gid):
    if set(images)!={'app','router'} or any(not re.fullmatch(r'sha256:[a-f0-9]{64}',v) for v in images.values()):raise RuntimeError('Immutable rehearsal images required')
    common={'networks':['isolated'],'restart':'no','cpus':0.5,'pids_limit':128,'security_opt':['no-new-privileges:true'],'cap_drop':['ALL'],'labels':{'io.macapps.backup-rehearsal':OWNER},'logging':{'driver':'json-file','options':{'max-size':'2m','max-file':'2'}}}
    env={'LOCAL_TEST_ONLY':'true','NODE_ENV':'production','SQUARE_ENVIRONMENT':'sandbox','MONGO_URI_DEV':urlunsplit(('mongodb','rehearsal:${MONGO_PASSWORD:?required}@mongo:27017','/tph_backup_restored','authSource=admin','')),'DISABLE_SCHEDULER':'true','WORKOS_ENABLED':'false','WORKOS_TENANT_AUTH_ENABLED':'false','WORKOS_IDENTITY_EVENTS_WORKER_ENABLED':'false','MANAGER_JWT_SECRET':'${MANAGER_SECRET:?required}','JWT_SECRET':'${JWT_SECRET:?required}','ADMIN_API_KEY':'${ADMIN_SECRET:?required}','SQUARE_ACCESS_TOKEN':'LOCAL_TEST_INVALID_NOT_A_PROVIDER_CREDENTIAL','AUTH0_DOMAIN':'auth.tph.invalid','AUTH0_AUDIENCE':'https://tph.invalid','LOCAL_SOURCE_SHA':SOURCE,'REHEARSAL_CONTROL_TOKEN':'${CONTROL_TOKEN:?required}','REHEARSAL_AUTHORITY':'${AUTHORITY:?required}','LOG_LEVEL':'error'}
    for key in ('ADMIN_SMS_ENABLED','ADMIN_PAYMENT_SMS_ENABLED','ERROR_ALERTS_ENABLED','ERROR_ALERTS_SMS_ENABLED','PERF_SLO_ALERTS_ENABLED','FACEBOOK_ENABLED'):env[key]='false'
    app={**common,'image':images['app'],'user':'node','read_only':True,'environment':env,'mem_limit':'512m','tmpfs':['/tmp:size=32m,mode=1777','/usr/src/app/backend/logs:rw,noexec,nosuid,size=16777216,uid=1000,gid=1000,mode=0700'],'healthcheck':{'test':['CMD','node','-e',"fetch('http://127.0.0.1:5051/ready').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"],'interval':'5s','timeout':'4s','retries':20}}
    sites={}
    for site in ('railway-simulation','mac-backup'):
        value=copy.deepcopy(app);value['environment']['REHEARSAL_SITE']=site;sites[site]=value
    return {'name':PROJECT,'services':{
      'mongo':{**common,'image':MONGO,'user':'999:999','mem_limit':'512m','command':['mongod','--wiredTigerCacheSizeGB','0.25','--bind_ip_all'],'environment':{'MONGO_INITDB_ROOT_USERNAME':'rehearsal','MONGO_INITDB_ROOT_PASSWORD':'${MONGO_PASSWORD:?required}'},'volumes':['mongo:/data/db','mongo_config:/data/configdb'],'healthcheck':{'test':['CMD','mongosh','--quiet','--eval','quit(db.adminCommand({ping:1}).ok?0:1)'],'interval':'5s','timeout':'4s','retries':25}},
      **sites,
      'router':{**common,'image':images['router'],'user':str(uid)+':'+str(gid),'mem_limit':'192m','read_only':True,'tmpfs':['/tmp:size=16m,mode=1777'],'ports':['127.0.0.1:18310:18310'],'volumes':['./private/state:/state:rw'],'environment':{'REHEARSAL_CONTROL_TOKEN':'${CONTROL_TOKEN:?required}'},'healthcheck':{'test':['CMD','python','-c',"import urllib.request;urllib.request.urlopen('http://127.0.0.1:18310/__backup/status',timeout=3)"],'interval':'5s','timeout':'4s','retries':20}}
    },'networks':{'isolated':{'internal':True}},'volumes':{'mongo':{},'mongo_config':{}}}
