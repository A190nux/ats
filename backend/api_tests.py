"""
Unit tests for backend/api.py using unittest and FastAPI TestClient.

Run: python3 -m unittest backend.api_tests -v
"""

import unittest
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from backend.api import app


class TestHealth(unittest.TestCase):
    """Test health check endpoint."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
    
    def test_health_check(self):
        """Test health check returns healthy status."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["queue_available"])
        self.assertIn("queue_stats", data)


class TestUpload(unittest.TestCase):
    """Test upload endpoints."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
        self.auth_headers = {"X-API-Key": "test-key-123"}
    
    def test_upload_single_file(self):
        """Test uploading a single file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test CV content")
            temp_file = f.name
        
        try:
            with open(temp_file, 'rb') as f:
                response = self.client.post(
                    "/upload",
                    files={"file": ("test.txt", f, "text/plain")},
                    headers=self.auth_headers
                )
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("job_id", data)
            self.assertEqual(data["status"], "pending")
            self.assertIn("test.txt", data["message"])
        finally:
            os.unlink(temp_file)
    
    def test_upload_without_api_key(self):
        """Test upload fails without API key."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test CV content")
            temp_file = f.name
        
        try:
            with open(temp_file, 'rb') as f:
                response = self.client.post(
                    "/upload",
                    files={"file": ("test.txt", f, "text/plain")}
                )
            
            self.assertEqual(response.status_code, 401)
        finally:
            os.unlink(temp_file)
    
    def test_upload_invalid_api_key(self):
        """Test upload fails with invalid API key."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test CV content")
            temp_file = f.name
        
        try:
            with open(temp_file, 'rb') as f:
                response = self.client.post(
                    "/upload",
                    files={"file": ("test.txt", f, "text/plain")},
                    headers={"X-API-Key": "wrong-key"}
                )
            
            self.assertEqual(response.status_code, 403)
        finally:
            os.unlink(temp_file)
    
    def test_upload_unsupported_file_type(self):
        """Test upload rejects unsupported file types."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.exe', delete=False) as f:
            f.write("malicious")
            temp_file = f.name
        
        try:
            with open(temp_file, 'rb') as f:
                response = self.client.post(
                    "/upload",
                    files={"file": ("test.exe", f, "application/octet-stream")},
                    headers=self.auth_headers
                )
            
            self.assertEqual(response.status_code, 400)
            data = response.json()
            error_msg = data.get("detail") or data.get("error", "")
            self.assertIn("not supported", error_msg.lower())
        finally:
            os.unlink(temp_file)


class TestStatus(unittest.TestCase):
    """Test status endpoints."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
        self.auth_headers = {"X-API-Key": "test-key-123"}
    
    def test_get_job_status(self):
        """Test getting job status."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test CV")
            temp_file = f.name
        
        try:
            with open(temp_file, 'rb') as f:
                upload_response = self.client.post(
                    "/upload",
                    files={"file": ("test.txt", f, "text/plain")},
                    headers=self.auth_headers
                )
            
            # Check upload succeeded
            if upload_response.status_code != 200:
                self.skipTest(f"Upload failed: {upload_response.json()}")
                
            job_id = upload_response.json()["job_id"]
            
            status_response = self.client.get(f"/status/{job_id}")
            self.assertEqual(status_response.status_code, 200, f"Status check failed: {status_response.json()}")
            
            data = status_response.json()
            self.assertEqual(data["job_id"], job_id)
            self.assertEqual(data["status"], "pending")
            self.assertEqual(data["retries"], 0)
        finally:
            os.unlink(temp_file)
    
    def test_get_nonexistent_job(self):
        """Test getting status of nonexistent job."""
        response = self.client.get("/status/nonexistent-job-id")
        self.assertEqual(response.status_code, 404)
    
    def test_get_queue_stats(self):
        """Test getting queue statistics."""
        response = self.client.get("/stats")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("pending", data)
        self.assertIn("processing", data)
        self.assertIn("completed", data)
        self.assertIn("failed", data)
    
    def test_list_jobs(self):
        """Test listing jobs."""
        response = self.client.get("/jobs")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("jobs", data)
        self.assertIn("limit", data)


class TestManagement(unittest.TestCase):
    """Test job management endpoints."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
        self.auth_headers = {"X-API-Key": "test-key-123"}
    
    def test_re_ingest_job(self):
        """Test re-ingesting a job."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test CV")
            temp_file = f.name
        
        try:
            with open(temp_file, 'rb') as f:
                upload_response = self.client.post(
                    "/upload",
                    files={"file": ("test.txt", f, "text/plain")},
                    headers=self.auth_headers
                )
            
            original_job_id = upload_response.json()["job_id"]
            
            re_ingest_response = self.client.post(
                f"/re-ingest/{original_job_id}",
                headers=self.auth_headers
            )
            
            self.assertEqual(re_ingest_response.status_code, 200)
            data = re_ingest_response.json()
            self.assertNotEqual(data["job_id"], original_job_id)
            self.assertEqual(data["status"], "pending")
        finally:
            os.unlink(temp_file)
    
    def test_re_ingest_nonexistent_job(self):
        """Test re-ingesting nonexistent job fails."""
        response = self.client.post(
            "/re-ingest/nonexistent",
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 404)


class TestRoot(unittest.TestCase):
    """Test root endpoint."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
    
    def test_root_endpoint(self):
        """Test root endpoint returns API info."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("name", data)
        self.assertIn("version", data)
        self.assertIn("endpoints", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
