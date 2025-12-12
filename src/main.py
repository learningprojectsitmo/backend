from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.routes import routers as v1_router
from src.core.config import settings
from src.core.container import Container


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


container = Container()
app = FastAPI(
    title="API",
    description="",
    version="1.0.0",
    lifespan=lifespan,
)
app.container = container
app.include_router(v1_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "System API", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
