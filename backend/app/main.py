import asyncio
import logging
import sys
import time

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings

from routers.auth import router as auth_router
from routers.attendance import router as attendance_router
from routers.wfh import router as wfh_router


# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="AttendEase LangGraph Backend"
)


@app.middleware("http")
async def log_requests(request, call_next):
    started_at = time.perf_counter()
    logger.info("request_started method=%s path=%s", request.method, request.url.path)
    try:
        response = await call_next(request)
        logger.info(
            "request_finished method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started_at) * 1000,
        )
        return response
    except Exception:
        logger.exception(
            "request_failed method=%s path=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            (time.perf_counter() - started_at) * 1000,
        )
        raise


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        settings.FRONTEND_ORIGIN
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# =========================================================
# API ROUTER
# =========================================================
#
# Structure:
#
#   /api/auth/...
#   /api/attendance/...
#
# This avoids having multiple independent /api prefixes.
# =========================================================

api_router = APIRouter()


# =========================================================
# AUTH ROUTES
# =========================================================

api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["auth"],
)


# =========================================================
# ATTENDANCE ROUTES
# =========================================================

api_router.include_router(
    attendance_router,
    prefix="/attendance",
    tags=["attendance"],
)

api_router.include_router(
    wfh_router,
    prefix="/attendance",
    tags=["attendance"],
)


# =========================================================
# REGISTER API ROUTER
# =========================================================

app.include_router(
    api_router,
    prefix="/api",
)


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
async def health():
    logger.info("health_check_started")
    return {
        "status": "ok"
    }
