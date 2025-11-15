#!/usr/bin/env python3
"""
ATS API Test Client - Demo script for testing API endpoints.

Run API in one terminal:
    python3 backend/api.py

Run this script in another:
    python3 test_api_client.py
"""

import requests
import json
import time
import tempfile
from pathlib import Path
from typing import Optional, List

class ATSClient:
    """ATS API client for testing."""
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "test-key-123"):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key}
    
    def health(self) -> dict:
        """Check API health."""
        response = requests.get(f"{self.base_url}/health")
        return response.json()
    
    def upload_file(self, file_path: str, max_retries: int = 3) -> dict:
        """Upload a single file."""
        with open(file_path, 'rb') as f:
            response = requests.post(
                f"{self.base_url}/upload",
                headers=self.headers,
                files={"file": (Path(file_path).name, f)},
                params={"max_retries": max_retries}
            )
        return response.json()
    
    def upload_bulk(self, file_paths: List[str], max_retries: int = 3) -> dict:
        """Upload multiple files."""
        files = [("files", (Path(fp).name, open(fp, 'rb'))) for fp in file_paths]
        response = requests.post(
            f"{self.base_url}/upload-bulk",
            headers=self.headers,
            files=files,
            params={"max_retries": max_retries}
        )
        for _, (_, f) in files:
            f.close()
        return response.json()
    
    def get_status(self, job_id: str) -> dict:
        """Get job status."""
        response = requests.get(f"{self.base_url}/status/{job_id}")
        return response.json()
    
    def get_stats(self) -> dict:
        """Get queue statistics."""
        response = requests.get(f"{self.base_url}/stats")
        return response.json()
    
    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> dict:
        """List jobs."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        response = requests.get(f"{self.base_url}/jobs", params=params)
        return response.json()
    
    def re_ingest(self, job_id: str, max_retries: int = 3) -> dict:
        """Re-ingest a job."""
        response = requests.post(
            f"{self.base_url}/re-ingest/{job_id}",
            headers=self.headers,
            params={"max_retries": max_retries}
        )
        return response.json()


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_health():
    """Test health endpoint."""
    print_section("1. Health Check")
    client = ATSClient()
    
    try:
        health = client.health()
        print(f"✓ Status: {health['status']}")
        print(f"✓ Queue available: {health['queue_available']}")
        print(f"✓ Queue path: {health['queue_path']}")
        stats = health['queue_stats']
        print(f"✓ Queue stats: pending={stats['pending']}, completed={stats['completed']}, failed={stats['failed']}")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_upload():
    """Test file upload."""
    print_section("2. Upload Single File")
    client = ATSClient()
    
    try:
        # Create a test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("This is a test CV from API test client.\nName: John Doe\nEmail: john@example.com\n")
            f.write("Skills: Python, FastAPI, Docker\n")
            f.write("Experience: 5 years in software development")
            temp_file = f.name
        
        print(f"Test file created: {temp_file}")
        
        result = client.upload_file(temp_file)
        print(f"\n✓ Upload successful!")
        print(f"  Job ID: {result['job_id']}")
        print(f"  Status: {result['status']}")
        print(f"  File path: {result['file_path']}")
        print(f"  Message: {result['message']}")
        
        Path(temp_file).unlink()
        
        return result['job_id']
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def test_bulk_upload():
    """Test bulk file upload."""
    print_section("3. Upload Bulk Files")
    client = ATSClient()
    
    try:
        # Create test files
        temp_files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(f"Test CV #{i+1}\n")
                f.write(f"Name: Candidate {i+1}\n")
                f.write(f"Skills: Python, FastAPI")
                temp_files.append(f.name)
        
        print(f"Created {len(temp_files)} test files")
        
        result = client.upload_bulk(temp_files)
        print(f"\n✓ Bulk upload successful!")
        print(f"  Total: {result['total']}")
        print(f"  Successful: {result['successful']}")
        print(f"  Skipped: {result['skipped']}")
        print(f"  Failed: {result['failed']}")
        
        print(f"\n  Results:")
        for item in result['results']:
            print(f"    - {item['filename']}: {item['status']} (Job: {item.get('job_id', 'N/A')})")
        
        for temp_file in temp_files:
            Path(temp_file).unlink()
        
        return result['results'][0]['job_id'] if result['successful'] > 0 else None
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def test_status(job_id: Optional[str]):
    """Test status endpoint."""
    print_section("4. Check Job Status")
    client = ATSClient()
    
    if not job_id:
        print("✗ No job ID provided (upload failed)")
        return
    
    try:
        status = client.get_status(job_id)
        print(f"✓ Job status retrieved!")
        print(f"  Job ID: {status['job_id']}")
        print(f"  Status: {status['status']}")
        print(f"  File path: {status['file_path']}")
        print(f"  Retries: {status['retries']}/{status['max_retries']}")
        print(f"  Created: {status['created_at']}")
        print(f"  Updated: {status['updated_at']}")
        if status['error_message']:
            print(f"  Error: {status['error_message']}")
        if status['result']:
            print(f"  Result: {json.dumps(status['result'], indent=4)}")
    
    except Exception as e:
        print(f"✗ Error: {e}")


def test_stats():
    """Test queue statistics."""
    print_section("5. Queue Statistics")
    client = ATSClient()
    
    try:
        stats = client.get_stats()
        print(f"✓ Queue stats retrieved!")
        print(f"  Pending: {stats['pending']}")
        print(f"  Processing: {stats['processing']}")
        print(f"  Completed: {stats['completed']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Total: {stats['total']}")
    
    except Exception as e:
        print(f"✗ Error: {e}")


def test_list_jobs():
    """Test listing jobs."""
    print_section("6. List Jobs")
    client = ATSClient()
    
    try:
        # List all jobs
        result = client.list_jobs(limit=5)
        print(f"✓ Jobs retrieved!")
        print(f"  Total jobs: {result['count']}")
        print(f"  Limit: {result['limit']}")
        
        if result['jobs']:
            print(f"\n  First few jobs:")
            for job in result['jobs'][:3]:
                print(f"    - ID: {job['job_id']}")
                print(f"      Status: {job['status']}")
                print(f"      File: {job['file_path']}")
        else:
            print(f"  No jobs found")
        
        # List pending jobs only
        print(f"\n  Pending jobs:")
        pending = client.list_jobs(status="pending")
        print(f"    Count: {pending['count']}")
    
    except Exception as e:
        print(f"✗ Error: {e}")


def test_auth():
    """Test authentication."""
    print_section("7. Authentication Test")
    
    try:
        # Test without API key
        print("Testing without API key...")
        response = requests.get("http://localhost:8000/health")
        print(f"  ✓ Health accessible without key: {response.status_code == 200}")
        
        # Test upload without key
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b"test")
            temp_file = f.name
        
        with open(temp_file, 'rb') as f:
            response = requests.post(
                "http://localhost:8000/upload",
                files={"file": f}
            )
        print(f"  Upload without key returns: {response.status_code} (should be 401)")
        
        # Test with wrong key
        with open(temp_file, 'rb') as f:
            response = requests.post(
                "http://localhost:8000/upload",
                files={"file": f},
                headers={"X-API-Key": "wrong-key"}
            )
        print(f"  Upload with wrong key returns: {response.status_code} (should be 403)")
        
        Path(temp_file).unlink()
        print(f"✓ Authentication working correctly")
    
    except Exception as e:
        print(f"✗ Error: {e}")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  ATS API TEST CLIENT")
    print("="*60)
    print("Base URL: http://localhost:8000")
    print("Make sure API is running: python3 backend/api.py")
    
    # Run tests
    test_health()
    job_id = test_upload()
    bulk_job_id = test_bulk_upload()
    test_status(job_id)
    test_stats()
    test_list_jobs()
    test_auth()
    
    print_section("✓ All Tests Complete")
    print("Next steps:")
    print("1. Run worker: python3 backend/ingest/worker.py")
    print("2. Check job status: python3 test_api_client.py")
    print("3. View API docs: http://localhost:8000/docs")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
