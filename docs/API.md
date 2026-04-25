# API Reference

Base URL: `http://localhost:8000` (backend service)

All endpoints that require authentication expect a Bearer token in the
`Authorization` header:

```
Authorization: Bearer <access_token>
```

Interactive docs (Swagger UI) are available at `http://localhost:8000/docs`.

---

## Authentication

### POST /api/auth/login

Obtain a JWT access token.

**Request body:**
```json
{ "email": "admin@example.com", "password": "admin123!" }
```

**Response 200:**
```json
{ "access_token": "<jwt>", "token_type": "bearer" }
```

### POST /api/auth/register

Create a new user. **Admin only.**

**Request body:**
```json
{ "email": "user@example.com", "password": "securepass", "is_active": true, "is_admin": false }
```

**Response 201:** `UserResponse`

### GET /api/auth/me

Return the currently authenticated user.

**Response 200:** `UserResponse`

---

## Health

### GET /health

Public endpoint — no authentication required.

**Response 200:**
```json
{
  "status": "ok",
  "timestamp": "2024-01-01T00:00:00Z",
  "features": { "core_video": true, "tts": true, … }
}
```

### GET /api/metrics

Aggregate job counts by status.

**Response 200:**
```json
{ "total_jobs": 42, "by_status": { "pending": 1, "completed": 38, "failed": 3 } }
```

---

## Projects

### GET /api/projects

List all projects belonging to the authenticated user.

**Response 200:** `ProjectResponse[]`

### POST /api/projects

Create a new project.

**Request body:**
```json
{
  "name": "My Channel",
  "default_voice": "en-US-JennyNeural",
  "default_caption_style": { "style": "basic" }
}
```

**Response 201:** `ProjectResponse`

### GET /api/projects/{project_id}

Get a single project.

### PUT /api/projects/{project_id}

Update project settings.

### DELETE /api/projects/{project_id}

Delete a project. Returns `204 No Content`.

---

## Jobs

### GET /api/jobs

List jobs with optional filters.

**Query params:** `status`, `project_id`, `page` (default 1), `size` (default 20)

**Response 200:**
```json
{
  "items": [ { "id": "…", "title": "…", "status": "completed", … } ],
  "total": 12,
  "page": 1,
  "size": 20
}
```

### POST /api/jobs

Create and queue a new video job.

**Request body:**
```json
{
  "title": "My Video",
  "project_id": 1,
  "job_type": "manual",
  "dry_run": false,
  "max_retries": 3,
  "input_data": {
    "topic": "How AI works",
    "script_text": "Optional pre-written script text",
    "voice": "en-US-JennyNeural",
    "script_settings": {}
  }
}
```

**Response 201:** `JobResponse`

> The Celery task is dispatched asynchronously. The job starts in `pending` status
> and transitions to `processing` → `rendering` → `uploading` → `completed` (or `failed`).

### GET /api/jobs/{job_id}

Get a single job with full metadata.

### POST /api/jobs/{job_id}/cancel

Cancel a pending or processing job.

**Response 200:** updated `JobResponse` with `status: "cancelled"`

### POST /api/jobs/{job_id}/retry

Re-queue a failed job. Only works if `retry_count < max_retries`.

**Response 200:** updated `JobResponse`

### GET /api/jobs/{job_id}/logs

Stream job execution logs as plain text.

**Response 200:** `text/plain` with timestamped log lines.

---

## Headless API

The headless API allows full video generation via structured JSON without using the
dashboard UI. See `docs/examples/` for ready-to-use payloads.

### POST /api/v1/headless/jobs

Create a job using one of three input modes.

**Modes:**

| Mode | Description |
|------|-------------|
| `auto` | Only `script.topic` required; all other settings use defaults |
| `semi_auto` | Topic + selective overrides for voice, captions, video |
| `full_control` | Explicit configuration for every pipeline stage |

**Auto mode example:**
```json
{
  "mode": "auto",
  "title": "How GPUs Work",
  "script": { "topic": "How GPUs work" }
}
```

