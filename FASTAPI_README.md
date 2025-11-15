# FastAPI Backend for ATS

Production-ready REST API for CV ingestion, job queueing, and status tracking.

## Overview

The API provides:
- **File uploads** — Single, bulk, and directory uploads
- **Job management** — Enqueue, track, and re-ingest jobs
- **Queue monitoring** — Statistics, job filtering, status tracking
- **Authentication** — API key-based security
- **OpenAPI docs** — Auto-generated Swagger UI and ReDoc

## Quick Start

### Installation

```bash
# Install dependencies
pip install fastapi uvicorn python-multipart

# Or from requirements.txt
pip install -r requirements.txt
```

### Run API Server

```bash
# Development (single worker, auto-reload)
python3 backend/api.py

# Or with uvicorn directly
uvicorn backend.api:app --reload --port 8000

# Production (multiple workers)
uvicorn backend.api:app --host 0.0.0.0 --port 8000 --workers 4
```

API will be available at:
- **API Base**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Configuration

Set environment variables to customize behavior:

```bash
export API_KEY="your-secret-key"           # Default: test-key-123
export QUEUE_DB="./jobs.db"                # SQLite database path
export UPLOAD_DIR="./cv_uploads"           # Where uploaded files are saved
```

## API Endpoints

### Public Endpoints (No Authentication)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check with queue stats |
| GET | `/` | API info and endpoint listing |
| GET | `/docs` | Swagger UI documentation |
| GET | `/redoc` | ReDoc documentation |

### Protected Endpoints (Require X-API-Key)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload single CV file |
| POST | `/upload-bulk` | Upload multiple CV files |
| POST | `/upload-directory` | Enqueue directory for processing |
| GET | `/status/{job_id}` | Get job status and result |
| GET | `/stats` | Get queue statistics |
| GET | `/jobs` | List all jobs (with optional status filter) |
| POST | `/re-ingest/{job_id}` | Re-ingest a job |
| DELETE | `/jobs/{job_id}` | Delete pending job (admin) |

## Authentication

All protected endpoints require the `X-API-Key` header:

```bash
curl -H "X-API-Key: test-key-123" \
     -F "file=@resume.pdf" \
     http://localhost:8000/upload
```

## Usage Examples

### 1. Upload a File

```bash
curl -X POST http://localhost:8000/upload \
  -H "X-API-Key: test-key-123" \
  -F "file=@resume.pdf"
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "File 'resume.pdf' uploaded successfully",
  "file_path": "./cv_uploads/resume.pdf",
  "created_at": "2025-11-13T10:30:00"
}
```

### 2. Check Job Status

```bash
curl http://localhost:8000/status/550e8400-e29b-41d4-a716-446655440000
```

Response:
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
    "documents_loaded": 1
  }
}
```

### 3. Get Queue Stats

```bash
curl http://localhost:8000/stats
```

Response:
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

### 4. List Jobs by Status

```bash
curl 'http://localhost:8000/jobs?status=pending&limit=10'
```

### 5. Upload Multiple Files

```bash
curl -X POST http://localhost:8000/upload-bulk \
  -H "X-API-Key: test-key-123" \
  -F "files=@resume1.pdf" \
  -F "files=@resume2.docx" \
  -F "files=@resume3.txt"
```

### 6. Re-ingest a Job

```bash
curl -X POST http://localhost:8000/re-ingest/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: test-key-123"
```

## Python Client

See `test_api_client.py` for a complete Python client example:

```bash
python3 test_api_client.py
```

Or use it in your code:

```python
import requests

# Upload a file
with open('resume.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/upload',
        headers={'X-API-Key': 'test-key-123'},
        files={'file': f}
    )

job_id = response.json()['job_id']

# Check status
status = requests.get(f'http://localhost:8000/status/{job_id}')
print(status.json())
```

## Integration with Worker

The API enqueues jobs to SQLite. Process them with the worker:

```bash
# Terminal 1: Run API
python3 backend/api.py

# Terminal 2: Run Worker
python3 backend/ingest/worker.py

# Terminal 3: Test
python3 test_api_client.py
```

The worker polls the queue and processes jobs with:
- Automatic retry on failure
- OCR support for scanned PDFs
- Multiple format support (PDF, DOCX, DOC, TXT, JPG, PNG)

## Job Lifecycle

1. **Pending** — Job is queued, waiting for worker
2. **Processing** — Worker is processing the job
3. **Completed** — Job processed successfully, result stored
4. **Failed** — Job failed after max retries exhausted

Failed jobs remain in the database for inspection. Re-ingest or delete them:

```bash
# Re-ingest a failed job
curl -X POST http://localhost:8000/re-ingest/job-id \
  -H "X-API-Key: test-key-123"

