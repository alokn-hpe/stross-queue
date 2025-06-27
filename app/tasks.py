from celery import Celery
import datetime
from .db import get_session
from .models import ImageScan, ScanStatus, JobStatus, Job
from .stross_api import start_scan, check_scan_status, download_report, upload_inventory
from logging import getLogger
from dotenv import load_dotenv
import io
import os
import zipfile

load_dotenv()
logger = getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

ARTIFACTORY_USERNAME = os.getenv("ARTIFACTORY_USERNAME")
ARTIFACTORY_PASSWORD = os.getenv("ARTIFACTORY_PASSWORD")

app = Celery('tasks')
app.config_from_object('celeryconfig')

@app.task(bind=True,max_retries=None)
def scan_image_task(self, id, token):
    db = get_session()
    scan = db.query(ImageScan).filter_by(id=id).first()
    job = db.query(Job).filter_by(id=scan.job_id).first()
    payload = {
        "productName": job.product_name,
        "productVersion": job.product_version,
        "artifactType": "container",
        "source": scan.image_name + f"?user={ARTIFACTORY_USERNAME}&token={ARTIFACTORY_PASSWORD}" if scan.image_name.startswith("arti") else ""
    }
    try:
        response = start_scan(payload, token).json()
        logger.debug(response)
    except Exception as e:
        logger.error(e)
        db.close()
        self.retry(countdown=30)
    if int(response["code"]) == 213: # 3 scans in queue code
        scan.status_response = str(response)
        db.commit()
        self.retry(countdown=120)
    elif response["success"] == True:
        scan.status = ScanStatus.in_progress
        scan.job.status = JobStatus.progress
        scan.scan_id = str(response['data']['scanId'])
        scan.status_response = str(response)
        db.commit()
        check_status_task.apply_async((scan.scan_id,token), countdown=30)

@app.task(bind=True,max_retries=50)
def check_status_task(self, scan_id, token):
    db = get_session()
    scan = db.query(ImageScan).filter_by(scan_id=scan_id).first()
    try:
        result = check_scan_status(scan.scan_id, token)
        logger.debug(result)
    except Exception as e:
        logger.error(e)
        db.close()
        self.retry(countdown=30)
    if result["data"]["status"] == 'completed':
        scan.status = ScanStatus.completed
        scan.status_response = str(result)
        db.commit()
        report_task.delay(scan_id, token)
    elif result["data"]["status"] == 'failed':
        scan.status = ScanStatus.failed
        scan.status_response = str(result)
        db.commit()
        scan_image_task.delay(scan.id, token)
    else:
        scan.status_response = str(result)
        db.commit()
        self.retry(countdown=300)

@app.task(bind=True)
def report_task(self, scan_id, token):
    db = get_session()
    scan = db.query(ImageScan).filter_by(scan_id=scan_id).first()

    # Generate Report
    if scan.status == ScanStatus.completed:
        report_bytes = download_report(scan.scan_id, token)
        logger.debug(report_bytes)
        if report_bytes.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(report_bytes.content)) as zip_file:
                zip_file.extractall(f"files/extracted_files_{scan_id}")
                logger.debug("Extracted files:"+str(zip_file.namelist()))
        
            for name in zip_file.namelist():
                if name.endswith(f"{scan_id}.json"):
                    file_to_upload = os.path.join(f"files/extracted_files_{scan_id}", name)
                    scan.report_file = file_to_upload
                    scan.status = ScanStatus.report_generated
                    db.commit()
                    break
        else:
            self.retry(countdown=30)
    elif scan.status == ScanStatus.report_generated:
        file_to_upload = scan.report_file
        db.commit()

    # Upload Inventory
    if not file_to_upload:
        raise Exception("No SPDX-JSON file found in zip to upload")
    
    inv_upload = upload_inventory(file_to_upload, scan, token)
    if inv_upload.status_code == 200:
        logger.info(f"File {file_to_upload} uploaded successfully.")
        scan.status = ScanStatus.inventory_uploaded
        db.commit()
        # Check if all file uploads completed
        if len(list(db.query(ImageScan).filter_by(job=scan.job).all())) == len(list(db.query(ImageScan).filter_by(job=scan.job, status=ScanStatus.inventory_uploaded).all())):
            scan.job.status = JobStatus.completed
            scan.job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
    else:
        logger.error(f"File upload failed: {inv_upload.status_code}, {inv_upload.text}")
        scan.status_response = {inv_upload.text}
        db.commit()
        self.retry(countdown=30)
