from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.routes import routers as v1_router
from src.core.config import settings
from src.core.database import Base, engine
from src.core.logging_config import get_logger, setup_logging
from src.core.middleware.logging_middleware import setup_logging_middleware
from src.core.audit_listeners import setup_audit_listeners

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Инициализация логирования при запуске
    setup_logging()
    logger = get_logger(__name__)

    logger.info("Starting API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"Database URL: {settings.DATABASE_URL}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified")

    setup_audit_listeners()


    logger.info("API startup completed successfully")
    yield

    logger.info("API shutdown initiated")


app = FastAPI(
    title="API",
    description="",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(v1_router)

# Настройка middleware для логирования
setup_logging_middleware(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root(request: Request):
    """Корневой endpoint API"""
    logger = get_logger(__name__)

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    logger.info(f"Root endpoint accessed - IP: {client_ip}, User-Agent: {user_agent}")

    return {"message": "System API", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
