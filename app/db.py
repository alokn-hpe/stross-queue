from logging import getLogger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from threading import local
from .models import Base
import os

load_dotenv()
logger = getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./scanner.db")

# Process-local storage
process_local = local()

# Default engine for the main process
default_engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
# Default session factory
default_Session = sessionmaker(bind=default_engine, expire_on_commit=False)
Base.metadata.create_all(bind=default_engine) # type: ignore

def create_engine_for_worker():
    logger.info("Creating a new SQLAlchemy engine for worker process")
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    process_local.engine = engine
    process_local.Session = sessionmaker(bind=engine, expire_on_commit=False)
    return engine

def dispose_engine():
    if hasattr(process_local, 'engine'):
        logger.info("Disposing SQLAlchemy engine for worker process")
        process_local.engine.dispose()
        del process_local.engine
        del process_local.Session

def get_engine():
    # Check if we have a process-local engine
    if hasattr(process_local, 'engine'):
        return process_local.engine
    # Otherwise, return the default engine
    return default_engine

def get_session():
    # Check if we have a process-local Session factory
    if hasattr(process_local, 'Session'):
        return process_local.Session()
    # Otherwise, use the default Session factory
    return default_Session()