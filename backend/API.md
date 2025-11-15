# ATS API Documentation

FastAPI backend for CV ingestion, search, and ranking system.

## Quick Start

### Installation

```bash
pip install fastapi uvicorn
pip install python-multipart  # Required for file uploads
```

### Run API Server

```bash
# Development
python3 backend/api.py

# Production (with Uvicorn)
uvicorn backend.api:app --host 0.0.0.0 --port 8000 --workers 4
```

API available at: `http://localhost:8000`
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Configuration

Set environment variables to customize:

```bash
export API_KEY="your-secure-key"           # Default: test-key-123
export QUEUE_DB="./jobs.db"                # Default: ./jobs.db
export UPLOAD_DIR="./cv_uploads"           # Default: ./cv_uploads
```

## Authentication

All endpoints except `/health`, `/docs`, `/redoc`, and `/` require authentication.

**Header:**
```
X-API-Key: your-api-key
```

**Example:**
```bash
curl -X POST http://localhost:8000/upload \
  -H "X-API-Key: test-key-123" \
  -F "file=@resume.pdf"
```

## API Endpoints

### Health & Info

#### GET /health
Health check and queue status.

**Response:**
```json
{
  "status": "healthy",
  "queue_available": true,
  "queue_path": "./jobs.db",
  "queue_stats": {
    "pending": 0,
    "processing": 0,
    "completed": 24,
    "failed": 0,
    "total": 24
  },
  "timestamp": "2025-11-13T10:30:00"
}
```

#### GET /
API root with endpoint listing.

---

### Upload Endpoints

#### POST /upload
Upload a single CV file for ingestion.

**Parameters:**
- `file` (form-data, required) — CV file (PDF, DOCX, DOC, TXT, JPG, PNG, TIFF)
- `max_retries` (query, optional) — Max retries on failure (default: 3, max: 10)

**Headers:**
- `X-API-Key` (required)

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "File 'resume.pdf' uploaded successfully",
  "file_path": "./cv_uploads/resume.pdf",
  "created_at": "2025-11-13T10:30:00"
}
```

**Examples:**

cURL:
```bash
curl -X POST http://localhost:8000/upload \
  -H "X-API-Key: test-key-123" \
  -F "file=@resume.pdf"
```

Python:
```python
import requests

with open('resume.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/upload',
        headers={'X-API-Key': 'test-key-123'},
        files={'file': f}
    )

