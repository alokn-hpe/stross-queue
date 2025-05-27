from fastapi import FastAPI, UploadFile, Form
from app import db, models
from app.models import ScanStatus, Job
from app.tasks import scan_image_task, check_status_task, report_task
from app.stross_api import get_token

app = FastAPI()

@app.get("/")
async def huho():
    return {"message": "Up and running!"}

@app.post("/initiate/")
async def upload_images_list(file: UploadFile, product_name: str = Form(...), product_version: str = Form(...)):
    content = await file.read()
    image_names = [image.split("\t")[0] for image in content.decode().splitlines() if image.split("\t")]
    token = get_token()

    session = db.SessionLocal()
    job = Job(product_name=product_name, product_version=product_version) # type: ignore
    session.add(job)
    for image in image_names:
        scan = models.ImageScan(image_name=image.strip(), status=ScanStatus.pending, job=job) # type: ignore
        session.add(scan)
    session.commit()

    # Re-fetch and enqueue
    scans = session.query(models.ImageScan).filter_by(status=ScanStatus.pending).all()
    for scan in scans:
        scan_image_task.delay(scan.id, token)
        scan.status = ScanStatus.queued
    session.commit()
    return {"job_id": job.id,"message": f"{len(image_names)} images queued for scanning."}

@app.post("/resume/{job_id}")
async def resume_job(job_id):
    session = db.SessionLocal()
    job = session.query(models.Job).filter_by(id=job_id).first()
    token = get_token()

    # Submit any scans if pending
    pending_scans = session.query(models.ImageScan).filter(job==job, models.ImageScan.status.in_([ScanStatus.queued,ScanStatus.pending,ScanStatus.init_fail])).all() # type: ignore
    for scan in pending_scans:
        scan_image_task.delay(scan.id, token)
        scan.status = ScanStatus.queued
    session.commit()

    # Poll scans which are in_progress
    progress_scans = session.query(models.ImageScan).filter_by(job=job,status=ScanStatus.in_progress).all()
    for scan in progress_scans:
        check_status_task.apply_async((scan.scan_id, token),countdown=30)
    
    # Generate reports for scans which are completed
    completed_scans = session.query(models.ImageScan).filter(job==job, models.ImageScan.status.in_([ScanStatus.completed,ScanStatus.report_generated])).all() # type: ignore
    for scan in completed_scans:
        report_task.apply_async((scan.scan_id, token))

    return {"job_id": job_id, "message":f"{len(pending_scans)} queued for scan, {len(progress_scans)} polled for status, {len(completed_scans)} submitted for report generation"}
