# Production Deployment — Nginx + SSL on avpk.prodit.rs

This guide walks through a complete production setup:
**Nginx reverse proxy → Let's Encrypt SSL → Docker Compose on a VPS.**

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Firewall](#2-firewall)
3. [Install Nginx and Certbot](#3-install-nginx-and-certbot)
4. [Deploy Nginx Config](#4-deploy-nginx-config)
5. [Obtain SSL Certificate](#5-obtain-ssl-certificate)
6. [Docker Compose — Production Mode](#6-docker-compose--production-mode)
7. [Next.js API URL](#7-nextjs-api-url)
8. [Start the Stack](#8-start-the-stack)
9. [Production Readiness Check](#9-production-readiness-check)
10. [Verify Everything Works](#10-verify-everything-works)
11. [Auto-Renewal](#11-auto-renewal)
12. [Optional Hardening](#12-optional-hardening)
13. [Updating the App](#13-updating-the-app)

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Ubuntu 22.04 / Debian 12 VPS | Other distros work — adapt package names |
| DNS A record | `avpk.prodit.rs` → your server's public IP |
| Docker ≥ 24 + Docker Compose ≥ 2.20 | [Install Docker](https://docs.docker.com/engine/install/ubuntu/) |
| Ports 80 & 443 reachable | Required for HTTP challenge |

Verify DNS propagation before continuing:

```bash
dig +short avpk.prodit.rs
# Should return your server's public IP
```

---

## 2. Firewall

Allow web traffic and block direct access to app ports from outside:

```bash
# Allow SSH (keep this open!)
sudo ufw allow 22/tcp

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Block direct access to app ports from the public internet
# (they will be bound to 127.0.0.1 anyway — this is an extra safeguard)
sudo ufw deny 3000/tcp
sudo ufw deny 8000/tcp

# Enable firewall
sudo ufw enable

# Verify
sudo ufw status verbose
```

Expected output:
```
Status: active

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW IN    Anywhere
80/tcp                     ALLOW IN    Anywhere
443/tcp                    ALLOW IN    Anywhere
3000/tcp                   DENY IN     Anywhere
8000/tcp                   DENY IN     Anywhere
```

---

## 3. Install Nginx and Certbot

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

---

## 4. Deploy Nginx Config

The repo ships two ready-to-use config files:

| Repo file | Destination |
|---|---|
| `nginx/http-extras.conf` | `/etc/nginx/conf.d/avpk-extras.conf` |
| `nginx/avpk.prodit.rs.conf` | `/etc/nginx/sites-available/avpk.prodit.rs` |

`http-extras.conf` must be installed first — it defines the `$connection_upgrade`
map and rate-limit zones that the site config references.

```bash
# 1. Install http-context directives (WebSocket map + rate-limit zones)
sudo cp nginx/http-extras.conf /etc/nginx/conf.d/avpk-extras.conf

# 2. Install the site config
sudo cp nginx/avpk.prodit.rs.conf /etc/nginx/sites-available/avpk.prodit.rs

# 3. Enable the site
sudo ln -s /etc/nginx/sites-available/avpk.prodit.rs \
           /etc/nginx/sites-enabled/avpk.prodit.rs

# 4. Disable the default site
sudo rm -f /etc/nginx/sites-enabled/default

# 5. Test config syntax
sudo nginx -t

# 6. Start / reload Nginx
sudo systemctl enable nginx
sudo systemctl restart nginx
```

> **Note:** Before the SSL certificate exists, the `ssl_certificate` lines will
> cause `nginx -t` to fail.  You can temporarily comment them out, obtain the
> cert in step 5, then uncomment.  Certbot's `--nginx` plugin will handle this
> automatically.

---

## 5. Obtain SSL Certificate

Certbot's Nginx plugin reads the existing config, obtains the certificate, and
rewrites the SSL directives automatically.

```bash
sudo certbot --nginx -d avpk.prodit.rs
```

Follow the interactive prompts:
- Enter your email address (for renewal notices)
- Agree to the Terms of Service
- Choose whether to share your email with EFF (optional)
- Certbot will automatically configure Nginx to redirect HTTP → HTTPS

Certbot stores certificates in `/etc/letsencrypt/live/avpk.prodit.rs/`.

---

## 6. Docker Compose — Production Mode

The repo ships `docker-compose.prod.yml` which overrides port bindings so that
**both services listen on 127.0.0.1 only** — they are never reachable directly
from the public internet.

It also sets `NEXT_PUBLIC_API_URL=https://avpk.prodit.rs/api`.

```bash
cd /path/to/ai-video-pipeline-kit

# Create / edit your .env
cp .env.example .env
nano .env
# Set at minimum:
#   SECRET_KEY   — openssl rand -hex 32
#   ADMIN_PASSWORD
#   POSTGRES_PASSWORD
```

### Option A — localhost bind (recommended, no extra container)

The `docker-compose.prod.yml` file binds ports to `127.0.0.1`.
Nginx runs on the **host** and forwards traffic to these loopback ports.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Option B — internal Docker network (advanced)

Run Nginx as a Docker container on the same internal network as the app.
Replace `127.0.0.1:3000` / `127.0.0.1:8000` in the Nginx config with the
container service names (`frontend:3000` / `backend:8000`).  This requires
adding a `nginx` service to your compose file and mounting the config.

Option A is simpler for a single-server setup.

---

## 7. Next.js API URL

`NEXT_PUBLIC_API_URL` is embedded **at build time** into the Next.js bundle.
Changing it in `.env` after the image is built has **no effect** until you
rebuild the image.

The `docker-compose.prod.yml` already sets the correct production value:

```
NEXT_PUBLIC_API_URL=https://avpk.prodit.rs/api
```

If you change the domain later:

```bash
# 1. Update docker-compose.prod.yml (or .env)
# 2. Rebuild and restart the frontend service
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    up -d --build frontend
```

---

## 8. Start the Stack

```bash
cd /path/to/ai-video-pipeline-kit

# Build images and start all services in the background
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Watch logs
docker compose logs -f
```

After a successful start, reload Nginx to pick up any final config changes:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## 9. Production Readiness Check

Before exposing the stack to traffic, run the readiness check to confirm all
services and dependencies are configured correctly:

```bash
# Run from the repo root (after docker compose up, or on the host directly)
python scripts/check_production_readiness.py
```

The script prints a **PASS / WARN / FAIL** table and exits with code `0` (all
clear) or `1` (at least one FAIL).

Example output:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║ AI Video Pipeline Kit — Production Readiness Check                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

  CHECK                              STATUS  DETAIL
──────────────────────────────────────────────────────────────────────────────
  PostgreSQL connection              PASS    Connected (db=aivideo)
  Redis connection                   PASS    redis://redis:6379/0
  FFmpeg installed                   PASS    /usr/bin/ffmpeg
  ffprobe installed                  PASS    /usr/bin/ffprobe
  TTS provider configured            PASS    edge-tts
  Stock media provider               WARN    No API keys; placeholder clips used
  Output storage writable            PASS    /storage/outputs
  Whisper / captions                 PASS    faster-whisper available (model=base)
  SECRET_KEY changed                 PASS    Custom key set (length OK)
  NEXT_PUBLIC_API_URL                PASS    https://avpk.prodit.rs/api/v1
──────────────────────────────────────────────────────────────────────────────

  RESULT: 1 WARN, 9 PASS
```

### What each check tests

| Check | PASS condition | WARN / FAIL condition |
|---|---|---|
| **PostgreSQL connection** | `psycopg2` can connect and execute a query | Cannot connect → FAIL |
| **Redis connection** | `redis-py` ping succeeds | Cannot ping → FAIL |
| **FFmpeg installed** | `ffmpeg` found on PATH | Not found → FAIL |
| **ffprobe installed** | `ffprobe` found on PATH | Not found → FAIL |
| **TTS provider configured** | `EDGE_TTS_ENABLED=true` or an API key set | None configured → WARN |
| **Stock media provider** | Pexels/Pixabay key set, or local video assets present | Neither → WARN (placeholder used) |
| **Output storage writable** | Can create a temp file in `$STORAGE_PATH/outputs` | Permission error → FAIL |
| **Whisper / captions** | `WHISPER_ENABLED=true` and `faster-whisper` importable | Disabled → WARN; not installed → WARN |
| **SECRET_KEY changed** | Not a known default, length ≥ 32 chars | Default/weak key → FAIL |
| **NEXT_PUBLIC_API_URL** | Starts with `https://` and not `localhost` | Not set → WARN; localhost URL → WARN |

> **Tip:** Run `python scripts/check_production_readiness.py || exit 1` in your
> CI/CD pipeline or deployment script to gate the deployment on a clean result.

---

## 10. Verify Everything Works

```bash
# 1. Frontend (returns HTML)
curl -I https://avpk.prodit.rs

# 2. Backend health endpoint
curl https://avpk.prodit.rs/api/health
# Expected: {"status":"ok"} or similar JSON

# 3. HTTP → HTTPS redirect
curl -I http://avpk.prodit.rs
# Expected: HTTP/1.1 301 Moved Permanently
#           Location: https://avpk.prodit.rs/

# 4. SSL certificate info
openssl s_client -connect avpk.prodit.rs:443 -servername avpk.prodit.rs \
    </dev/null 2>/dev/null | openssl x509 -noout -subject -dates \
    | grep -E "subject=|notAfter"

# 5. Confirm app ports are NOT reachable from outside
# Run from a remote machine:
curl http://avpk.prodit.rs:3000   # Should time out or be refused
curl http://avpk.prodit.rs:8000   # Should time out or be refused
```

---

## 11. Auto-Renewal that renews certificates automatically.
Verify it is active:

```bash
sudo systemctl status certbot.timer
```

Expected output contains `Active: active (waiting)`.

Test a dry run:

```bash
sudo certbot renew --dry-run
```

Nginx is reloaded automatically after renewal via the `/etc/letsencrypt/renewal-hooks/deploy/` hook installed by `python3-certbot-nginx`.

---

## 12. Optional Hardening

### Gzip
Already enabled in `nginx/avpk.prodit.rs.conf` for HTML, CSS, JS, JSON, SVG,
and fonts.

### Security Headers
The following headers are set in the config:

| Header | Value |
|---|---|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `X-Content-Type-Options` | `nosniff` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |

### Rate Limiting
Two zones are configured:

| Zone | Limit | Applied to |
|---|---|---|
| `api_limit` | 30 req/s (burst 50) | `/api` |
| `general_limit` | 60 req/s (burst 100) | `/` (frontend) |

Tune these values in `/etc/nginx/conf.d/avpk-extras.conf` and the site config.

### Fail2ban (optional)
```bash
sudo apt install -y fail2ban
# Default jail blocks IPs after repeated HTTP 4xx/5xx responses
sudo systemctl enable --now fail2ban
```

---

## 13. Updating the App

```bash
cd /path/to/ai-video-pipeline-kit
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Database migrations run automatically on backend startup.