job_id = response.json()['job_id']
print(f"Job ID: {job_id}")
```

---

#### POST /upload-bulk
Upload multiple CV files at once.

**Parameters:**
- `files` (form-data, required) — Multiple CV files
- `max_retries` (query, optional) — Max retries per job (default: 3)

**Response:**
```json
{
  "total": 3,
  "successful": 3,
  "skipped": 0,
  "failed": 0,
  "results": [
    {
      "filename": "resume1.pdf",
      "job_id": "...",
      "status": "pending",
      "file_path": "./cv_uploads/resume1.pdf",
      "created_at": "..."
    },
    ...
  ],
  "timestamp": "2025-11-13T10:30:00"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/upload-bulk \
  -H "X-API-Key: test-key-123" \
  -F "files=@resume1.pdf" \
  -F "files=@resume2.docx" \
  -F "files=@resume3.txt"
```

---

#### POST /upload-directory
Enqueue all files in a directory for ingestion.

**Parameters:**
- `directory_path` (query, required) — Path to directory on server
- `max_retries` (query, optional) — Max retries per job (default: 3)

**Response:** Same as `/upload`

**Example:**
```bash
curl -X POST 'http://localhost:8000/upload-directory?directory_path=./cv_uploads' \
  -H "X-API-Key: test-key-123"
```

---

### Status & Monitoring

#### GET /status/{job_id}
Get job status and result.

**Parameters:**
- `job_id` (path, required) — Job ID from upload response

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "file_path": "./cv_uploads/resume.pdf",
  "retries": 0,
  "max_retries": 3,
  "created_at": "2025-11-13T10:30:00",
  "updated_at": "2025-11-13T10:30:05",
  "error_message": null,
  "result": {
    "documents_loaded": 1,
    "type": "pdf",
    "pages": 2
  }
}
```

**Status Values:**
- `pending` — Waiting to be processed
- `processing` — Currently processing
- `completed` — Successfully processed
- `failed` — Failed after max retries

**Example:**
```bash
curl http://localhost:8000/status/550e8400-e29b-41d4-a716-446655440000
```

---

#### GET /stats
Get queue statistics.

**Response:**
```json
{
  "pending": 5,
  "processing": 1,
  "completed": 24,
  "failed": 0,
  "total": 30,
  "timestamp": "2025-11-13T10:30:00"
}
```

---

#### GET /jobs
List all jobs (optionally filtered by status).

**Parameters:**
- `status` (query, optional) — Filter by status: `pending`, `processing`, `completed`, `failed`
- `limit` (query, optional) — Max results (default: 50, max: 500)

**Response:**
```json
{
  "count": 2,
  "limit": 50,
  "status_filter": "pending",
  "jobs": [
    {
      "job_id": "...",
      "status": "pending",
      "file_path": "...",
      "retries": 0,
      "max_retries": 3,
      "created_at": "...",
      "updated_at": "...",
      "error_message": null,
      "result": null
    },
    ...
  ],
  "timestamp": "2025-11-13T10:30:00"
}
```

**Example:**
```bash
curl 'http://localhost:8000/jobs?status=pending&limit=10'
```

---

### Job Management

#### POST /re-ingest/{job_id}
Re-ingest a completed or failed job (creates new job with same path).

**Parameters:**
- `job_id` (path, required) — Original job ID
- `max_retries` (query, optional) — Max retries for new job (default: 3)

**Response:** Same as `/upload`

**Example:**
```bash
curl -X POST 'http://localhost:8000/re-ingest/550e8400-e29b-41d4-a716-446655440000' \
  -H "X-API-Key: test-key-123"
```

---

#### DELETE /jobs/{job_id}
Delete a pending job (admin only).

**Parameters:**
- `job_id` (path, required) — Job ID to delete

**Response:**
```json
{
  "message": "Job deleted",
  "job_id": "..."
}
```

**Example:**
```bash
curl -X DELETE 'http://localhost:8000/jobs/550e8400-e29b-41d4-a716-446655440000' \
  -H "X-API-Key: test-key-123"
```

---

## Python Client Example

```python
import requests
from typing import Optional, List

class ATSClient:
    """Simple ATS API client."""
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "test-key-123"):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key}
    
    def upload_file(self, file_path: str, max_retries: int = 3) -> dict:
        """Upload a single file."""
        with open(file_path, 'rb') as f:
            response = requests.post(
                f"{self.base_url}/upload",
                headers=self.headers,
                files={"file": f},
                params={"max_retries": max_retries}
            )
        return response.json()
    
    def upload_bulk(self, file_paths: List[str], max_retries: int = 3) -> dict:
        """Upload multiple files."""
        files = [("files", open(fp, 'rb')) for fp in file_paths]
        response = requests.post(
            f"{self.base_url}/upload-bulk",
            headers=self.headers,
            files=files,
            params={"max_retries": max_retries}
        )
        for _, f in files:
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


# Usage
if __name__ == "__main__":
    client = ATSClient()
    
    # Upload a file
    result = client.upload_file("./cv_uploads/resume.pdf")
    job_id = result["job_id"]
    print(f"Uploaded: {job_id}")
    
    # Check status
    status = client.get_status(job_id)
    print(f"Status: {status['status']}")
    
    # Get queue stats
    stats = client.get_stats()
    print(f"Queue: {stats['pending']} pending, {stats['completed']} completed")
    
    # List pending jobs
    jobs = client.list_jobs(status="pending")
    print(f"Pending jobs: {jobs['count']}")
```

---

## Error Handling

All errors return JSON with error details:

```json
{
  "error": "Error message"
}
```

**Common Status Codes:**
- `200` — Success
- `400` — Bad request (invalid parameters)
- `401` — Missing API key
- `403` — Invalid API key
- `404` — Resource not found
- `413` — File too large
- `500` — Server error

---

## Integration with Worker

The API enqueues jobs to a SQLite database. Process them with the worker:

```bash
# Terminal 1: Run API
python3 backend/api.py

# Terminal 2: Run worker
python3 backend/ingest/worker.py
```

The worker continuously polls the queue and processes jobs with OCR fallback for scanned PDFs.

---

## Deployment

### Docker

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

ENV API_KEY="production-key"
ENV QUEUE_DB="/data/jobs.db"
ENV UPLOAD_DIR="/data/cv_uploads"

CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    environment:
      API_KEY: "your-secure-key"
      QUEUE_DB: "/data/jobs.db"
      UPLOAD_DIR: "/data/cv_uploads"

  worker:
    build: .
    volumes:
      - ./data:/data
    environment:
      QUEUE_DB: "/data/jobs.db"
      UPLOAD_DIR: "/data/cv_uploads"
    command: python3 backend/ingest/worker.py
    depends_on:
      - api
```

Then run:
```bash
docker-compose up
```
