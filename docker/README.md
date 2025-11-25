# Hindsight Docker Setup

Complete Docker Compose setup for running all Hindsight services locally.

## Services

This setup includes:
- **PostgreSQL** with pgvector extension (port 5432)
- **API Service** - FastAPI backend (port 8888)
- **Control Plane** - Next.js web UI (port 3000)

## Quick Start

1. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and set your API keys
   ```

2. **Start all services:**
   ```bash
   ./start.sh
   ```

3. **Access the services:**
   - Control Plane: http://localhost:3000
   - API: http://localhost:8888
   - PostgreSQL: localhost:5432

## Scripts

### `./start.sh`
Build and start all services. Waits for all services to be healthy.

### `./stop.sh`
Stop all services (keeps data).

### `./clean.sh`
Stop all services and remove all data (destructive).

### `./logs.sh [service]`
View logs for all services or a specific service:
```bash
./logs.sh              # All services
./logs.sh api          # API only
./logs.sh postgres     # PostgreSQL only
./logs.sh control-plane # Control plane only
```

## Manual Docker Compose Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Rebuild and start
docker-compose up --build -d

# View logs
docker-compose logs -f

# Remove everything including data
docker-compose down -v
```

## Database

### Connection Info
- **Host:** localhost
- **Port:** 5432
- **Database:** hindsight
- **User:** hindsight
- **Password:** hindsight_dev

### Migrations

Database migrations run automatically when the API service starts. The API uses Alembic to:
1. Check the current schema version
2. Run any pending migrations
3. Initialize the database if it's empty

Extensions (pgvector, uuid-ossp) are created automatically by the first migration.

## Environment Variables

Required in `.env` file:

```bash
# API Service Configuration
HINDSIGHT_API_DATABASE_URL=postgresql://hindsight:hindsight_dev@localhost:5432/hindsight
HINDSIGHT_API_LLM_PROVIDER=groq
HINDSIGHT_API_LLM_API_KEY=your-api-key-here
HINDSIGHT_API_LLM_MODEL=openai/gpt-oss-120b

# Optional: Custom LLM endpoint
# HINDSIGHT_API_LLM_BASE_URL=http://localhost:11434/v1

# Control Plane Configuration
HINDSIGHT_CP_DATAPLANE_API_URL=http://localhost:8888
```

## Troubleshooting

### Services won't start
Check logs for errors:
```bash
./logs.sh
```

### Database connection issues
Ensure PostgreSQL is healthy:
```bash
docker exec hindsight-postgres pg_isready -U hindsight
```

### API won't connect to database
Check if migrations ran successfully:
```bash
./logs.sh api
```

### Control plane can't reach API
Verify the API is running:
```bash
curl http://localhost:8888/
```

### Reset everything
```bash
./clean.sh
./start.sh
```

## Development

### Rebuilding after code changes

**API changes:**
```bash
docker-compose up --build -d api
```

**Control Plane changes:**
```bash
docker-compose up --build -d control-plane
```

### Accessing the database
```bash
docker exec -it hindsight-postgres psql -U hindsight -d hindsight
```

### Inspecting containers
```bash
docker-compose ps
docker-compose exec api bash
docker-compose exec control-plane sh
```

## Data Persistence

PostgreSQL data is persisted in a Docker volume named `postgres_data`. This data survives container restarts but not `docker-compose down -v`.

To backup data:
```bash
docker exec hindsight-postgres pg_dump -U hindsight hindsight > backup.sql
```

To restore data:
```bash
docker exec -i hindsight-postgres psql -U hindsight hindsight < backup.sql
```
