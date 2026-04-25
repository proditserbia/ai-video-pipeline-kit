# Post-MVP Roadmap

This file tracks the planned GitHub issues for each post-MVP development phase.
Each section corresponds to one GitHub issue. Use the content below to create
the issues in the repository with the suggested labels.

---

## Phase 1 – Beta Hardening

### Issue 1: End-to-end integration tests for the video pipeline

**Labels:** `beta-hardening`, `testing`, `priority:high`
**Estimated complexity:** Medium (3–5 days)

**Background**

The unit test suite covers individual modules and API endpoints in isolation.
Before a public beta, we need integration tests that exercise the full pipeline
(job creation → Celery worker → FFmpeg → DB state update) against real
infrastructure (Postgres + Redis + a real FFmpeg binary in CI).

**Acceptance criteria**

- [ ] A `docker-compose.test.yml` (or an existing `docker-compose.override`)
  brings up Postgres, Redis, and a single worker alongside the API.
- [ ] A pytest test (`tests/integration/test_full_pipeline.py`) creates a job
  via the API, waits for its status to become `completed` or `failed` (poll ≤ 30 s),
  and asserts `output_path` is set.
- [ ] The test runs in CI (GitHub Actions) on every push to `main` and on every PR.
- [ ] A `dry_run=True` mode allows the test to run without real OpenAI / Pexels keys.
- [ ] The CI step is documented in `docs/development.md`.

---

### Issue 2: Structured logging and Sentry integration

**Labels:** `beta-hardening`, `observability`, `priority:high`
**Estimated complexity:** Small (1–2 days)

**Background**

The system already uses `structlog` for structured log output. For beta, operators
need a way to capture unhandled exceptions and receive alerts.

**Acceptance criteria**

- [ ] `sentry-sdk[fastapi,celery]` added to `requirements.txt`.
- [ ] `SENTRY_DSN` environment variable documented in `.env.example`; SDK is
  initialised only when the variable is set (no-op otherwise).
- [ ] Both the FastAPI app (`app/main.py`) and the Celery worker
  (`worker/celery_app.py`) initialise the Sentry SDK at startup.
- [ ] Unhandled exceptions in the pipeline task are captured by Sentry in addition
  to being logged via structlog.
- [ ] A `docs/operations.md` section explains how to configure the DSN.

---

### Issue 3: Rate limiting and API key rotation

**Labels:** `beta-hardening`, `security`, `priority:medium`
**Estimated complexity:** Small (1 day)

**Background**

The API already uses `slowapi` for rate limiting, but the limits are not yet
documented or tunable via environment variables.

**Acceptance criteria**

- [ ] Rate limits are configurable via `RATE_LIMIT_DEFAULT` and
  `RATE_LIMIT_JOBS_CREATE` env vars (documented in `.env.example`).
- [ ] The `/api/v1/jobs` POST endpoint has a separate, stricter per-user rate limit
  (e.g. 10 job creations / minute by default).
- [ ] A `429 Too Many Requests` response includes a `Retry-After` header.
- [ ] Existing tests cover the 429 path.

---

### Issue 4: Health-check improvements and readiness probe

**Labels:** `beta-hardening`, `ops`, `priority:medium`
**Estimated complexity:** Small (< 1 day)

**Background**

The `/health` endpoint exists but does not check downstream dependencies
(Postgres, Redis, Celery worker queue).

**Acceptance criteria**

- [ ] `GET /health/ready` checks DB connectivity (1 query), Redis ping, and
  Celery queue depth; returns 200 only when all pass.
- [ ] `GET /health/live` (simple liveness) stays as-is (`200 OK`).
- [ ] Docker Compose `healthcheck` for the API service uses `/health/ready`.
- [ ] Kubernetes example (in `docs/deployment.md`) uses
  `readinessProbe` → `/health/ready` and `livenessProbe` → `/health/live`.

---

## Phase 2 – Template System

### Issue 5: Expand built-in job templates and add a template marketplace

**Labels:** `templates`, `feature`, `priority:medium`
**Estimated complexity:** Medium (3–5 days)

**Background**

Five built-in templates exist (`quick_explainer`, `product_review`,
`news_summary`, `tutorial`, `story_hook`). We need more variety and a
discoverable way to browse / share templates.

**Acceptance criteria**

- [ ] At least 5 additional templates covering: YouTube Shorts, podcast clip,
  LinkedIn post teaser, news-ticker style, and "educational explainer with
  chapters".
- [ ] A `GET /api/v1/headless/templates` response includes a `category` and
  `thumbnail_url` (static image) field per template.
- [ ] The dashboard **Templates** page lists all templates with their category
  and a preview thumbnail.
- [ ] Users can fork a template via `POST /api/v1/headless/templates/{id}/fork`
  which creates a user-owned copy in the `user_templates` table.
