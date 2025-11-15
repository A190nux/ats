# ATS: AI-Powered CV Search & Ranking System

A self-hostable, open-source system for CV ingestion, parsing, semantic search, and candidate ranking using local LLMs and vector embeddings.

## Features

- **Bulk CV Ingestion** – Drag-and-drop uploads for PDF, DOCX, DOC, TXT, and image-based PDFs (via OCR)
- **Intelligent Parsing** – LLM-powered structured CV parsing with deterministic fallbacks and normalization
- **Vector Embeddings & RAG** – Semantic search and retrieval-augmented generation (RAG) over CVs using local embeddings
- **Job Description Matching** – Parse JDs and rank candidates with configurable scoring rules
- **Chat Interface** – Query CVs in natural language with source citations
- **Export & Integration** – Download ranked shortlists as CSV/JSON
- **Self-Hosted** – All components run locally via Docker Compose (no cloud dependencies)

## Quick Start with Docker

### Prerequisites

- Docker and Docker Compose (v2.0+)
- 10+ GB disk space (for models and vector DB)
- 8+ GB RAM recommended

### 1. Start the stack

```bash
git clone https://github.com/A190nux/ats.git
cd ats

docker-compose up -d
```

This starts:
- **API** (FastAPI) on http://localhost:8000
- **Web UI** (Streamlit) on http://localhost:8501
- **Ollama** (Local LLM) on http://localhost:11434

### 2. Pull the LLM model

```bash
docker exec ats-ollama ollama pull phi4-mini:latest
```

(Takes 5–30 minutes on first run; requires ~4 GB disk)

### 3. Access the Web UI

Open **http://localhost:8501** in your browser to upload CVs and run searches.

### 4. Verify services

```bash
# Check health
curl http://localhost:8000/health

# View API docs
open http://localhost:8000/docs
```

For detailed setup, troubleshooting, and configuration, see [**DOCKER_SETUP.md**](./DOCKER_SETUP.md).

## Architecture

```
┌─────────────────┐
│  Streamlit UI   │ (8501)
│  (web/app.py)   │
└────────┬────────┘
         │
┌────────▼────────────────┐
│   FastAPI Backend       │ (8000)
│   (backend/api.py)      │
│  ┌────────────────────┐ │
│  │ Ingestion Queue    │ │
│  │ (jobs.db)          │ │
│  └────────────────────┘ │
└────────┬────────────────┘
         │
    ┌────┴──────────────────────────┐
    │                               │
┌───▼──────────────┐        ┌──────▼─────────────┐
│  CV Parsing      │        │  Ollama LLM       │
│  + Normalization │        │  (phi4-mini)      │
│  (ingest_*.py)   │        │  (11434)          │
└───┬──────────────┘        └──────┬─────────────┘
    │                              │
    └──────────────┬───────────────┘
                   │
         ┌─────────▼──────────┐
         │  Chroma Vector DB  │
         │  (Embeddings)      │
         └────────────────────┘
```

## Key Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **Ingestion Pipeline** | Load & parse CVs from multiple formats | `backend/ingest/` |
| **Parser & Normalizer** | Extract structured info (name, skills, exp) | `backend/parse/` |
| **Vector Store (Chroma)** | Store and retrieve CV embeddings | `chroma_db/` |
| **RAG Module** | Retrieve & generate answers with citations | `backend/parse/rag.py` |
| **JD Matcher** | Score & rank candidates against JDs | `backend/parse/jd_matcher.py` |
| **API Server** | FastAPI endpoints for all operations | `backend/api.py` |
| **Web UI** | Streamlit interface for users | `web/app.py` |

## API Endpoints

### Upload & Ingestion
- `POST /upload` – Upload single CV
- `POST /upload-bulk` – Upload multiple CVs
- `GET /status/{job_id}` – Check ingestion status
- `GET /stats` – Queue statistics

### Search & RAG
- `POST /rag-chat` – Query CVs in natural language

### Job Description Matching
- `POST /jd/parse` – Parse a job description
- `GET /jd/{jd_id}` – Retrieve parsed JD
- `POST /jd/{jd_id}/rank` – Rank candidates against JD

For full API docs, visit http://localhost:8000/docs (Swagger UI).

## Configuration

### Environment Variables

Create a `.env` file to override defaults:

```bash
cp .env.example .env
```

