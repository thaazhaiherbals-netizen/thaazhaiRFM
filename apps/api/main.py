import json
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from apps.api.admin import router as admin_router
from apps.api.config import get_settings
from apps.api.db import get_engine
from apps.api.marketing import router as marketing_router
from apps.api.operations import router as operations_router

logger = logging.getLogger("thaazhai.api")
app = FastAPI(title="Thaazhai Operations API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


class HealthResponse(BaseModel):
    status: str
    service: str = "thaazhai-api"


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness stays available before database configuration."""
    return HealthResponse(status="ok")


@app.get("/health/ready", response_model=HealthResponse)
def ready() -> HealthResponse | JSONResponse:
    """Readiness verifies the configured database without exposing connection details."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logger.warning(json.dumps({"event": "database_readiness_failed"}))
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return HealthResponse(status="ready")


app.include_router(admin_router)
app.include_router(operations_router)
app.include_router(marketing_router)
