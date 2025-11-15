# Docker Deployment Guide

This document explains how to run the ATS (Applicant Tracking System) stack using Docker Compose.

## Prerequisites

1. **Docker** (v20.10+) and **Docker Compose** (v2.0+)
   - Install from: https://docs.docker.com/get-docker/

2. **Optional: NVIDIA GPU support** (for faster LLM inference)
   - Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
   - Uncomment the GPU section in `docker-compose.yml` under the `ollama` service

3. **Disk space:**
   - Ollama models: ~5–10 GB (depends on model size)
   - Chroma DB: ~1–5 GB (depends on number of CVs)
   - Code & images: ~2 GB

## Quick Start

### 1. Clone and setup the environment

```bash
cd /path/to/ats
```

### 2. Create a `.env` file (optional)

If you want to override default values:

```bash
cat > .env << EOF
API_KEY=your-secret-key-here
API_URL=http://api:8000
EOF
```

If not provided, defaults are:
- `API_KEY=test-key-123`
- `API_URL=http://api:8000` (inside containers)

### 3. Start the stack

```bash
docker-compose up -d
```

This will:
- Build the `api` and `web` images
- Download and start `ollama/ollama:latest`
- Create a shared network `ats-net` and volumes for persistence

### 4. Verify services are running

```bash
docker-compose ps
```

Expected output:
```
CONTAINER ID   IMAGE          COMMAND                  PORTS               NAMES
...            ats-api        uvicorn backend.api...   0.0.0.0:8000        ats-api
...            ats-web        streamlit run ...        0.0.0.0:8501        ats-web
...            ollama/ollama  ollama serve             0.0.0.0:11434       ats-ollama
```

### 5. Check health

```bash
# API health
curl http://localhost:8000/health

# Web UI (should return HTML)
curl http://localhost:8501/_stcore/health
```

### 6. Access the services

- **Web UI**: http://localhost:8501
- **API Docs**: http://localhost:8000/docs
- **Ollama API**: http://localhost:11434

## First-Time Setup: Pull LLM Model

The first time you start the stack, Ollama needs to download an LLM model. Run:

```bash
# Pull the model used by the system (phi4-mini or your choice)
docker exec ats-ollama ollama pull phi4-mini:latest

# Or pull a smaller/larger model:
# docker exec ats-ollama ollama pull mistral:latest
# docker exec ats-ollama ollama pull llama2:latest
```

**Note**: Model download takes 5–30 minutes depending on your internet speed and model size. You'll see progress in the Ollama container logs:

```bash
docker logs -f ats-ollama
```

## Common Tasks

### View logs

```bash
# All services
docker-compose logs -f

# Just API
docker-compose logs -f api

# Just Streamlit
docker-compose logs -f web

# Just Ollama
docker-compose logs -f ollama
```

### Stop the stack

```bash
docker-compose down
```

This stops and removes containers but **preserves volumes** (data/chroma_db/ollama_models).

### Stop and clean up (including volumes)

```bash
docker-compose down -v
```

**Warning**: This deletes all data, parsed CVs, and downloaded models.

### Restart a service

```bash
docker-compose restart api
docker-compose restart web
docker-compose restart ollama
```

### Rebuild images after code changes

```bash
docker-compose build
docker-compose up -d
```

### Run a one-off command (e.g., debug parsing)

```bash
docker-compose exec api python -c "from ingest_simplified import parse_cv_document; print('OK')"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `test-key-123` | Secret key for API authentication |
| `QUEUE_DB` | `/app/data/jobs.db` | Path to SQLite queue database (inside container) |
| `UPLOAD_DIR` | `/app/data/cv_uploads` | Path to CV uploads directory (inside container) |
| `API_URL` | `http://api:8000` | API URL for Streamlit (inside container) |
| `OLLAMA_HOST` | `0.0.0.0:11434` | Ollama service address |

Set these in `.env` or pass via `-e` flag to `docker-compose`.

## Persistence & Data

All persistent data is stored in volumes:

- **`./data`** → mounted to `/app/data` in API container
  - `jobs.db` (ingestion queue)
  - `cv_uploads/` (uploaded CVs and parsed JSON)
- **`./chroma_db`** → mounted to `/app/chroma_db`
  - Vector embeddings and metadata
- **`./ollama_models`** → mounted to `/root/.ollama` in Ollama container
  - Downloaded LLM models (large!)

To back up your data:

```bash
tar -czf ats_backup_$(date +%Y%m%d).tar.gz data/ chroma_db/ ollama_models/
```

## GPU Support

If you have an NVIDIA GPU and want to use it for faster inference:

1. Install NVIDIA Container Toolkit:
   ```bash
   https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
   ```

2. Uncomment the GPU section in `docker-compose.yml` under `ollama` service:
   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: 1
             capabilities: [gpu]
   ```

3. Restart:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

Verify GPU is being used:

```bash
docker exec ats-ollama nvidia-smi
```

## Troubleshooting

### "Connection refused" to API or Ollama

- Check container is running: `docker-compose ps`
- Check logs: `docker-compose logs api` or `docker-compose logs ollama`
- Wait a few seconds for services to initialize (health checks have a start period of 40s)

### Ollama model not found or very slow

- Verify model is pulled: `docker exec ats-ollama ollama list`
- Pull it if missing: `docker exec ats-ollama ollama pull phi4-mini:latest`
- Check available disk space: `docker exec ats-ollama df -h /root/.ollama`
- Use a smaller model: `docker exec ats-ollama ollama pull orca-mini:latest`

### Out of memory

- Increase Docker memory limit in Docker Desktop settings
- Or use a smaller embedding model (edit `ingest_simplified.py` to use a smaller HuggingFace model)

### Parsed CVs not appearing in vector DB

- Check worker is running and processing jobs:
  - API logs: `docker-compose logs api`
  - Job queue status: `curl http://localhost:8000/stats`
- Run embeddings manually (inside container):
  ```bash
  docker-compose exec api python ingest_simplified.py
  ```

### Streamlit "API connection error"

- Verify API is running and healthy: `curl http://localhost:8000/health`
- Check `API_URL` env var in Streamlit container: should be `http://api:8000`
- Check firewall allows Docker bridge traffic

## Running without Docker (for development)

If you prefer to run services locally:

### 1. Install system dependencies

**macOS (Homebrew):**
```bash
brew install tesseract poppler
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install tesseract-ocr poppler-utils python3.11 python3-pip
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Start Ollama (locally or in Docker)

```bash
# Via Docker (single service)
docker run -it -p 11434:11434 ollama/ollama:latest

# Or install locally: https://ollama.ai
ollama serve
```

### 4. Start the API

```bash
export API_KEY=test-key-123
export QUEUE_DB=./jobs.db
export UPLOAD_DIR=./cv_uploads
export OLLAMA_HOST=http://localhost:11434

python -m uvicorn backend.api:app --host 0.0.0.0 --port 8000
```

### 5. Start the Streamlit UI (in another terminal)

```bash
export API_URL=http://localhost:8000
export API_KEY=test-key-123

streamlit run web/app.py
```

### 6. (Optional) Start a worker in another terminal

```bash
python backend/ingest/worker.py --queue-path ./jobs.db --poll-interval 5
```

## Next Steps

- Upload test CVs via the Web UI at http://localhost:8501
- Parse a job description and rank candidates
- Check API docs at http://localhost:8000/docs
- Review logs and troubleshoot as needed

For more details, see the main `README.md` and individual module documentation in the repo.