Key variables:
- `API_KEY` – Secret key for API auth (default: `test-key-123`)
- `QUEUE_DB` – Path to SQLite job queue
- `UPLOAD_DIR` – Directory for uploaded CVs
- `OLLAMA_HOST` – Ollama service URL (default: `0.0.0.0:11434`)

### GPU Support

To enable GPU acceleration for LLM inference:

1. Install NVIDIA Container Toolkit
2. Uncomment GPU section in `docker-compose.yml` under `ollama`
3. Restart: `docker-compose down && docker-compose up -d`

## Local Development

To run without Docker:

```bash
# Install system deps (macOS)
brew install tesseract poppler

# Or Linux (Ubuntu/Debian)
sudo apt-get install tesseract-ocr poppler-utils

# Install Python deps
pip install -r requirements.txt

# Start Ollama (separately)
ollama serve

# Start API (new terminal)
export API_KEY=test-key-123
uvicorn backend.api:app --host 0.0.0.0 --port 8000

# Start Web UI (new terminal)
streamlit run web/app.py
```

## Project Structure

```
ats/
├── backend/
│   ├── api.py                 # FastAPI main server
│   ├── gpu_lock.py            # GPU coordination
│   ├── ingest/                # Document loading & OCR
│   │   ├── loader.py
│   │   ├── ocr.py
│   │   ├── worker.py
│   │   └── job_queue.py
│   └── parse/
│       ├── jd_parser.py       # JD parsing
│       ├── jd_matcher.py      # Scoring & ranking
│       ├── retrieval.py       # Vector DB search
│       ├── rag.py             # RAG generation
│       ├── normalize.py       # Skill normalization
│       └── dedupe.py          # Duplicate removal
├── web/
│   └── app.py                 # Streamlit UI
├── data_schemas/
│   ├── cv.py                  # CV schema
│   └── parse_utils.py         # Parsing helpers
├── ingest.py                  # Main ingestion script
├── ingest_simplified.py       # Simplified ingestion pipeline
├── docker-compose.yml         # Docker services
├── Dockerfile.api             # API image
├── Dockerfile.web             # Web UI image
└── requirements.txt           # Python dependencies
```

## Example Workflow

1. **Upload CVs:**
   - Drag-and-drop in Web UI or use `POST /upload-bulk` API

2. **Wait for parsing:**
   - Monitor progress in Web UI or via `GET /stats`
   - Parsed JSON saved to `data/cv_uploads/parsed/`

3. **Search (RAG):**
   - Type natural language query in Web UI
   - RAG returns matching candidates with source snippets

4. **Rank against JD:**
   - Upload or paste job description
   - System parses JD and ranks all candidates
   - Download shortlist as CSV/JSON

## Troubleshooting

**Services not starting?**
```bash
docker-compose logs -f
```

**Ollama model not found?**
```bash
docker exec ats-ollama ollama list
docker exec ats-ollama ollama pull phi4-mini:latest
```

**Out of memory?**
- Reduce Ollama model size: `ollama pull orca-mini:latest`
- Or increase Docker memory limit

**CVs not appearing in search?**
- Check job status: `curl http://localhost:8000/stats`
- Run embeddings manually: `docker-compose exec api python ingest_simplified.py`

See [**DOCKER_SETUP.md**](./DOCKER_SETUP.md) for detailed troubleshooting.

## Known Limitations

- **No RBAC yet** – Single API key; admin/recruiter roles not enforced
- **Streaming chat** – Responses are buffered, not streamed token-by-token
- **PDF reports** – Export is CSV/JSON only; formatted PDF reports not yet supported
- **Resume offsets** – Citation source offsets are approximate
- **Fuzzy dedupe** – Deduplication uses email/phone only; name similarity not implemented

See the [Issue Tracker](https://github.com/A190nux/ats/issues) for roadmap and feature requests.

## License

MIT

## Contributing

Pull requests welcome! Please:
1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit changes (`git commit -m "Add my feature"`)
4. Push to branch (`git push origin feature/my-feature`)
5. Open a Pull Request

## Support

- **Documentation**: See `DOCKER_SETUP.md` for deployment details
- **Issues**: Report bugs on [GitHub Issues](https://github.com/A190nux/ats/issues)
- **Discussion**: Start a [GitHub Discussion](https://github.com/A190nux/ats/discussions)
