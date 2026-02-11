# Email Change Security - Quick Reference

> Note: API-wide security controls (timeouts, idempotency, throttling, cache policy, pagination hardening) are tracked in `API_SECURITY_SUMMARY.md`.

## What Was Implemented ✅

### 🔐 Security Steps

1. **Password Confirmation** ← Required to initiate change
2. **Email Verification** ← Must click link in new email
3. **Old Email Notification** ← Security alert to original address

### 📧 The Flow

```
User changes email in profile
       ↓
Password field appears (required)
       ↓
User enters current password & saves
       ↓
[Verification email] → NEW email address
[Security alert] → OLD email address
       ↓
User clicks link in NEW email
       ↓
Email verified & updated
       ↓
Must login with NEW email
```

## Quick Test

1. **Login as garage owner**: `truxpitstop@gmail.com` / `BUse@1534`
2. **Go to Settings** (profile icon)
3. **Click Edit**, change email
4. **Password field appears** - enter: `BUse@1534`
5. **Save** → "Verification email sent!"
6. **(In production)** Check new email for verification link
7. **Click link** → Email verified
8. **Login with new email**

## What Happens

### New Email Receives:
```
📧 Verify Your Email Address

Confirm your email change by clicking below:

[Verify Email Address] ← Button with verification link

⏱️ Link expires in 1 hour
🔒 Didn't request this? Ignore this email
```

### Old Email Receives:
```
⚠️ Email Change Request

Someone requested to change your email from:
old@example.com → ne***w@example.com

A verification link was sent to the new address.
Your email will only change after verification.

❗ Didn't request this change?
Change your password immediately!
```

## Security Features

| Feature | Status | Description |
|---------|--------|-------------|
| Password Required | ✅ | Must enter current password to change email |
| Duplicate Check | ✅ | Can't use email that's already taken |
| Email Verification | ✅ | Must click link in new email |
| Old Email Alert | ✅ | Original email is notified |
| Token Expiration | ✅ | Links expire in 1 hour |
| Single-Use Token | ✅ | Each token can only be used once |
| Masked Email | ✅ | New email partially hidden in notification |

## Applies To

✅ **Garage Owners** - Profile Settings
✅ **Garage Admins** - Profile Settings  
✅ **Mechanics** - Profile tab (mobile view)
✅ **Receptionists** - Profile Settings
✅ **All Users** - Can change their email securely

## Configuration Needed

Ensure these are set in `backend/.env`:
```bash
RESEND_API_KEY=your_api_key_here
RESEND_FROM_EMAIL=noreply@truckpitstop.com
FRONTEND_URL=http://localhost:5173
REDIS_URL=redis://localhost:6379/0
```

## Notes

- **Email updates only after verification** - User keeps old email until they click the link
- **No account lockout** - If user never verifies, email stays the same
- **Secure by default** - Password + verification = bank-level security
- **User-friendly** - Clear messaging at every step

🔒 Your users' accounts are now protected!