**Full control example:**
```json
{
  "mode": "full_control",
  "title": "Docker in 5 Minutes",
  "script": {
    "text": "Welcome back. Today we cover Docker in 5 minutes.",
    "duration_seconds": 90
  },
  "voice": { "provider": "edge_tts", "voice_id": "en-US-JennyNeural", "rate": "+5%" },
  "caption": { "enabled": true, "style": "basic" },
  "video": { "resolution": "1080x1920", "background_music": false },
  "upload": { "destinations": ["local"] }
}
```

**Response 201:** `HeadlessJobResponse`

### POST /api/v1/headless/jobs/from-template

Create a job from a named template + props.

**Request body:**
```json
{
  "template_id": "quick_explainer",
  "props": { "topic": "How blockchain works" },
  "dry_run": false
}
```

**Response 201:** `HeadlessJobResponse`

### GET /api/v1/headless/templates

List all built-in templates with required/optional props.

**Response 200:** `TemplateInfo[]`

### GET /api/v1/headless/templates/{template_id}

Get a single template including its default payload.

**Response 200:** `TemplateInfo`
**Response 404:** template not found

### GET /api/v1/headless/examples

Return ready-to-paste example payloads for each input mode.

**Response 200:**
```json
{
  "auto": { … },
  "semi_auto": { … },
  "full_control": { … },
  "template": { … },
  "dry_run": { … }
}
```

---

## Topics (Trend Discovery)

### GET /api/topics

List discovered topics. Optional `?status=pending|approved|used|rejected` filter.

### POST /api/topics/discover

Trigger a trend-discovery run (Google Trends + RSS). Requires `FEATURE_TRENDS=true`.

**Request body:**
```json
{ "keyword": null, "limit": 10, "sources": ["google", "rss"] }
```

### PUT /api/topics/{topic_id}/approve

Mark a topic as approved for use.

### PUT /api/topics/{topic_id}/reject

Mark a topic as rejected.

---

## Assets

### GET /api/assets

List uploaded assets. Optional `?project_id=` filter.

### POST /api/assets/upload

Upload a media file (video, audio, image).

**Content-Type:** `multipart/form-data`  
**Field:** `file` (required), `project_id` (optional query param)  
**Max size:** 500 MB  
**Allowed types:** `.mp4`, `.mov`, `.mp3`, `.wav`, `.jpg`, `.jpeg`, `.png`, `.gif`

### DELETE /api/assets/{asset_id}

Delete an asset and its file on disk. Returns `204 No Content`.

---

## Settings

### GET /api/settings

Return current application settings (feature flags, storage path, etc.).

---

## Webhooks

### POST /api/webhooks/n8n

Receive a webhook payload from n8n. Requires `FEATURE_N8N=true`.

**Response 200:** `{ "status": "received" }`

### GET /api/webhooks/status

Return count of received webhooks and timestamp of the last one.

---

## Error Responses

| Status | Meaning |
|--------|---------|
| `400` | Bad request (e.g. cancelling an already-completed job) |
| `401` | Missing or invalid Bearer token |
| `403` | Feature disabled or insufficient permissions |
| `404` | Resource not found |
| `409` | Conflict (e.g. duplicate email on register) |
| `413` | Upload file too large (> 500 MB) |
| `422` | Request validation error (Pydantic) |
| `429` | Rate limit exceeded |
| `500` | Internal server error |

---

## Common `JobResponse` fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` (UUID) | Job identifier |
| `title` | `string` | Human-readable job title |
| `status` | `string` | `pending`, `processing`, `rendering`, `uploading`, `completed`, `failed`, `cancelled` |
| `dry_run` | `boolean` | Whether this is a dry-run (no FFmpeg, no upload) |
| `logs` | `string` | Timestamped pipeline log |
| `output_path` | `string` | Absolute path to the output MP4 on disk |
| `output_metadata` | `object` | Upload URL and other post-process data |
| `validation_result` | `object` | ffprobe validation results |
| `error_message` | `string` | Error detail if status is `failed` |
| `created_at` | `datetime` | Job creation timestamp |
| `started_at` | `datetime` | Pipeline start timestamp |
| `completed_at` | `datetime` | Pipeline completion timestamp |
