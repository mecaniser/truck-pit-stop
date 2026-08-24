# DieselBridge Network Management System

A comprehensive multi-tenant web application for managing semi-truck repair garages.

## Tech Stack

- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS
- **Backend**: FastAPI (Python 3.11+) + SQLAlchemy (async) + Alembic
- **Database**: PostgreSQL
- **Infrastructure**: Railway
- **Payment**: Stripe
- **SMS**: Twilio
- **Email**: Resend
- **Background Tasks**: Celery + Redis

## Features Implemented

### Phase 1: Foundation ✅
- Multi-tenant architecture
- JWT-based authentication (login, register, refresh)
- Role-based access control (Super Admin, Garage Admin, Mechanic, Receptionist, Customer)
- React frontend with routing
- API structure with FastAPI

### Phase 2: Core Entities ✅
- Customer CRUD with multi-tenant isolation
- Vehicle CRUD
- Repair Order management
- Customer Portal (customers can view their vehicles and repair history)

### Services Ready
- Email service (Resend)
- SMS service (Twilio)
- Stripe payment integration
- Receipt PDF generation

## Project Structure

```
truck-pit-stop/
├── frontend/          # React SPA
│   ├── src/
│   │   ├── features/  # Feature modules (auth, customers, vehicles, etc.)
│   │   ├── components/# Reusable components
│   │   ├── stores/    # Zustand state management
│   │   └── lib/       # Utilities, API client
│   └── package.json
├── backend/           # FastAPI application
│   ├── app/
│   │   ├── api/v1/    # API endpoints
│   │   ├── db/models/ # SQLAlchemy models
│   │   ├── schemas/   # Pydantic schemas
│   │   ├── services/  # External service integrations
│   │   └── tasks/     # Celery tasks
│   ├── alembic/       # Database migrations
│   └── requirements.txt
└── railway.json       # Railway configuration
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker and Docker Compose (for local PostgreSQL/Redis)
- Or use Railway's managed services

### Backend Setup

```bash
# Start PostgreSQL and Redis with Docker
docker compose up -d postgres redis

# Backend setup
cd backend

# Create virtual environment
# Use Python 3.11 — the version the Dockerfile and CI both build against.
# A venv built with an older interpreter (e.g. macOS's system python3.9) cannot
# import the app at all: the codebase uses 3.10+ `X | Y` type syntax, so the
# whole test suite fails to collect.
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Verify you are on the right interpreter before installing:
python --version   # expect Python 3.11.x

# Install dependencies
pip install -r requirements.txt

# .env file is already configured for Docker setup
# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload
```

### Docker Backend Dev Server

Use this when you want the backend in Docker without a stale baked app image.
The backend source is mounted into the container and `uvicorn --reload` watches
for route/code changes.

```bash
# Stop the production-style local app container if it owns port 8000
docker rm -f dieselbridge_app 2>/dev/null || true

# Start Postgres, Redis, and the hot-reload API
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build api
```

Keep the frontend on Vite:

```bash
cd frontend
npm run dev
```

Avoid using a baked `truck-pit-stop-local` app image for local feature testing
unless you rebuild and recreate it after every backend or frontend change.

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Copy environment file
cp .env.example .env
# Edit .env with your API URL

# Start development server
npm run dev
```

## Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login
- `POST /api/v1/auth/refresh` - Refresh access token
- `GET /api/v1/auth/me` - Get current user info

### Customers
- `GET /api/v1/customers` - List customers
- `POST /api/v1/customers` - Create customer
- `GET /api/v1/customers/{id}` - Get customer
- `PUT /api/v1/customers/{id}` - Update customer

### Vehicles
- `GET /api/v1/vehicles` - List vehicles
- `POST /api/v1/vehicles` - Create vehicle
- `GET /api/v1/vehicles/{id}` - Get vehicle
- `PUT /api/v1/vehicles/{id}` - Update vehicle

### Repair Orders
- `GET /api/v1/repair-orders` - List repair orders
- `POST /api/v1/repair-orders` - Create repair order
- `GET /api/v1/repair-orders/{id}` - Get repair order
- `PUT /api/v1/repair-orders/{id}` - Update repair order

## Customer Portal

Customers can access their portal at `/portal` after logging in. Features:
- View and manage their profile
- Add and manage vehicles
- View repair history
- Track repair order status

## Environment Variables

### Backend (.env)
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1234567890
RESEND_API_KEY=re_...
QUICKBOOKS_ACCOUNTING_ENVIRONMENT=sandbox
QUICKBOOKS_PAYMENTS_ENVIRONMENT=sandbox
# JSON versioned Fernet keyring and active write version for tenant-owned
# conversion webhook signing secrets.
PAID_INVOICE_WEBHOOK_ENCRYPTION_KEYS={"v1":"..."}
PAID_INVOICE_WEBHOOK_ACTIVE_KEY_VERSION=v1
PAID_INVOICE_WEBHOOK_DNS_TIMEOUT_SECONDS=3
PAID_INVOICE_WEBHOOK_TOTAL_TIMEOUT_SECONDS=35
CONVERSION_OUTBOX_PII_RETENTION_DAYS=30
# Enable only when the Celery worker from railway.worker.json is deployed.
PROVIDER_OUTBOX_ENABLED=false
FRONTEND_URL=http://localhost:5173
PUBLIC_API_BASE_URL=http://localhost:8000
CORS_ORIGINS_STR=http://localhost:5173
COOKIE_DOMAIN=
```

### Frontend (.env)
```
VITE_API_URL=http://localhost:8000/api/v1
VITE_SITE_URL=http://localhost:5173
VITE_STRIPE_PUBLISHABLE_KEY=pk_...
VITE_GA_MEASUREMENT_ID=G-...
```

### Production example (dieselbridge.com)
```
# Backend
ENVIRONMENT=production
FRONTEND_URL=https://www.dieselbridge.com
PUBLIC_API_BASE_URL=https://api.dieselbridge.com
CORS_ORIGINS_STR=https://www.dieselbridge.com,https://dieselbridge.com
COOKIE_DOMAIN=.dieselbridge.com
COOKIE_SECURE=true

# Frontend
VITE_API_URL=https://api.dieselbridge.com/api/v1
VITE_SITE_URL=https://www.dieselbridge.com
```

## Deployment to Railway

1. Create PostgreSQL service in Railway
2. Create Redis service in Railway
3. Deploy backend service (point to Railway PostgreSQL/Redis)
4. Deploy the Celery worker using `railway.worker.json`
5. Set the same versioned `PAID_INVOICE_WEBHOOK_ENCRYPTION_KEYS` and active
   version on every backend process that configures or delivers conversion
   webhooks; generate keys with `Fernet.generate_key().decode()` and retain
   them in Railway's secret store
6. Verify the worker registers `process_paid_invoice_webhooks` and beat contains
   `process-paid-invoice-webhooks` before enabling a shop webhook
7. Set `PROVIDER_OUTBOX_ENABLED=true` on the backend after the worker is healthy
8. Deploy frontend service (set VITE_API_URL to backend URL)
9. Set environment variables in Railway dashboard

## Next Steps

Remaining features to implement:
- Inventory management
- Quote generation workflow
- Parts and labor tracking
- Invoice generation
- Payment processing (Stripe integration ready)
- Automated notifications
- Reporting dashboard
- File uploads
- Activity logs/audit trail
