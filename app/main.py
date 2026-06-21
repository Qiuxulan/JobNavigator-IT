import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings

os.environ.pop("SSLKEYLOGFILE", None)

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="JobNavigator-IT API for extraction, recommendation, path planning, trend and decision chat.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1",
        "http://localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

