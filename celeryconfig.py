from dotenv import load_dotenv
import os

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

broker_url = REDIS_URL
result_backend = REDIS_URL
task_routes = {
    'app.tasks.scan_image_task': {'queue': 'scan'},
    'app.tasks.check_status_task': {'queue': 'scan'},
    'app.tasks.report_task': {'queue': 'report'}
}