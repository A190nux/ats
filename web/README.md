# Streamlit Web UI for ATS

Minimal, beautiful web interface for CV ingestion, job tracking, and candidate search using Streamlit.

## Quick Start

### Installation

```bash
pip install streamlit requests

# Or from requirements.txt
pip install -r requirements.txt
```

### Run the App

```bash
# Make sure API is running in another terminal
python3 backend/api.py

# In another terminal, start the worker
python3 backend/ingest/worker.py

# Then run the Streamlit app
streamlit run web/app.py
```

The app will open at: **http://localhost:8501**

## Features

### 📤 Upload Tab
- **Drag-and-drop file uploads** — Drop files or click to browse
- **Bulk upload** — Upload multiple CVs at once
- **Progress tracking** — See upload status in real-time
- **Format support** — PDF, DOCX, DOC, TXT, JPG, PNG, TIFF

### 📊 Dashboard Tab
- **Queue statistics** — Pending, processing, completed, failed counts
- **Real-time updates** — Auto-refresh statistics
- **Activity timeline** — Recent uploads and processing history

### 📋 Jobs Tab
- **Job listing** — View all ingestion jobs
- **Status filtering** — Filter by pending, processing, completed, failed
- **Job details** — Expand for full job information (ID, timestamps, results)
- **Job management** — Re-ingest or retry failed jobs
- **Pagination** — Configurable job list limit (5-100)

### 💬 Chat Tab
- **RAG queries** — Ask questions about candidate CVs (coming soon)
- **Semantic search** — Find relevant candidates
- **Context-aware responses** — Get answers with source citations

## Configuration

### API Configuration

The app expects the API to be running at `http://localhost:8000` with API key `test-key-123`.

To change these settings:

**Option 1: Environment Variables**
```bash
export API_URL="http://your-api:8000"
export API_KEY="your-secret-key"
streamlit run web/app.py
```

**Option 2: Streamlit Secrets**
Edit `.streamlit/secrets.toml`:
```toml
api_url = "http://your-api:8000"
api_key = "your-secret-key"
```

**Option 3: In the UI**
- Click the ⚙️ Settings button in the sidebar
- Update API URL and key
- Click Save

### Streamlit Configuration

Edit `.streamlit/config.toml` to customize:
- Theme colors (primary, background, text)
- Port and server settings
- Upload size limits
- Logging levels

## Usage

### Uploading Files

1. Click the **📤 Upload** tab
2. Drag files into the upload area (or click to browse)
3. Select files to upload
4. Click **✅ Upload Files**
5. Monitor progress in the dashboard

### Tracking Jobs

1. Click the **📋 Jobs** tab
2. Select a status filter (all, pending, processing, completed, failed)
3. Click **🔄 Refresh** to update the list
4. Click **📊** to expand job details
5. Click **🔄** button to retry a failed job

### Managing Uploads

- **View Details**: Click 📊 button to see job information
- **Re-ingest**: Click 🔄 button to re-process a job
- **Filter**: Select status to filter job list
- **Pagination**: Adjust limit to show more/fewer jobs

## Architecture

### Frontend → API → Queue → Worker → Chroma

```
┌─────────────────────────────────────────────────────────────┐
│                  Streamlit Web UI (Frontend)                │
│  - File uploads, job tracking, chat interface, dashboard    │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP/JSON
┌─────────────────────▼───────────────────────────────────────┐
│              FastAPI Backend (backend/api.py)               │
│  - /upload, /upload-bulk, /status, /stats, /re-ingest      │
└─────────────────────┬───────────────────────────────────────┘
                      │ SQLite
┌─────────────────────▼───────────────────────────────────────┐
│          Ingestion Queue (backend/ingest/queue.py)          │
│  - Job persistence, status tracking, retry logic            │
└─────────────────────┬───────────────────────────────────────┘
                      │ Polls
┌─────────────────────▼───────────────────────────────────────┐
│          Worker Process (backend/ingest/worker.py)          │
│  - Processes jobs, calls load_documents(), retries on error │
└─────────────────────┬───────────────────────────────────────┘
                      │ Loads
┌─────────────────────▼───────────────────────────────────────┐
│         Document Loader (backend/ingest/loader.py)          │
│  - Multi-format support, OCR fallback for scanned PDFs       │
└─────────────────────┬───────────────────────────────────────┘
                      │ Embeddings
┌─────────────────────▼───────────────────────────────────────┐
│              Chroma Vector Database                         │
│  - Persistent document embeddings for search & RAG          │
└─────────────────────────────────────────────────────────────┘
```

## Performance

- **Upload**: ~100-500ms per file (depends on network)
- **Job tracking**: Real-time updates via polling (2-5 second refresh)
- **Dashboard**: ~50-100ms to load statistics
- **Bulk operations**: Handles 100+ files with pagination

## Troubleshooting

### API Connection Error

**Problem**: "Cannot connect to API at http://localhost:8000"

**Solution**:
```bash
# Check if API is running
curl http://localhost:8000/health

# If not running, start it
python3 backend/api.py
```

### Files Not Uploading

**Problem**: Upload fails silently or shows error

**Solutions**:
1. Check API key is correct (⚙️ Settings)
2. Verify file format is supported
3. Check file size < 50 MB
4. Ensure upload directory is writable

### Jobs Stuck in Processing

**Problem**: Jobs stay in "processing" status

**Solutions**:
1. Check worker is running: `ps aux | grep worker.py`
2. Start worker: `python3 backend/ingest/worker.py`
3. Check logs: `tail -f ingestion_worker.log`

### Slow Performance

**Problem**: Dashboard is slow or jobs take too long

**Solutions**:
1. Reduce job list limit (📋 Jobs tab)
2. Start another worker process for parallelization
3. Check system resources (CPU, memory, disk)

## Deployment

### Local Development

```bash
# Terminal 1
python3 backend/api.py

# Terminal 2
python3 backend/ingest/worker.py

# Terminal 3
streamlit run web/app.py
```

### Docker

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8501 8000

CMD ["streamlit", "run", "web/app.py"]
```

### Docker Compose

```yaml
services:
  app:
    build: .
    ports:
      - "8501:8501"
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      API_URL: "http://localhost:8000"
      API_KEY: "your-secret-key"
```

## File Structure

```
web/
├── app.py                  # Main Streamlit application
├── README.md              # This file
└── requirements.txt       # Python dependencies

.streamlit/
├── config.toml           # Streamlit configuration
└── secrets.toml          # Secrets (API key, URL)
```

## Security Considerations

- **API Key**: Store in `.streamlit/secrets.toml` (not in code)
- **HTTPS**: Use reverse proxy (Nginx) for HTTPS in production
- **Authentication**: Implement Streamlit authentication for multi-user setup
- **Rate Limiting**: Add rate limiting to API for protection

## Future Enhancements

- [ ] Chat interface with RAG queries
- [ ] Semantic search of uploaded CVs
- [ ] Candidate shortlisting and ranking
- [ ] Export to CSV/PDF
- [ ] User authentication and multi-user support
- [ ] Advanced filtering and search
- [ ] Batch operations
- [ ] Dark mode theme

## License

MIT - See LICENSE file