- [ ] Community templates can be submitted via a GitHub PR (a `templates/`
  directory with JSON files) – documented in `CONTRIBUTING.md`.

---

## Phase 3 – Headless API Examples

### Issue 6: Developer documentation and SDK-style usage examples

**Labels:** `documentation`, `headless-api`, `priority:medium`
**Estimated complexity:** Medium (2–3 days)

**Background**

The headless API (`/api/v1/headless/*`) is the primary interface for developers
integrating the pipeline into their own workflows. It needs real-world examples.

**Acceptance criteria**

- [ ] A `examples/headless/` directory is added to the repository with the
  following ready-to-run scripts (each with its own `README.md`):
  - `01_quick_start.py` – minimal Python example using `requests`
  - `02_poll_until_done.py` – polling loop with progress display
  - `03_batch_from_csv.py` – reads a CSV of topics, submits one job per row
  - `04_webhook_receiver.py` – `flask` webhook endpoint that reacts to job events
  - `05_n8n_trigger.json` – an n8n workflow JSON that POSTs to the headless API
- [ ] All examples work against a local Docker Compose stack (`docker-compose up`).
- [ ] A `docs/headless-api.md` guide explains auth, pagination, and webhook events.
- [ ] OpenAPI schema is exported to `docs/openapi.json` as part of CI.

---

## Phase 4 – YouTube Uploader

### Issue 7: Complete YouTube Data API v3 upload flow

**Labels:** `youtube`, `uploader`, `priority:high`
**Estimated complexity:** Large (5–8 days)

**Background**

`worker/modules/uploader/youtube_uploader.py` has the class skeleton and raises
`NotImplementedError`. The OAuth2 + resumable upload flow needs to be implemented.

**Acceptance criteria**

- [ ] `google-api-python-client` and `google-auth-oauthlib` added to
  `requirements.txt`.
- [ ] `YouTubeUploader.upload()` implements:
  1. Load client secrets from `YOUTUBE_CLIENT_SECRETS_FILE`.
  2. Refresh or obtain tokens (service account preferred for unattended use;
     InstalledAppFlow as fallback for dev).
  3. Resumable upload via `youtube.videos().insert(...)` with
     `MediaFileUpload(..., resumable=True)`.
  4. Set title, description, tags, category, and privacy from `metadata`.
  5. Return `UploadResult(url=f"https://youtu.be/{video_id}", ...)` on success.
- [ ] `YOUTUBE_UPLOAD` feature flag defaults to `False`; enabled only when
  secrets file is present and valid.
- [ ] Unit tests mock `googleapiclient`; integration test is gated on the env var.
- [ ] `docs/integrations/youtube.md` covers OAuth2 setup and service account usage.

---

## Phase 5 – S3 / Cloudflare R2 Storage

### Issue 8: Implement S3-compatible cloud storage exporter

**Labels:** `storage`, `cloud`, `priority:medium`
**Estimated complexity:** Medium (3–5 days)

**Background**

`config.py` already exposes `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
and `S3_BUCKET`. The `cloud_storage` feature flag exists but the uploader is not
implemented.

**Acceptance criteria**

- [ ] `boto3` added to `requirements.txt`.
- [ ] New module `worker/modules/uploader/s3_exporter.py` implements
  `AbstractUploader.upload()`:
  - Upload the output MP4 to `s3://{S3_BUCKET}/outputs/{job_id}.mp4`.
  - Generate a pre-signed URL valid for 7 days (configurable via
    `S3_PRESIGN_EXPIRY_SECONDS`).
  - Return `UploadResult(url=presigned_url, ...)`.
- [ ] Works with AWS S3, Cloudflare R2 (custom `S3_ENDPOINT_URL`), and MinIO
  (local dev).
- [ ] `CLOUD_STORAGE` feature flag defaults to `False`; auto-enabled when
  `S3_BUCKET` is set.
- [ ] Docker Compose includes an optional MinIO service for local testing.
- [ ] `docs/integrations/s3-storage.md` documents setup for AWS, R2, and MinIO.

---

## Phase 6 – n8n Workflow Examples

### Issue 9: n8n workflow collection for the video pipeline

**Labels:** `n8n`, `automation`, `priority:low`
**Estimated complexity:** Small (2–3 days)

**Background**

The `n8n` feature flag exists and the `/api/v1/webhooks` endpoint can receive
job-status events. n8n users need ready-to-import workflow JSON files.

**Acceptance criteria**

- [ ] A `examples/n8n/` directory is added with at least 4 workflow JSON files:
  1. `01_weekly_content_batch.json` – cron trigger → batch job creation → Slack
     notification on completion.
  2. `02_rss_to_video.json` – RSS feed → topic extraction → headless job → YouTube upload.
  3. `03_webhook_to_slack.json` – receive `/webhooks` callback → post Slack message
     with output URL.
  4. `04_topic_approval_flow.json` – create topic → send approval request via
     email → approve/reject → create job.
