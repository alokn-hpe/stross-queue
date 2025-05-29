from app.tasks import app as celery_app
from celery.signals import worker_process_init, worker_process_shutdown
from app.db import create_engine_for_worker, dispose_engine

__all__ = ("celery_app",)

@worker_process_init.connect
def init_worker_process(*args, **kwargs):
    create_engine_for_worker()

@worker_process_shutdown.connect
def shutdown_worker_process(*args, **kwargs):
    dispose_engine()
