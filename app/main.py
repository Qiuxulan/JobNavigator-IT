from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="JobNavigator-IT API for extraction, recommendation, path planning, trend and decision chat.",
)

app.include_router(router)

