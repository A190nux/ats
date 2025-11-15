"""
Test suite for ingestion queue and worker.

Tests job enqueue, retrieval, status updates, retries, and worker processing.
"""

import os
import tempfile
import unittest
import time
from pathlib import Path

from backend.ingest.job_queue import IngestionQueue, JobStatus, Job


class TestIngestionQueue(unittest.TestCase):
    """Test ingestion queue."""
    
    def setUp(self):
        """Create a temporary queue for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.queue_path = os.path.join(self.temp_dir, "test_queue.db")
        self.queue = IngestionQueue(self.queue_path)
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_enqueue_job(self):
        """Test enqueueing a job."""
        job_id = self.queue.enqueue("/path/to/file.pdf")
        self.assertIsNotNone(job_id)
        self.assertEqual(len(job_id), 36)  # UUID4 length
        
        # Retrieve the job
        job = self.queue.get_job(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job.file_path, "/path/to/file.pdf")
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.retries, 0)
    
    def test_get_pending_job(self):
        """Test retrieving the next pending job."""
        job_id_1 = self.queue.enqueue("/path/to/file1.pdf")
        job_id_2 = self.queue.enqueue("/path/to/file2.pdf")
        
        # Get first pending job
        job = self.queue.get_pending_job()
        self.assertIsNotNone(job)
        self.assertEqual(job.job_id, job_id_1)
        
        # Mark as completed
        self.queue.mark_completed(job_id_1)
        
        # Get second pending job
        job = self.queue.get_pending_job()
        self.assertIsNotNone(job)
        self.assertEqual(job.job_id, job_id_2)
    
    def test_mark_completed(self):
        """Test marking a job as completed."""
        job_id = self.queue.enqueue("/path/to/file.pdf")
        result = {"documents_loaded": 5}
        
        self.queue.mark_completed(job_id, result)
        
        job = self.queue.get_job(job_id)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.result, result)
        self.assertIsNone(job.error_message)
    
    def test_mark_failed_with_retry(self):
        """Test marking a job as failed with retry."""
        job_id = self.queue.enqueue("/path/to/file.pdf", max_retries=3)
        
        # First failure: should retry
        self.queue.mark_failed(job_id, "Error 1")
        job = self.queue.get_job(job_id)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.retries, 1)
        self.assertEqual(job.error_message, "Error 1")
        
        # Second failure: should retry
        self.queue.mark_failed(job_id, "Error 2")
        job = self.queue.get_job(job_id)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.retries, 2)
        
        # Third failure: should retry
        self.queue.mark_failed(job_id, "Error 3")
        job = self.queue.get_job(job_id)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.retries, 3)
    
    def test_mark_failed_max_retries(self):
        """Test that job is marked as failed after max retries."""
        job_id = self.queue.enqueue("/path/to/file.pdf", max_retries=2)
        
        # Exhaust retries
        self.queue.mark_failed(job_id, "Error 1")
        self.queue.mark_failed(job_id, "Error 2")
        self.queue.mark_failed(job_id, "Error 3")  # This should permanently fail
        
        job = self.queue.get_job(job_id)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.retries, 2)
    
    def test_get_stats(self):
        """Test queue statistics."""
        self.queue.enqueue("/path/to/file1.pdf")
        self.queue.enqueue("/path/to/file2.pdf")
        job_id_3 = self.queue.enqueue("/path/to/file3.pdf")
        
        # Mark one as completed
        self.queue.mark_completed(job_id_3)
        
        stats = self.queue.get_stats()
        self.assertEqual(stats[JobStatus.PENDING], 2)
        self.assertEqual(stats[JobStatus.COMPLETED], 1)
        self.assertEqual(stats[JobStatus.PROCESSING], 0)
        self.assertEqual(stats[JobStatus.FAILED], 0)
    
    def test_get_all_jobs(self):
        """Test retrieving all jobs."""
        job_ids = []
        for i in range(5):
            job_id = self.queue.enqueue(f"/path/to/file{i}.pdf")
            job_ids.append(job_id)
        
        # Get all jobs
        jobs = self.queue.get_all_jobs(limit=10)
        self.assertEqual(len(jobs), 5)
        
        # Get pending jobs only
        jobs = self.queue.get_all_jobs(status=JobStatus.PENDING)
        self.assertEqual(len(jobs), 5)
        
        # Mark one as completed and check
        self.queue.mark_completed(job_ids[0])
        jobs = self.queue.get_all_jobs(status=JobStatus.PENDING)
        self.assertEqual(len(jobs), 4)
    
    def test_mark_processing(self):
        """Test marking a job as processing."""
        job_id = self.queue.enqueue("/path/to/file.pdf")
        
        self.queue.mark_processing(job_id)
        
        job = self.queue.get_job(job_id)
        self.assertEqual(job.status, JobStatus.PROCESSING)
    
    def test_job_timestamps(self):
        """Test that job timestamps are set correctly."""
        job_id = self.queue.enqueue("/path/to/file.pdf")
        job = self.queue.get_job(job_id)
        
        self.assertIsNotNone(job.created_at)
        self.assertIsNotNone(job.updated_at)
        
        # Wait and update
        time.sleep(0.1)
        self.queue.mark_completed(job_id)
        job = self.queue.get_job(job_id)
        
        # updated_at should be more recent than created_at
        self.assertGreater(job.updated_at, job.created_at)
    
    def test_to_dict(self):
        """Test Job.to_dict() serialization."""
        job_id = self.queue.enqueue("/path/to/file.pdf")
        job = self.queue.get_job(job_id)
        
        job_dict = job.to_dict()
        self.assertIsInstance(job_dict, dict)
        self.assertEqual(job_dict['job_id'], job_id)
        self.assertEqual(job_dict['file_path'], "/path/to/file.pdf")
        self.assertEqual(job_dict['status'], JobStatus.PENDING)


if __name__ == '__main__':
    unittest.main()
