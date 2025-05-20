from celery import Celery
import datetime
from .db import SessionLocal
from .models import ImageScan, ScanStatus, JobStatus
from .stross_api import start_scan, check_scan_status, download_report, upload_inventory, get_token
from dotenv import load_dotenv
import io
import os
import zipfile

load_dotenv()

ARTIFACTORY_USERNAME = os.getenv("ARTIFACTORY_USERNAME")
ARTIFACTORY_PASSWORD = os.getenv("ARTIFACTORY_PASSWORD")

app = Celery('tasks')
app.config_from_object('celeryconfig')

@app.task(bind=True,max_retries=50)
def scan_image_task(self, id, token):
    db = SessionLocal()
    scan = db.query(ImageScan).filter_by(id=id).first()
    try:
        payload = {
            "productName": scan.job.product_name,
            "productVersion": scan.job.product_version,
            "artifactType": "container",
            "source": scan.image_name + f"?user={ARTIFACTORY_USERNAME}&token={ARTIFACTORY_PASSWORD}" if scan.image_name.startswith("arti") else ""
        }
        response = start_scan(payload, token)
        if int(response["code"]) == 420:
            raise self.retry(countdown=90)
        elif response["success"] == True:
            scan.status = ScanStatus.in_progress
            scan.job.status = JobStatus.progress
            scan.scan_id = int(response['data']['scanId'])
            db.commit()
            check_status_task.apply_async((scan.scan_id,token), countdown=30)

    except Exception as e:
        scan.status = ScanStatus.init_fail
        db.commit()
        raise e

@app.task(bind=True,max_retries=20)
def check_status_task(self, scan_id, token):
    db = SessionLocal()
    scan = db.query(ImageScan).filter_by(scan_id=scan_id).first()
    try:
        result = check_scan_status(scan.scan_id, token)
    except Exception as e:
        print(e)
        self.retry(countdown=30)
    print(result)
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
        self.retry(countdown=90)

@app.task(bind=True)
def report_task(self, scan_id, token):
    db = SessionLocal()
    scan = db.query(ImageScan).filter_by(scan_id=scan_id).first()

    # Generate Report
    if scan.status == ScanStatus.completed:
        report_bytes = download_report(scan.scan_id, token)
        if report_bytes.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(report_bytes.content)) as zip_file:
                zip_file.extractall(f"files/extracted_files_{scan_id}")
                print("Extracted files:", zip_file.namelist())
        
            for name in zip_file.namelist():
                if name.endswith(f"{scan_id}.json"):
                    file_to_upload = os.path.join(f"files/extracted_files_{scan_id}", name)
                    scan.report_file = file_to_upload
                    scan.status = ScanStatus.report_generated
                    db.commit()
                    break
        else:
            print(report_bytes.json())
            self.retry(countdown=30)
    elif scan.status == ScanStatus.report_generated:
        file_to_upload = scan.report_file

    # Upload Inventory
    if not file_to_upload:
        raise Exception("No SPDX-JSON file found in zip to upload")
    
    inv_upload = upload_inventory(file_to_upload, scan, token)
    if inv_upload.status_code == 200:
        print(f"File {file_to_upload} uploaded successfully.")
        scan.status = ScanStatus.inventory_uploaded
        db.commit()
        # Check if all file uploads completed
        if len(db.query(ImageScan).filter_by(job=scan.job)) == len(db.query(ImageScan).filter_by(job=scan.job, status=ScanStatus.inventory_uploaded)):
            scan.job.status = JobStatus.completed
            scan.job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
    else:
        print(f"File upload failed: {inv_upload.status_code}, {inv_upload.text}")
        self.retry(countdown=30)
