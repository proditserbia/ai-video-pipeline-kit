# Troubleshooting Guide

## Quick diagnostics

```bash
# Check all service statuses
docker compose ps

# Tail all logs
docker compose logs -f

# Tail a single service
docker compose logs -f backend
docker compose logs -f worker
```

---

## Services won't start

### `postgres` or `redis` fails to start

```
Error: port is already allocated
```

Another process is using port 5432 or 6379. Either stop the conflicting process or
override the ports in `.env`:

```env
POSTGRES_PORT=5433
```

Then update `docker-compose.yml` to use `${POSTGRES_PORT:-5432}:5432`.

### `backend` exits immediately

Check logs:
```bash
docker compose logs backend
```

**Common causes:**
- `DATABASE_URL` points to a wrong scheme. The backend needs `postgresql+asyncpg://…`.
  Ensure `DATABASE_URL` is set correctly in `docker-compose.yml` (not `psycopg2`).
- `SYNC_DATABASE_URL` is missing. Alembic migrations use the sync driver.
- `SECRET_KEY` is shorter than 32 characters.

### `worker` exits immediately

```bash
docker compose logs worker
```

**Common causes:**
- Redis not yet healthy — wait for the healthcheck to pass (`docker compose ps`).
- `SYNC_DATABASE_URL` missing — the Celery worker uses the psycopg2 URL.

---

## Jobs stay in `pending` forever

The most common reason is a queue name mismatch between the task router and the worker.

1. Verify the worker is running:
   ```bash
   docker compose ps worker
   ```

2. Check that the worker consumes from the right queues:
   ```bash
   docker compose logs worker | grep -E "celery|queues"
   ```
   The worker should log something like:
   ```
   [queues]  .> pipeline         exchange=pipeline(direct) key=pipeline
   ```

3. Inspect the Celery inspect output:
   ```bash
   docker compose exec worker celery -A worker.celery_app inspect active_queues
   ```

4. If the queues don't include `pipeline` or `scheduled`, the Dockerfile.worker
   `-Q` argument is out of sync with the task routing in `celery_app.py`. Both
   should list `pipeline,scheduled,default`.

---

## Jobs fail immediately with `NameError: name '_run' is not defined`

This was a bug in `ffmpeg_builder.py` where the `_run` helper function was placed as
dead code inside `_escape_srt_path`. It has been fixed — ensure you are running the
latest version of the code:

```bash
git pull
docker compose up -d --build
```

---

## Jobs fail with `AttributeError: 'dict' object has no attribute 'OPENAI_BASE_URL'`

This was a bug in `openai_provider.py` where the method parameter `settings` shadowed
the module-level `from app.config import settings` import. It has been fixed — pull
the latest code and rebuild.

---

## Jobs fail with `'sessionmaker' object has no attribute 'query'`

This was a bug in `video_pipeline.py` and `scheduled.py` where `SyncSessionLocal()`
returned the sessionmaker factory instead of a session. It has been fixed — pull the
latest code and rebuild.

---

## `/health` returns 500

1. **Database not reachable** — check that postgres is healthy and `DATABASE_URL` is correct.
2. **Alembic migration failed** — check backend logs for `alembic_migration_failed`.
   Try running migrations manually:
   ```bash
   docker compose exec backend alembic upgrade head
   ```

---

## Admin user not created

The admin user is seeded automatically at backend startup. If login fails:

1. Check startup logs for `admin_seed_failed`:
   ```bash
   docker compose logs backend | grep admin_seed
   ```
2. Run the seed script manually:
   ```bash
   docker compose exec backend python seed.py
   ```
3. Verify the `ADMIN_EMAIL` and `ADMIN_PASSWORD` env vars match what you are using to log in.

---

## No video output / `output_path` is null

1. **FFmpeg not installed in the container** — both Dockerfiles install `ffmpeg` via apt.
   If running outside Docker, install FFmpeg ≥ 5.0.
2. **`dry_run: true`** — dry-run jobs skip FFmpeg rendering and produce no output file.
3. **`FEATURE_CORE_VIDEO=false`** — the video building step was skipped.
4. **Storage path not writable** — the `/storage` volume must be writable by the process.
5. Check job logs in the dashboard or via the API:
   ```bash
   curl -H "Authorization: Bearer <token>" http://localhost:8000/api/jobs/<job_id>/logs
   ```

---

## Edge TTS fails / no audio

Edge TTS requires outbound HTTPS access to Microsoft servers. In air-gapped or restricted
networks it will fail silently (log entry: `TTS audio: None`) and the video will be built
without audio.

Fix:
- Allow outbound HTTPS from the worker container.
- Or use a local TTS solution (Coqui TTS — see `docs/MODULES.md`).

---

## Captions not appearing in video

1. **`FEATURE_CAPTIONS=false`** — captions step is disabled.
2. **faster-whisper not installed** — check `requirements.txt` includes `faster-whisper`.
3. **Model download failed** — whisper models are downloaded on first use (~74 MB for `base`).
   Ensure outbound internet access from the worker container.
4. **SRT path escaping** — special characters (`:`, `'`, `[`) in the storage path can break
   the FFmpeg `subtitles=` filter. Move the storage volume to a path without special characters.

---

## Frontend shows "Network Error" / can't reach backend

The frontend makes API calls to `NEXT_PUBLIC_API_URL`. In Docker Compose this is set to
`http://localhost:8000` by default. This works when the user's browser is on the same
machine as Docker.

For remote/VPS deployments:
- Set `NEXT_PUBLIC_API_URL=http://<your-server-ip>:8000` before building the frontend image.
- Or configure a reverse proxy so both frontend and backend are served from the same origin.

---

## `python-multipart` error on form upload

```
RuntimeError: Form data requires "python-multipart" to be installed.
```

`python-multipart` must be in `requirements.txt`. This was corrected in version 0.0.22.
Pull the latest code and rebuild.

---

## `ImportError: email-validator is not installed`

The `EmailStr` Pydantic type requires the `email-validator` package. It has been added to
`requirements.txt`. Pull the latest code and rebuild the containers.

---

## Tests fail with `aiosqlite` errors

```
ModuleNotFoundError: No module named 'aiosqlite'
```

Run: `pip install aiosqlite` (or ensure `aiosqlite` is in `requirements.txt`).

---

## Resetting all data

```bash
# Stop services and delete all volumes (wipes database and storage)
docker compose down -v

# Start fresh
docker compose up --build
```

---

## Getting more verbose logs

Increase Celery log level in `Dockerfile.worker`:
```
--loglevel=debug
```

Enable SQLAlchemy query logging in `database.py`:
```python
_async_engine = create_async_engine(settings.DATABASE_URL, echo=True, …)
```

> ⚠️ Do not enable `echo=True` in production — it logs all SQL queries including data.
