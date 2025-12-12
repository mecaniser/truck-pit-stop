# Docker Setup for Truck Pit Stop

## Quick Start

### 1. Start PostgreSQL and Redis

```bash
docker-compose up -d
```

This will start:
- PostgreSQL on port 5432
- Redis on port 6379

### 2. Verify Services are Running

```bash
docker-compose ps
```

You should see both services as "Up" and "healthy".

### 3. Run Database Migrations

```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

### 4. Start Backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

## Database Connection

The backend is configured to connect to:
- **Host**: localhost:5432
- **Database**: truckpitstop
- **User**: truckpitstop
- **Password**: truckpitstop_dev

These are set in `backend/.env` and match the docker-compose.yml configuration.

## Useful Commands

### Stop Services
```bash
docker-compose down
```

### Stop and Remove Volumes (deletes all data)
```bash
docker-compose down -v
```

### View Logs
```bash
docker-compose logs -f postgres
docker-compose logs -f redis
```

### Connect to PostgreSQL
```bash
docker exec -it truckpitstop_postgres psql -U truckpitstop -d truckpitstop
```

### Reset Database
```bash
# Stop services and remove volumes
docker-compose down -v

# Start fresh
docker-compose up -d

# Run migrations
cd backend
source venv/bin/activate
alembic upgrade head
```

## Production Notes

For production, you should:
1. Change the PostgreSQL password in docker-compose.yml
2. Use environment variables for sensitive data
3. Set up proper backups
4. Use Railway's managed PostgreSQL instead of Docker

