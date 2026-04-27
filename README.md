# AI Video Production Factory

> A modular, Dockerized, web-based AI video automation system for generating short-form vertical videos automatically.

---

## Quick Start

```bash
git clone https://github.com/proditserbia/ai-video-pipeline-kit.git
cd ai-video-pipeline-kit
cp .env.example .env
docker compose up --build
# Open http://localhost:3000  (admin@example.com / admin123!)
```

## Architecture

```
Browser (Next.js :3000) → FastAPI Backend (:8000) → PostgreSQL + Redis
                                                   → Celery Worker → FFmpeg/TTS/Whisper
                                                   → /storage volume
```

## Modules

| Module | Status | Requires |
|--------|--------|---------|
| Core Job System | ✅ MVP | — |
| Dashboard (Next.js) | ✅ MVP | — |
| TTS (Edge-TTS) | ✅ MVP | — (free) |
| Video Builder (FFmpeg) | ✅ MVP | FFmpeg |
| Caption/Transcription | ✅ MVP | faster-whisper |
| AI Script Generator | ✅ MVP | OpenAI key (optional) |
| Stock Media | ✅ MVP | Pexels/Pixabay key (optional) |
| Trend Discovery | ✅ MVP | optional |
| YouTube Upload | ❌ Not implemented | — |
| n8n Integration | ✅ MVP | n8n instance |
| GPU Rendering (NVENC) | ✅ MVP | NVIDIA GPU |

## Docs

- [Installation](./docs/INSTALL.md)
- [Configuration](./docs/CONFIGURATION.md)
- [Modules](./docs/MODULES.md)
- [API](./docs/API.md)
- [Production Deployment](./docs/PRODUCTION.md)
- [Troubleshooting](./docs/TROUBLESHOOTING.md)

## Production Readiness Check

Before going live, validate that all services and dependencies are reachable and correctly configured:

```bash
python scripts/check_production_readiness.py
```

Prints a PASS / WARN / FAIL table for PostgreSQL, Redis, FFmpeg, TTS, stock media, storage, Whisper, and secret-key hygiene.  Exits `1` on any failure.  See [docs/PRODUCTION.md](./docs/PRODUCTION.md#9-production-readiness-check) for full details.

## Stock Media — Pexels Setup

When `PEXELS_API_KEY` is configured, the worker automatically sources real stock footage from [Pexels](https://www.pexels.com/api/) instead of generating coloured placeholder clips.

### Configuration

1. Sign up for a free Pexels API key at <https://www.pexels.com/api/>.
2. Add the key to your `.env` file:

   ```env
   PEXELS_API_KEY=your_key_here
   ```

   `docker-compose.yml` forwards this value to the worker container automatically.

### Provider Priority

When a job runs, stock media is sourced in the following order:

| Priority | Provider | Trigger |
|----------|----------|---------|
| 1 | **Pexels** | `PEXELS_API_KEY` is set |
| 2 | **Pixabay** | `PIXABAY_API_KEY` is set (Pexels returned no clips) |
| 3 | **Local assets** | Video files under `STORAGE_PATH/assets/` (no API key) |
| 4 | **Placeholder** | Always available — coloured FFmpeg-generated clips |

### Search Query

The search query used for Pexels (and Pixabay) is built from the job's content in this order:
1. Full script text
2. Topic field
3. Job title

### Rate Limits (Pexels free tier)

| Limit | Value |
|-------|-------|
| Requests per hour | 200 |
| Requests per month | 20,000 |
| Videos per request | up to 15 |

See the [Pexels API docs](https://www.pexels.com/api/documentation/) for details on paid tiers.

### Fallback Behaviour

If Pexels is configured but returns no results (empty query, rate-limited, or network error):

- The pipeline falls back to Pixabay → local assets → placeholder in order.
- A `stock_warning` key is written to `job.output_metadata`.
- The job is **not** failed; it continues with whatever clips are available.
- `result_quality` is set to `"fallback"` if only placeholder clips were used.

### Job Output Metadata

After a successful run the following keys are present in `output_metadata`:

```json
{
  "stock_provider": "pexels",
  "stock_query":    "autumn leaves forest",
  "stock_clips":    ["/storage/temp/<job_id>/media/pexels_12345.mp4"],
  "clip_sources":   ["pexels", "pexels", "pexels"]
}
```

If Pexels fell back to another provider, `stock_warning` is also included.

### Verify the Integration

```bash
python scripts/test_pexels.py "nature"
# Or fetch multiple clips:
python scripts/test_pexels.py "city skyline" --count 3
```

The script prints a diagnostic table and exits `0` on success or `1` on failure.

## License

See [LICENSE_NOTICE.md](./LICENSE_NOTICE.md) — Commercial tiers from $500–$6,000.
