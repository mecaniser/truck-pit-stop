# Truck Pit Stop Management System

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
docker-compose up -d

# Backend setup
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# .env file is already configured for Docker setup
# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload
```

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
FRONTEND_URL=http://localhost:5173
```

### Frontend (.env)
```
VITE_API_URL=http://localhost:8000/api/v1
VITE_STRIPE_PUBLISHABLE_KEY=pk_...
```

## Deployment to Railway

1. Create PostgreSQL service in Railway
2. Create Redis service in Railway
3. Deploy backend service (point to Railway PostgreSQL/Redis)
4. Deploy frontend service (set VITE_API_URL to backend URL)
5. Set environment variables in Railway dashboard

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

