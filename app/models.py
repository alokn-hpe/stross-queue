from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel
import shortuuid
import enum
import datetime

###### REQUEST MODELS
class Product(BaseModel):
    name: str
    version: str

###### DB MODELS
Base = declarative_base()

class ScanStatus(str, enum.Enum):
    pending = "PENDING"
    queued = "QUEUED"
    init_fail = "INIT_FAIL"
    in_progress = "IN_PROGRESS"
    completed = "COMPLETED"
    report_generated = "REPORT_GENERATED"
    inventory_uploaded = "INVENTORY_UPLOADED"
    failed = "FAILED"

class JobStatus(str, enum.Enum):
    init = "INITIATED"
    progress = "IN_PROGRESS"
    completed = "COMPLETED"

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(22), primary_key=True, default=shortuuid.uuid)
    product_name = Column(String, nullable=False)
    product_version = Column(String, nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.init)
    init_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))
    completed_at = Column(DateTime)
    
    image_scans = relationship("ImageScan", back_populates="job")

class ImageScan(Base):
    __tablename__ = "image_scans"

    id = Column(Integer, primary_key=True, index=True)
    image_name = Column(String, nullable=False)
    scan_id = Column(String, nullable=True, index=True)
    status = Column(Enum(ScanStatus), default=ScanStatus.pending)
    status_response = Column(String, nullable=True)
    report_file = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))

    job_id = Column(Integer, ForeignKey('jobs.id'))
    job = relationship("Job", back_populates="image_scans")