# Delete a pending job
curl -X DELETE http://localhost:8000/jobs/job-id \
  -H "X-API-Key: test-key-123"
```

## Supported File Formats

- **Documents**: PDF, DOCX, DOC, TXT
- **Images**: JPG, JPEG, PNG, TIFF (OCR enabled)

Maximum file size: 50 MB (configurable in `backend/api.py`)

## Error Handling

The API returns standardized error responses:

```json
{
  "error": "Invalid API key"
}
```

**Common Status Codes:**
- `200` — Success
- `400` — Bad request (invalid parameters, unsupported format)
- `401` — Missing API key
- `403` — Invalid API key
- `404` — Resource not found
- `413` — File too large
- `500` — Server error

## Performance

- **Upload**: ~100ms for small files
- **Status check**: ~10ms
- **Queue stats**: ~10ms
- **Job processing**: 1-5 seconds per file (depends on OCR)

For bulk uploads and processing:
- Run worker in separate process/container
- Use multiple workers for parallelization
- Monitor queue stats for bottlenecks

## Deployment

### Docker

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

ENV API_KEY="production-key"
ENV QUEUE_DB="/data/jobs.db"
ENV UPLOAD_DIR="/data/cv_uploads"

EXPOSE 8000

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
      API_KEY: "your-secret-key"
      QUEUE_DB: "/data/jobs.db"
      UPLOAD_DIR: "/data/cv_uploads"

  worker:
    build: .
    volumes:
      - ./data:/data
    environment:
      QUEUE_DB: "/data/jobs.db"
    command: python3 backend/ingest/worker.py
    depends_on:
      - api
```

Run with: `docker-compose up`

### Nginx Reverse Proxy

```nginx
upstream api {
    server localhost:8000;
}

server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # Increase timeout for file uploads
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
    }
}
```

## Testing

Run the test suite:

```bash
# Unit tests with pytest
python3 -m pytest backend/api_tests.py -v

# Manual testing with client script
python3 test_api_client.py
```

Tests cover:
- Upload (single, bulk, directory)
- Status checking
- Queue statistics
- Job listing
- Re-ingestion
- Authentication
- Error handling

## Monitoring & Logging

The API logs to console with timestamp and level:

```
2025-11-13 18:34:56 - backend.ingest.queue - INFO - Queue database initialized at ./jobs.db
2025-11-13 18:35:00 - backend.api - INFO - File saved: ./cv_uploads/resume.pdf
2025-11-13 18:35:01 - backend.api - INFO - Job enqueued: 550e8400... for ./cv_uploads/resume.pdf
```

Monitor queue health:

```bash
# Check queue stats
curl http://localhost:8000/stats

# List failed jobs for inspection
curl 'http://localhost:8000/jobs?status=failed&limit=50'

# Check health
curl http://localhost:8000/health
```

## Troubleshooting

**API won't start**
- Check API_KEY and port availability
- Ensure SQLite is writable: `chmod 666 jobs.db`

**Uploads fail**
- Verify file format is supported
- Check file size < 50 MB
- Ensure upload directory is writable

**Jobs stuck in "processing"**
- Check worker is running: `ps aux | grep worker.py`
- Check logs: `tail -f ingestion_worker.log`
- Manually mark job as failed: Check queue.py `mark_failed()` method

**OCR not working**
- Verify Tesseract installed: `which tesseract`
- Check if pytesseract is available: `python3 -c "import pytesseract; print(pytesseract.pytesseract.tesseract_cmd)"`

## Security Considerations

- **API Key**: Change from default `test-key-123` in production
- **CORS**: Currently allows all origins; restrict in production
- **File Uploads**: Validate file types on client and server
- **Rate Limiting**: Add rate limiting middleware for production
- **HTTPS**: Use HTTPS/TLS in production
- **Database**: Backup SQLite database regularly

## Future Enhancements

- [ ] Rate limiting per API key
- [ ] Webhook callbacks on job completion
- [ ] Batch processing with progress tracking
- [ ] Job priority queues
- [ ] Result caching and pagination
- [ ] Metrics export (Prometheus)
- [ ] Role-based access control (RBAC)
- [ ] Audit logging
- [ ] WebSocket support for real-time updates

See `docs/schema_audit.md` and `backend/ingest/QUEUE.md` for related documentation.
