from celery import Celery

from app.core.config import settings

celery_app = Celery("jobnavigator_worker", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task(name="worker.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="worker.extract_profile")
def extract_profile_task(payload: dict) -> dict:
    return {"status": "queued", "payload": payload}

