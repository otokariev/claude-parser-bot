from celery import Celery

from bot.config import settings

# Initialize Celery with Redis as broker and backend
celery_app = Celery(
    "claude_parser_bot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# SSL settings for Upstash Redis (rediss://)
redis_ssl_config = {
    "ssl_cert_reqs": "none",
}

# Celery configuration
celery_app.conf.update(
    broker_use_ssl=redis_ssl_config,
    redis_backend_use_ssl=redis_ssl_config,
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
    # Celery Beat schedule
    beat_schedule={
        "check-monitors-every-day": {
            "task": "tasks.check_monitors",
            "schedule": 86400.0,
        },
    },
)

# Auto-discover tasks from services/tasks.py
celery_app.autodiscover_tasks(["services"])