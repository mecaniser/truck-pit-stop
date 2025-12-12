# Quick Start - Local Development

## 1. Start Database Services

```bash
# Start PostgreSQL and Redis with Docker
docker-compose up -d

# Verify they're running
docker-compose ps
```

## 2. Backend Setup (Terminal 1)

```bash
cd backend

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start backend server
uvicorn app.main:app --reload
```

Backend will run on: **http://localhost:8000**
API docs: **http://localhost:8000/docs**

## 3. Frontend Setup (Terminal 2)

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend will run on: **http://localhost:5173**

## 4. Test It

1. Open http://localhost:5173 in your browser
2. Click "Register" to create an account
3. Login and explore!

## Stop Services

```bash
# Stop Docker services
docker-compose down

# Or stop and remove all data
docker-compose down -v
```

## Troubleshooting

**Docker not starting:**
- Make sure Docker Desktop is running
- Check ports 5432 and 6379 aren't already in use

**Database connection errors:**
- Ensure `docker-compose up -d` completed successfully
- Check `docker-compose ps` shows services as healthy
- Verify `backend/.env` has correct DATABASE_URL

**Migration errors:**
- Make sure PostgreSQL container is healthy: `docker-compose ps`
- Try: `docker-compose restart postgres`
