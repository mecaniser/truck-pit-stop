# Local Development Setup

Quick guide to get Truck Pit Stop running locally.

## Quick Start

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file (copy from example)
cp .env.example .env

# Edit .env - minimum required:
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/truckpitstop
# SECRET_KEY=your-random-secret-key-here
# REDIS_URL=redis://localhost:6379/0
```

**For local development, you can use SQLite temporarily:**

Edit `.env`:
```
DATABASE_URL=sqlite+aiosqlite:///./truckpitstop.db
```

**Or use PostgreSQL:**
- Install PostgreSQL locally, or
- Use Docker: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15`

### 2. Database Setup

```bash
# If using PostgreSQL, create database first:
# createdb truckpitstop

# Run migrations
cd backend
alembic upgrade head
```

### 3. Start Backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

Backend runs on: http://localhost:8000
API docs: http://localhost:8000/docs

### 4. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create .env file
echo "VITE_API_URL=http://localhost:8000/api/v1" > .env

# Start dev server
npm run dev
```

Frontend runs on: http://localhost:5173

## Testing the Setup

1. Open http://localhost:5173
2. Click "Register" to create an account
3. Login with your credentials
4. You should see the dashboard (or customer portal if registered as customer)

## Development Tips

- Backend auto-reloads on file changes (--reload flag)
- Frontend hot-reloads automatically
- Check backend logs in terminal for API requests
- Use http://localhost:8000/docs for API testing

## Troubleshooting

**Database connection errors:**
- Check DATABASE_URL in backend/.env
- Ensure PostgreSQL is running (if using PostgreSQL)
- For SQLite, ensure write permissions in backend directory

**Frontend can't connect to API:**
- Check VITE_API_URL in frontend/.env
- Ensure backend is running on port 8000
- Check CORS settings in backend/app/main.py

**Import errors:**
- Ensure virtual environment is activated
- Run `pip install -r requirements.txt` again
- Check Python version: `python --version` (should be 3.11+)


