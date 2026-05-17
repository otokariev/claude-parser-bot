from celery import Celery

from bot.config import settings

# Initialize Celery with Redis as broker and backend
celery_app = Celery(
    "claude_parser_bot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Celery configuration
celery_app.conf.update(
    # Task serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task settings
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Fix CUDA fork issue
    worker_pool="solo",
)

# Auto-discover tasks from services/tasks.py
celery_app.autodiscover_tasks(["services"])