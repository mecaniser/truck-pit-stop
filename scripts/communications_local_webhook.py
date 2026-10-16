"""Submit signed synthetic callbacks/inbound events to localhost8006 only."""
import argparse
import os
import uuid
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from twilio.request_validator import RequestValidator
from app.core.config import settings


def main():
    if os.environ.get('COMMUNICATIONS_ISOLATED_LOCAL') != '1' or '@127.0.0.1:55460/communications_local' not in settings.DATABASE_URL:
        raise RuntimeError('Isolated configuration required')
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command',required=True)
    inbound = sub.add_parser('inbound')
    inbound.add_argument('--from-number',default='+15005550100')
    inbound.add_argument('--body',required=True)
    inbound.add_argument('--sid')
    status = sub.add_parser('status')
    status.add_argument('--sid',required=True)
    status.add_argument('--status',choices=['queued','sent','delivered','failed','undelivered'],required=True)
    status.add_argument('--error-code')
    args = p.parse_args()
    values = {'MessageSid': args.sid or 'SM' + uuid.uuid4().hex}
    if args.command == 'inbound':
        values.update(From=args.from_number,To='+15005550001',Body=args.body)
    else:
        values['MessageStatus'] = args.status
        if args.error_code:
            values['ErrorCode'] = args.error_code
    url = 'http://127.0.0.1:8006/api/v1/webhooks/twilio/sms/' + args.command
    signature = RequestValidator(settings.TWILIO_AUTH_TOKEN).compute_signature(url,values)
    request = Request(url,data=urlencode(values).encode(),headers={'X-Twilio-Signature':signature,'Content-Type':'application/x-www-form-urlencoded'},method='POST')
    with urlopen(request,timeout=10) as response:
        print(f'Synthetic {args.command}: HTTP {response.status}; SID {values["MessageSid"]}')

if __name__ == '__main__':
    main()