- [ ] Each JSON file can be imported directly into n8n ("Import from File").
- [ ] A `docs/integrations/n8n.md` guide covers:
  - Setting the `WEBHOOK_SECRET` for signed payloads.
  - Mapping n8n credentials to the API key.
  - The complete webhook payload schema.

---

## Phase 7 – GPU / NVENC Deployment

### Issue 10: NVIDIA NVENC hardware encoding support and deployment guide

**Labels:** `gpu`, `performance`, `priority:low`
**Estimated complexity:** Large (5–8 days)

**Background**

`ffmpeg_builder.py` already switches to `h264_nvenc` when `use_nvenc=True`.
The config has `NVIDIA_NVENC_ENABLED`. What is missing is a verified Dockerfile
and deployment guide for CUDA-enabled hosts.

**Acceptance criteria**

- [ ] `Dockerfile.worker.gpu` extends `nvidia/cuda:12.3.1-base-ubuntu22.04` and
  installs `ffmpeg` with `nvenc` support.
- [ ] `docker-compose.gpu.yml` override adds the `deploy.resources.reservations`
  block for a GPU device.
- [ ] A GPU smoke-test CI job (skipped unless `NVIDIA_VISIBLE_DEVICES` is set)
  verifies `ffmpeg -encoders | grep nvenc` exits 0.
- [ ] `NVIDIA_NVENC_ENABLED=true` is automatically passed into the worker when the
  GPU compose override is active.
- [ ] `docs/deployment/gpu.md` covers:
  - CUDA driver requirements and `nvidia-container-toolkit` setup.
  - Performance comparison (CPU vs GPU) benchmarks.
  - Cost-vs-speed guidance for cloud GPU instances (AWS g4dn, Lambda, Runpod).

---

## Phase 8 – Commercial Packaging and Licensing

### Issue 11: Commercial license, pricing tiers, and self-hosted packaging

**Labels:** `commercial`, `licensing`, `priority:low`
**Estimated complexity:** Medium (3–5 days, cross-functional)

**Background**

The current codebase is open source (see `LICENSE`). A commercial offering
needs a clear licensing model, feature differentiation, and packaging for
self-hosted enterprise deployments.

**Acceptance criteria**

- [ ] A `LICENSE_COMMERCIAL.md` document describes the commercial license terms
  (per-seat or per-deployment model TBD by business).
- [ ] `.env.example` includes a `LICENSE_KEY` variable; the API validates the key
  on startup and disables commercial-only features if absent or invalid.
- [ ] Commercial-only features are gated behind `LicenseGuard` middleware
  (e.g. GPU rendering, white-label, advanced analytics).
- [ ] A `Makefile` target `make package` produces a self-contained `tar.gz`
  with `docker-compose.production.yml`, `.env.example`, a seeded DB migration
  script, and a `QUICKSTART.md`.
- [ ] A `docs/commercial/` directory contains:
  - `pricing.md` – proposed tier structure (Starter / Pro / Enterprise).
  - `self-hosted.md` – step-by-step for air-gapped / on-premise deployments.
  - `white-label.md` – custom domain, logo, and colour-scheme configuration.

---

## Label definitions

| Label | Colour | Description |
|---|---|---|
| `beta-hardening` | `#e4e669` | Stability and reliability work before public beta |
| `templates` | `#0075ca` | Video job templates and template system |
| `headless-api` | `#0052cc` | Headless / programmatic API improvements |
| `youtube` | `#ff0000` | YouTube uploader and OAuth integration |
| `storage` | `#5319e7` | Cloud storage (S3, R2, MinIO) |
| `n8n` | `#f7931e` | n8n workflow automation examples |
| `gpu` | `#76b900` | NVIDIA NVENC / GPU-accelerated rendering |
| `commercial` | `#b60205` | Commercial licensing and packaging |
| `testing` | `#0e8a16` | Test coverage and CI |
| `documentation` | `#cfd3d7` | Docs, guides, examples |
| `observability` | `#d93f0b` | Logging, metrics, Sentry |
| `security` | `#b60205` | Auth, rate limiting, secrets |
| `ops` | `#e4e669` | Infrastructure, deployment, health checks |
| `cloud` | `#5319e7` | Cloud storage integration |
| `uploader` | `#0075ca` | Upload destinations |
| `performance` | `#76b900` | Speed and resource optimisation |
| `automation` | `#f7931e` | Automation and workflow integration |
| `feature` | `#84b6eb` | New feature work |
| `priority:high` | `#b60205` | Should be addressed in the next sprint |
| `priority:medium` | `#e4e669` | Should be addressed in the next 2 sprints |
| `priority:low` | `#cfd3d7` | Nice to have, schedule when bandwidth allows |
