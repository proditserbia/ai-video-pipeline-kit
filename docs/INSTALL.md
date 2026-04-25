# Installation Guide

## Prerequisites

- **Docker** ≥ 24.0 — [Install Docker](https://docs.docker.com/get-docker/)
- **Docker Compose** ≥ 2.20 — included with Docker Desktop
- **Git**
- 4 GB RAM minimum (8 GB recommended)
- 10 GB free disk space

## Quick Start (5 Steps)

```bash
# 1. Clone
git clone https://github.com/proditserbia/ai-video-pipeline-kit.git
cd ai-video-pipeline-kit

# 2. Create environment file
cp .env.example .env

# 3. (Optional) Edit .env — the MVP works without any API keys
nano .env

# 4. Build and start
docker compose up --build

# 5. Open browser
open http://localhost:3000
```

**Default credentials:** `admin@example.com` / `admin123!`

> ⚠️ Change `SECRET_KEY` and `ADMIN_PASSWORD` in `.env` before deploying to production.

## Services Started

| Service | Port | Description |
|---------|------|-------------|
| Frontend (Next.js) | 3000 | Web dashboard |
| Backend (FastAPI) | 8000 | REST API |
| PostgreSQL | 5432 (internal) | Database |
| Redis | 6379 (internal) | Queue |
| Worker (Celery) | — | Background job processor |

## First Run Walkthrough

### 1. Create a Project

1. Login at http://localhost:3000
2. Go to **Projects** → click **New Project**
3. Enter a project name (e.g., "My First Channel")
4. Click **Create Project**

### 2. Create a Manual Job

1. Go to **Jobs** → click **New Job**
2. Select your project
3. Enter a **Title** (e.g., "Test Video")
4. Set **Script Mode** to "Manual Text"
5. Enter script text (e.g., "Welcome to my channel. Today we explore AI video generation.")
6. Select a **Voice** (e.g., `en-US-JennyNeural` — free Edge-TTS)
7. Set **Caption Style** to "basic"
8. Click **Submit Job**

### 3. Monitor Progress

1. Go to **Jobs** — your job shows as `pending` then `processing`
2. Click the job to see the **detail page** with live logs
3. When complete, status changes to `completed`
4. Download button appears for the output MP4

## Production Deployment

For a VPS deployment:

```bash
# Generate a secure secret key
openssl rand -hex 32

# Edit .env with production values
nano .env
# Set: SECRET_KEY, ADMIN_PASSWORD, POSTGRES_PASSWORD

# Start in detached mode
docker compose up -d --build

# View logs
docker compose logs -f
```

### Reverse Proxy (nginx) + SSL

For a complete, production-ready Nginx + Let's Encrypt setup see
**[docs/PRODUCTION.md](PRODUCTION.md)**.

It covers:
- Full Nginx config with HTTP → HTTPS redirect, WebSocket support, gzip, and security headers
- Certbot SSL certificate issuance and auto-renewal
- UFW firewall rules (open 80/443, block 3000/8000)
- `docker-compose.prod.yml` that binds ports to `127.0.0.1` only
- Health-check verification commands

## Updating

```bash
git pull
docker compose up -d --build
```

Migrations run automatically on backend startup.

## Stopping

```bash
docker compose down          # Stop services, keep data
docker compose down -v       # Stop services, DELETE all data
```
