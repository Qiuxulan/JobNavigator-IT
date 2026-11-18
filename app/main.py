import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.companies import router as companies_router
from app.api.hiring import router as hiring_router
from app.api.market import router as market_router
from app.api.news import router as news_router
from app.api.role_insights import router as role_insights_router
from app.api.routes import router
from app.api.user_data import router as user_data_router
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

# 技能趋势 v3（app/api/trends_v3.py）：技能维度真实月度面板。
# 必须先于旧 /v1/trends/{job_role} 路由注册，否则 /v1/trends/skills 会被旧路由截获。
from app.api.trends_v3 import router as trends_v3_router

app.include_router(trends_v3_router)
app.include_router(router)
app.include_router(role_insights_router)
app.include_router(news_router)
app.include_router(user_data_router)
app.include_router(hiring_router)
app.include_router(companies_router)
app.include_router(market_router)

