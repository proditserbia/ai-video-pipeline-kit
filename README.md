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
| YouTube Upload | ✅ MVP | OAuth credentials |
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

## License

See [LICENSE_NOTICE.md](./LICENSE_NOTICE.md) — Commercial tiers from $500–$6,000.
