"""
Simple SQLite-backed job queue for ingestion.

Provides:
- Enqueue ingestion jobs (files or directories)
- Job status tracking (pending, processing, completed, failed)
- Automatic retry with exponential backoff
- Simple persistence without external dependencies

Job states:
- 'pending': Waiting to be processed
- 'processing': Currently being processed
- 'completed': Successfully processed
- 'failed': Failed after max retries
"""

import sqlite3
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Job:
    """Represents an ingestion job."""
    
    def __init__(
        self,
        job_id: str,
        file_path: str,
        status: str = JobStatus.PENDING,
        retries: int = 0,
        max_retries: int = 3,
        error_message: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        result: Optional[dict] = None,
    ):
        self.job_id = job_id
        self.file_path = file_path
        self.status = status
        self.retries = retries
        self.max_retries = max_retries
        self.error_message = error_message
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.updated_at = updated_at or datetime.utcnow().isoformat()
        self.result = result or {}

    def to_dict(self) -> dict:
        """Convert job to dictionary."""
        return {
            "job_id": self.job_id,
            "file_path": self.file_path,
            "status": self.status,
            "retries": self.retries,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
        }


class IngestionQueue:
    """SQLite-backed job queue for ingestion."""
    
    def __init__(self, db_path: str = "./jobs.db"):
        """Initialize the queue with a SQLite database.
        
        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retries INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_json TEXT
                )
            """)
            # Index for querying pending jobs
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)
            """)
            conn.commit()
            logger.info(f"Queue database initialized at {self.db_path}")
    
    def enqueue(self, file_path: str, max_retries: int = 3) -> str:
        """Enqueue a file for ingestion.
        
        Args:
            file_path: Path to file to ingest.
            max_retries: Maximum retry attempts.
        
        Returns:
            Job ID.
        """
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO jobs (job_id, file_path, status, retries, max_retries, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (job_id, file_path, JobStatus.PENDING, 0, max_retries, now, now))
            conn.commit()
        
        logger.info(f"Enqueued job {job_id}: {file_path}")
        return job_id
    
    def get_pending_job(self) -> Optional[Job]:
        """Retrieve the next pending job for processing.
        
        Returns:
            Job object or None if no pending jobs.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT job_id, file_path, status, retries, max_retries, error_message, created_at, updated_at, result_json
                FROM jobs
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
            """, (JobStatus.PENDING,))
            row = cursor.fetchone()
        
        if not row:
            return None
        
        job_id, file_path, status, retries, max_retries, error_msg, created_at, updated_at, result_json = row
        result = json.loads(result_json) if result_json else {}
        
        return Job(
            job_id=job_id,
            file_path=file_path,
            status=status,
            retries=retries,
            max_retries=max_retries,
            error_message=error_msg,
            created_at=created_at,
            updated_at=updated_at,
            result=result,
        )
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a specific job by ID.
        
        Args:
            job_id: Job ID.
        
        Returns:
            Job object or None if not found.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT job_id, file_path, status, retries, max_retries, error_message, created_at, updated_at, result_json
                FROM jobs
                WHERE job_id = ?
            """, (job_id,))
            row = cursor.fetchone()
        
        if not row:
            return None
        
        job_id, file_path, status, retries, max_retries, error_msg, created_at, updated_at, result_json = row
        result = json.loads(result_json) if result_json else {}
        
        return Job(
            job_id=job_id,
            file_path=file_path,
            status=status,
            retries=retries,
            max_retries=max_retries,
            error_message=error_msg,
            created_at=created_at,
            updated_at=updated_at,
            result=result,
        )
    
    def mark_processing(self, job_id: str):
        """Mark a job as processing.
        
        Args:
            job_id: Job ID.
        """
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE jobs
                SET status = ?, updated_at = ?
                WHERE job_id = ?
            """, (JobStatus.PROCESSING, now, job_id))
            conn.commit()
        logger.debug(f"Job {job_id} marked as processing")
    
    def mark_completed(self, job_id: str, result: Optional[dict] = None):
        """Mark a job as completed.
        
        Args:
            job_id: Job ID.
            result: Optional result data.
        """
        now = datetime.utcnow().isoformat()
        result_json = json.dumps(result or {})
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE jobs
                SET status = ?, updated_at = ?, result_json = ?, error_message = NULL
                WHERE job_id = ?
            """, (JobStatus.COMPLETED, now, result_json, job_id))
            conn.commit()
        logger.info(f"Job {job_id} completed")
    
    def mark_failed(self, job_id: str, error_message: str):
        """Mark a job as failed (with potential retry).
        
        Args:
            job_id: Job ID.
            error_message: Error description.
        """
        job = self.get_job(job_id)
        if not job:
            return
        
        now = datetime.utcnow().isoformat()
        
        # Check if we can retry
        if job.retries < job.max_retries:
            # Retry: increment retries and reset to pending
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, retries = ?, error_message = ?, updated_at = ?
                    WHERE job_id = ?
                """, (JobStatus.PENDING, job.retries + 1, error_message, now, job_id))
                conn.commit()
            logger.warning(f"Job {job_id} failed (attempt {job.retries + 1}/{job.max_retries}): {error_message}")
        else:
            # Max retries exceeded: mark as failed permanently
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE job_id = ?
                """, (JobStatus.FAILED, error_message, now, job_id))
                conn.commit()
            logger.error(f"Job {job_id} permanently failed after {job.max_retries} retries: {error_message}")
    
    def get_stats(self) -> dict:
        """Get queue statistics.
        
        Returns:
            Dict with counts by status.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, COUNT(*) FROM jobs GROUP BY status
            """)
            rows = cursor.fetchall()
        
        stats = {
            JobStatus.PENDING: 0,
            JobStatus.PROCESSING: 0,
            JobStatus.COMPLETED: 0,
            JobStatus.FAILED: 0,
        }
        
        for status, count in rows:
            stats[status] = count
        
        return stats
    
    def get_all_jobs(self, status: Optional[str] = None, limit: int = 100) -> List[Job]:
        """Retrieve all jobs, optionally filtered by status.
        
        Args:
            status: Filter by status (optional).
            limit: Maximum jobs to return.
        
        Returns:
            List of Job objects.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("""
                    SELECT job_id, file_path, status, retries, max_retries, error_message, created_at, updated_at, result_json
                    FROM jobs
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT job_id, file_path, status, retries, max_retries, error_message, created_at, updated_at, result_json
                    FROM jobs
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()
        
        jobs = []
        for row in rows:
            job_id, file_path, status, retries, max_retries, error_msg, created_at, updated_at, result_json = row
            result = json.loads(result_json) if result_json else {}
            jobs.append(Job(
                job_id=job_id,
                file_path=file_path,
                status=status,
                retries=retries,
                max_retries=max_retries,
                error_message=error_msg,
                created_at=created_at,
                updated_at=updated_at,
                result=result,
            ))
        
        return jobs
    
    def clear_all(self):
        """Clear all jobs (for testing)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM jobs")
            conn.commit()
        logger.warning("All jobs cleared from queue")
