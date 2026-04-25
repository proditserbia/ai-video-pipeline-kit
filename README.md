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
- [Troubleshooting](./docs/TROUBLESHOOTING.md)

## License

See [LICENSE_NOTICE.md](./LICENSE_NOTICE.md) — Commercial tiers from $500–$6,000.
