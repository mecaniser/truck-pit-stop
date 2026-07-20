# Stripe Standard account connection

DieselBridge never creates a Stripe account for a garage. A garage creates and
owns its Stripe Standard account directly with Stripe, then selects **Connect
My Stripe Account** in Payments & Accounting to authorize the relationship.

DieselBridge must configure its Stripe Connect application once with:

```dotenv
STRIPE_SECRET_KEY=...
STRIPE_CONNECT_CLIENT_ID=ca_...
STRIPE_CONNECT_REDIRECT_URI=https://api.example.com/api/v1/stripe/connect/oauth/callback
```

Register the redirect URI exactly in Stripe. The backend generates a one-time,
tenant-bound OAuth state and stores only its SHA-256 digest. Tenant API keys,
Stripe passwords, card details, and OAuth tokens are never exposed to the
browser or stored for payment routing. Payments use the platform key plus the
authorized connected account ID.

Existing DieselBridge-created Express links are marked `express_legacy`. A
garage must explicitly disconnect that relationship, which does not delete the
old Stripe account, before connecting its independent Stripe Standard account.
