from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import auth, assets, headless, health, jobs, projects, settings, topics, webhooks
from app.config import settings as app_settings
from app.core.rate_limit import limiter
from app.middleware.logging import LoggingMiddleware

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create storage directories
    for sub in ["uploads", "outputs", "temp", "assets"]:
        Path(app_settings.STORAGE_PATH, sub).mkdir(parents=True, exist_ok=True)

    # Run DB migrations
    try:
        import subprocess
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("alembic_migration_failed", stderr=result.stderr)
        else:
            logger.info("alembic_migration_ok")
    except FileNotFoundError:
        logger.warning("alembic_not_found")

    # Seed admin user
    try:
        from app.services.job_service import seed_admin_user
        await seed_admin_user()
    except Exception as exc:
        logger.warning("admin_seed_failed", error=str(exc))

    logger.info("startup_complete")
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Video Pipeline Kit",
        version="1.0.0",
        description="Production-ready AI video production factory API",
        lifespan=lifespan,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    # Middleware (order matters – outermost added last)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers – each data router is mounted at both /api (legacy) and /api/v1 (current)
    # so the frontend's /api/v1/… calls and the test suite's /api/… calls both work.
    _data_routers = [auth.router, jobs.router, projects.router, topics.router,
                     assets.router, settings.router, webhooks.router]
    for _r in _data_routers:
        app.include_router(_r, prefix="/api")
        app.include_router(_r, prefix="/api/v1")

    # Health / metrics – paths are hardcoded in the handler (no router prefix)
    app.include_router(health.router)

    # Headless API – already uses full /api/v1/headless prefix internally
    app.include_router(headless.router)

    # Validation error handler
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Pydantic v2 errors() may contain non-JSON-serializable objects such as
        # bytes (raw request input) or Exception instances (ctx["error"]).
        # Recursively sanitize the entire error structure before serializing.
        def _sanitize(obj: object) -> object:
            if isinstance(obj, bytes):
                return obj.decode("utf-8", errors="replace")
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_sanitize(v) for v in obj]
            if not isinstance(obj, (str, int, float, bool, type(None))):
                return str(obj)
            return obj

        errors = [_sanitize(dict(err)) for err in exc.errors()]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": errors},
        )

    return app


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Rate limit exceeded"},
    )


app = create_app()
