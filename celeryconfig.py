broker_url = 'redis://localhost:6379/0'
result_backend = 'redis://localhost:6379/0'
task_routes = {
    'app.tasks.scan_image_task': {'queue': 'scan'},
    'app.tasks.check_status_task': {'queue': 'scan'},
    'app.tasks.report_task': {'queue': 'report'}
}