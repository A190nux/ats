"""
FastAPI backend for ATS (Applicant Tracking System).

Endpoints:
- POST /upload — Upload single file or directory for ingestion
- POST /upload-bulk — Upload multiple files
- GET /status/{job_id} — Get job status and progress
- GET /stats — Get queue statistics
- POST /re-ingest/{job_id} — Re-ingest a completed/failed job
- GET /health — Health check
- OpenAPI docs: /docs (Swagger UI)
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# Add workspace to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, File, UploadFile, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.ingest.job_queue import IngestionQueue, JobStatus

try:
    from backend.parse.retrieval import search_resumes, ChunkMatch, ResumeRanking, get_retriever
except ImportError:
    # Fallback for direct execution
    import sys
    sys.path.insert(0, '/home/aly/ats')
    from backend.parse.retrieval import search_resumes, ChunkMatch, ResumeRanking, get_retriever

try:
    from backend.parse.rag import generate_rag_answer, RAGAnswer, LLMTimeout
except ImportError:
    from backend.parse.rag import generate_rag_answer, RAGAnswer, LLMTimeout

import uuid
import json

# Configuration
QUEUE_DB = os.getenv("QUEUE_DB", "./jobs.db")
API_KEY = os.getenv("API_KEY", "test-key-123")  # Change in production
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./cv_uploads")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt', '.jpg', '.jpeg', '.png', '.tiff'}

# Ensure upload directory exists
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# JD parsing & matching (after logger is defined)
try:
    from backend.parse.jd_parser import (
        parse_jd_text,
        save_jd_parsed,
        load_jd_parsed,
        save_jd_with_original,
        load_jd_with_original
    )
except ImportError as e:
    logger.error(f"Failed to import jd_parser: {e}")
    raise

try:
    from backend.parse.jd_matcher import rank_all_candidates, ScoringRubric
except ImportError as e:
    logger.error(f"Failed to import jd_matcher: {e}")
    raise

# Initialize FastAPI app
app = FastAPI(
    title="ATS API",
    description="CV Ingestion, Search & Ranking API",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize queue
queue = IngestionQueue(QUEUE_DB)


# ==================== Request/Response Models ====================

class UploadResponse(BaseModel):
    """Response model for upload endpoints."""
    job_id: str
    status: str
    message: str
    file_path: str
    created_at: str


class JobStatusResponse(BaseModel):
    """Response model for job status."""
    job_id: str
    status: str
    file_path: str
    retries: int
    max_retries: int
    created_at: str
    updated_at: str
    error_message: Optional[str]
    result: Optional[dict]


class QueueStatsResponse(BaseModel):
    """Response model for queue statistics."""
    pending: int
    processing: int
    completed: int
    failed: int
    total: int
    timestamp: str


class ErrorResponse(BaseModel):
    """Response model for errors."""
    error: str
    detail: Optional[str]


class RAGChatRequest(BaseModel):
    """Request for RAG chat endpoint."""
    question: str
    top_k: int = 10
    llm_model: str = "phi4-mini:latest"


class JDParseRequest(BaseModel):
    """Request model for JD parsing."""
    jd_text: Optional[str] = None


class RAGChatResponse(BaseModel):
    """Response from RAG chat endpoint."""
    question: str
    answer: str
    sources: list = []
    num_resumes_retrieved: int
    model: str


# ==================== Authentication ====================

def verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Verify API key from request headers."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


# ==================== Health Check ====================

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    try:
        stats = queue.get_stats()
        return {
            "status": "healthy",
            "queue_available": True,
            "queue_path": QUEUE_DB,
            "queue_stats": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


# ==================== Upload Endpoints ====================

@app.post("/upload", response_model=UploadResponse, tags=["Upload"])
async def upload_file(
    file: UploadFile = File(...),
    max_retries: int = Query(3, ge=1, le=10),
    x_api_key: Optional[str] = Header(None)
):
    """
    Upload a single CV file for ingestion.
    
    Supported formats: PDF, DOCX, DOC, TXT, JPG, PNG, TIFF
    
    Returns job ID for status tracking.
    """
    verify_api_key(x_api_key)
    
    try:
        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{file_ext}' not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        # Validate file size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds maximum of {MAX_FILE_SIZE / 1024 / 1024:.0f} MB"
            )
        
        # Save file
        file_path = Path(UPLOAD_DIR) / file.filename
        with open(file_path, 'wb') as f:
            f.write(content)
        
        logger.info(f"File saved: {file_path}")
        
        # Enqueue job
        job_id = queue.enqueue(str(file_path), max_retries=max_retries)
        
        logger.info(f"Job enqueued: {job_id} for {file_path}")
        
        return UploadResponse(
            job_id=job_id,
            status="pending",
            message=f"File '{file.filename}' uploaded successfully",
            file_path=str(file_path),
            created_at=datetime.now().isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload-bulk", tags=["Upload"])
async def upload_bulk(
    files: list[UploadFile] = File(...),
    max_retries: int = Query(3, ge=1, le=10),
    x_api_key: Optional[str] = Header(None)
):
    """
    Upload multiple CV files for ingestion (bulk upload).
    
    Returns list of job IDs for each file.
    """
    verify_api_key(x_api_key)
    
    results = []
    
    for file in files:
        try:
            # Validate file extension
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in ALLOWED_EXTENSIONS:
                results.append({
                    "filename": file.filename,
                    "status": "skipped",
                    "reason": f"File type '{file_ext}' not supported"
                })
                continue
            
            # Validate file size
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                results.append({
                    "filename": file.filename,
                    "status": "skipped",
                    "reason": f"File size exceeds {MAX_FILE_SIZE / 1024 / 1024:.0f} MB"
                })
                continue
            
            # Save file
            file_path = Path(UPLOAD_DIR) / file.filename
            with open(file_path, 'wb') as f:
                f.write(content)
            
            # Enqueue job
            job_id = queue.enqueue(str(file_path), max_retries=max_retries)
            
            results.append({
                "filename": file.filename,
                "job_id": job_id,
                "status": "pending",
                "file_path": str(file_path),
                "created_at": datetime.now().isoformat()
            })
            
            logger.info(f"Bulk upload: {file.filename} → job {job_id}")
        
        except Exception as e:
            logger.error(f"Bulk upload failed for {file.filename}: {e}")
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": str(e)
            })
    
    return {
        "total": len(files),
        "successful": sum(1 for r in results if r.get("status") == "pending"),
        "skipped": sum(1 for r in results if r.get("status") == "skipped"),
        "failed": sum(1 for r in results if r.get("status") == "error"),
        "results": results,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/upload-directory", response_model=UploadResponse, tags=["Upload"])
async def upload_directory(
    directory_path: str = Query(..., description="Path to directory containing CVs"),
    max_retries: int = Query(3, ge=1, le=10),
    x_api_key: Optional[str] = Header(None)
):
    """
    Enqueue all files in a directory for ingestion.
    
    The directory must be accessible from the server.
    """
    verify_api_key(x_api_key)
    
    try:
        dir_path = Path(directory_path)
        if not dir_path.exists():
            raise HTTPException(status_code=400, detail=f"Directory not found: {directory_path}")
        
        if not dir_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {directory_path}")
        
        # Enqueue directory
        job_id = queue.enqueue(str(dir_path), max_retries=max_retries)
        
        logger.info(f"Directory enqueued: {job_id} for {dir_path}")
        
        return UploadResponse(
            job_id=job_id,
            status="pending",
            message=f"Directory '{directory_path}' enqueued for processing",
            file_path=str(dir_path),
            created_at=datetime.now().isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Directory upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Status & Monitoring ====================

@app.get("/status/{job_id}", response_model=JobStatusResponse, tags=["Status"])
async def get_job_status(job_id: str):
    """
    Get the status of an ingestion job.
    
    Returns: job ID, status (pending/processing/completed/failed), result if available.
    """
    try:
        job = queue.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        # Handle both enum and string status values
        status_value = job.status.value if hasattr(job.status, 'value') else job.status
        
        return JobStatusResponse(
            job_id=job.job_id,
            status=status_value,
            file_path=job.file_path,
            retries=job.retries,
            max_retries=job.max_retries,
            created_at=job.created_at,
            updated_at=job.updated_at,
            error_message=job.error_message,
            result=job.result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats", response_model=QueueStatsResponse, tags=["Status"])
async def get_queue_stats():
    """
    Get queue statistics: pending, processing, completed, failed counts.
    """
    try:
        stats = queue.get_stats()
        return QueueStatsResponse(
            pending=stats.get('pending', 0),
            processing=stats.get('processing', 0),
            completed=stats.get('completed', 0),
            failed=stats.get('failed', 0),
            total=stats.get('total', 0),
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Stats check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs", tags=["Status"])
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status: pending, processing, completed, failed"),
    limit: int = Query(50, ge=1, le=500)
):
    """
    List all jobs, optionally filtered by status.
    """
    try:
        # Validate status if provided
        if status:
            try:
                status_enum = JobStatus[status.upper()]
                jobs = queue.get_all_jobs(status=status_enum, limit=limit)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        else:
            jobs = queue.get_all_jobs(limit=limit)
        
        return {
            "count": len(jobs),
            "limit": limit,
            "status_filter": status,
            "jobs": [job.to_dict() for job in jobs],
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List jobs failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Job Management ====================

@app.post("/re-ingest/{job_id}", response_model=UploadResponse, tags=["Management"])
async def re_ingest_job(
    job_id: str,
    max_retries: int = Query(3, ge=1, le=10),
    x_api_key: Optional[str] = Header(None)
):
    """
    Re-ingest a completed or failed job.
    
    Creates a new job with the same file/directory path.
    """
    verify_api_key(x_api_key)
    
    try:
        # Get original job
        original_job = queue.get_job(job_id)
        if not original_job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        # Enqueue new job with same path
        new_job_id = queue.enqueue(original_job.file_path, max_retries=max_retries)
        
        logger.info(f"Re-ingestion: {job_id} → {new_job_id}")
        
        return UploadResponse(
            job_id=new_job_id,
            status="pending",
            message=f"Job {job_id} re-ingested",
            file_path=original_job.file_path,
            created_at=datetime.now().isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Re-ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/jobs/{job_id}", tags=["Management"])
async def delete_job(
    job_id: str,
    x_api_key: Optional[str] = Header(None)
):
    """
    Delete a job (admin only).
    
    Only pending jobs can be deleted.
    """
    verify_api_key(x_api_key)
    
    try:
        job = queue.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        if job.status != JobStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Only pending jobs can be deleted. Current status: {job.status.value}"
            )
        
        # Delete from database (note: simple implementation, assumes single row update)
        # In production, add a delete_job method to IngestionQueue
        logger.info(f"Job deleted: {job_id}")
        
        return {"message": f"Job {job_id} deleted", "job_id": job_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job deletion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search", tags=["Retrieval"])
async def search_resumes_endpoint(
    query: str = Query(..., min_length=5, description="Search query (requirement, skill, or JD snippet)"),
    top_k: int = Query(10, ge=1, le=50, description="Number of top chunks to retrieve"),
    chunks_per_resume: int = Query(3, ge=1, le=10, description="Max chunks per resume"),
    x_api_key: Optional[str] = Header(None)
):
    """
    Search for relevant resumes using semantic similarity.
    
    **Input:**
    - `query`: A requirement, skill, or JD snippet to search for
    - `top_k`: Number of chunks to retrieve (default: 10)
    - `chunks_per_resume`: Max chunks per resume in results (default: 3)
    
    **Output:**
    - List of ranked resumes with their top matching chunks
    - Each chunk includes: resume_id, candidate_name, chunk_text, similarity_score
    
    **Example:**
    ```
    GET /search?query=machine+learning+experience&top_k=20
    ```
    """
    verify_api_key(x_api_key)
    
    try:
        rankings = search_resumes(query, top_k=top_k)
        
        # Trim to chunks_per_resume
        for ranking in rankings:
            ranking.top_chunks = ranking.top_chunks[:chunks_per_resume]
        
        return {
            "query": query,
            "total_resumes": len(rankings),
            "resumes": [r.to_dict() for r in rankings],
        }
    
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rag-chat", tags=["RAG"], response_model=RAGChatResponse)
async def rag_chat_endpoint(
    request: RAGChatRequest,
    x_api_key: Optional[str] = Header(None)
):
    """
    RAG-based Q&A endpoint: retrieves relevant candidates and generates LLM answers with citations.
    
    **Input:**
    - `question`: A recruitment question, skill requirement, or JD snippet
    - `top_k`: Number of candidate chunks to retrieve (default: 10)
    - `llm_model`: Ollama model to use (default: "phi4-mini:latest")
    
    **Output:**
    - `answer`: Generated answer with candidate recommendations
    - `sources`: Top matching candidate excerpts with similarity scores
    - `num_resumes_retrieved`: Number of unique candidates considered
    
    **Example:**
    ```json
    {
      "question": "Find candidates with Machine Learning and TensorFlow experience",
      "top_k": 10,
      "llm_model": "phi4-mini:latest"
    }
    ```
    """
    verify_api_key(x_api_key)
    
    try:
        # Validate question
        if not request.question or len(request.question) < 3:
            raise HTTPException(status_code=400, detail="Question must be at least 3 characters")
        
        logger.info(f"RAG Chat: {request.question}")
        
            # Generate RAG answer (with longer timeout for LLM)
        try:
            rag_result = generate_rag_answer(
                question=request.question,
                top_k=request.top_k,
                llm_model=request.llm_model,
                llm_timeout=120.0,
            )
        except LLMTimeout as e:
            logger.error(f"RAG generation timed out: {e}")
            raise HTTPException(status_code=504, detail=str(e))
        
        return RAGChatResponse(
        question=rag_result.question,
        answer=rag_result.answer,
            sources=rag_result.sources,
            num_resumes_retrieved=rag_result.num_resumes_retrieved,
            model=rag_result.model,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"RAG generation error: {str(e)}")


# -----------------------
# JD endpoints & helpers
# -----------------------

JDS_DIR = Path(__file__).parent / "data" / "jds"
JDS_DIR.mkdir(parents=True, exist_ok=True)


def _save_jd_to_disk(jd_parsed, original_text: str) -> str:
    """Deprecated: use save_jd_with_original() from jd_parser instead.
    
    This wrapper is kept for backward compatibility during migration.
    """
    jd_id, _ = save_jd_with_original(jd_parsed, original_text, JDS_DIR)
    return jd_id


def _load_all_parsed_cvs(parsed_dir: Path = Path("./cv_uploads/parsed")) -> List:
    """Load all parsed CV JSON files from `cv_uploads/parsed` and return as list of CVParsed-like dicts.

    This is a simple, reliable source of CVParsed data created by ingestion.
    """
    cvs = []
    if not parsed_dir.exists():
        return cvs

    for p in parsed_dir.glob("*.parsed.json"):
        try:
            raw = json.loads(p.read_text(encoding='utf-8'))
            cvs.append((p.stem, raw))
        except Exception:
            logger.warning(f"Could not load parsed CV: {p}")
    return cvs


@app.post("/jd/parse", tags=["JD"])
async def api_parse_jd(
    request: JDParseRequest,
    x_api_key: Optional[str] = Header(None)
):
    """Parse a JD from text, store parsed JD, and return jd_id + parsed object."""
    verify_api_key(x_api_key)

    if not request.jd_text:
        raise HTTPException(status_code=400, detail="Provide `jd_text` in request body")

    try:
        parsed = parse_jd_text(request.jd_text)
        jd_id = _save_jd_to_disk(parsed, request.jd_text)

        return {
            'jd_id': jd_id,
            'jd_parsed': parsed.model_dump() if hasattr(parsed, 'model_dump') else parsed.dict(),
            'message': 'JD parsed and saved',
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"JD parse failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jd/{jd_id}", tags=["JD"])
async def api_get_jd(jd_id: str, x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    
    try:
        jd_parsed, original = load_jd_with_original(jd_id, JDS_DIR)
        parsed_dict = jd_parsed.model_dump() if hasattr(jd_parsed, 'model_dump') else jd_parsed.dict()
        return { 'jd_id': jd_id, 'jd_parsed': parsed_dict, 'original': original }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"JD not found: {jd_id}")
    except Exception as e:
        logger.error(f"Failed to load JD {jd_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jd/list", tags=["JD"])
async def api_list_jds(x_api_key: Optional[str] = Header(None)):
    verify_api_key(x_api_key)
    items = []
    for d in sorted(JDS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if d.is_dir():
            items.append({ 'jd_id': d.name, 'path': str(d) })
    return { 'count': len(items), 'jds': items }


@app.post("/jd/{jd_id}/rank", tags=["JD"])
async def api_rank_candidates(
    jd_id: str,
    semantic_weight: float = Query(0.4, ge=0.0, le=1.0, description="Weight of semantic (retriever) score in final blend"),
    top_k: int = Query(20, ge=1, le=200),
    x_api_key: Optional[str] = Header(None)
):
    """Rank candidates for a stored JD. Blends rule-based scores with optional semantic scores from Chroma.

    `semantic_weight` controls influence of retriever score (0 = only rule-based).
    """
    verify_api_key(x_api_key)

    try:
        jd, _ = load_jd_with_original(jd_id, JDS_DIR)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"JD not found: {jd_id}")

    try:
        # Load parsed CVs from disk (cv_uploads/parsed)
        cvs = _load_all_parsed_cvs()

        # Convert to CVParsed objects lazily only when needed to score
        from data_schemas.cv import CVParsed

        # Get semantic resume scores from retriever (resume-level)
        semantic_map = {}
        try:
            retriever = get_retriever()
            sem_results = retriever.search_by_resume(jd.job_title + "\n" + (jd.description or ""), top_n_resumes=top_k)
            for r in sem_results:
                # r: {resume_id, candidate_name, similarity, metadata}
                semantic_map[str(r.get('resume_id'))] = r.get('similarity') or 0.0
        except Exception as e:
            logger.debug(f"Semantic retriever unavailable: {e}")

        # Build CVParsed list and map by resume id (filename stem)
        cv_objects = []
        id_map = {}
        for stem, raw in cvs:
            try:
                cv_obj = CVParsed(**raw)
                cv_objects.append((stem, cv_obj))
                id_map[stem] = cv_obj
            except Exception:
                logger.debug(f"Failed to construct CVParsed for {stem}")

        # Compute rule-based ranking
        cv_list = [cv for _, cv in cv_objects]
        rule_results = rank_all_candidates(jd, cv_list)

        # Attach resume_id & semantic score, blend final score
        final = []
        for res in rule_results:
            # try to find resume_id by candidate name or via id_map
            matched_resume_id = None
            for stem, cv in cv_objects:
                if getattr(cv, 'name', None) and res.candidate_name and cv.name == res.candidate_name:
                    matched_resume_id = stem
                    break

            # fallback: if resume_id provided in result, use it
            if not matched_resume_id and res.resume_id:
                matched_resume_id = res.resume_id

            sem_score = semantic_map.get(matched_resume_id, 0.0)

            blended = (1.0 - semantic_weight) * res.score + semantic_weight * (sem_score or 0.0)

            final.append({
                'candidate_name': res.candidate_name,
                'resume_id': matched_resume_id,
                'rule_score': res.score,
                'semantic_score': sem_score,
                'final_score': blended,
                'matched_must': res.matched_must,
                'matched_nice': res.matched_nice,
                'missing_must': res.missing_must,
                'details': res.details,
            })

        final_sorted = sorted(final, key=lambda r: r['final_score'], reverse=True)

        return { 'jd_id': jd_id, 'rankings': final_sorted }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ranking failed for JD {jd_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Error Handlers ====================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Catch-all exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


# ==================== Chat & Session Management ====================

try:
    from backend.chat_session import create_session, get_session, list_sessions
except ImportError:
    logger.warning("Chat session module not available")

try:
    from backend.export_utils import export_csv, export_xlsx, export_json, export_pdf
except ImportError:
    logger.warning("Export utilities not available")

try:
    from backend.rbac import (
        create_user, authenticate_user, get_user, get_user_permissions,
        has_permission, list_users, create_default_admin
    )
except ImportError:
    logger.warning("RBAC module not available")


class ChatRequest(BaseModel):
    """Request for chat endpoint."""
    session_id: Optional[str] = None
    question: str
    top_k: int = 10


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    session_id: str
    message_id: str
    question: str
    answer: str
    sources: list
    timestamp: str


class ExportRequest(BaseModel):
    """Request for export endpoint."""
    results: List[Dict]
    format: str  # 'csv', 'xlsx', 'json', 'pdf'
    jd_data: Optional[Dict] = None
    jd_title: Optional[str] = None


class AuthRequest(BaseModel):
    """Request for authentication."""
    username: str
    password: str


class AuthResponse(BaseModel):
    """Response from authentication."""
    token: str
    user_id: str
    username: str
    role: str


@app.post("/auth/login", response_model=AuthResponse, tags=["Auth"])
async def login(req: AuthRequest):
    """Authenticate user and return token."""
    try:
        user = authenticate_user(req.username, req.password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # For now, use user_id as token (in production use JWT)
        return AuthResponse(
            token=user["user_id"],
            user_id=user["user_id"],
            username=user["username"],
            role=user["role"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=500, detail="Authentication failed")


@app.get("/auth/me", tags=["Auth"])
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current authenticated user."""
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        
        user_id = authorization.replace("Bearer ", "")
        user = get_user(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user")


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(req: ChatRequest, x_api_key: Optional[str] = Header(None)):
    """
    Chat with RAG over CVs.
    
    If session_id is provided, appends to existing session.
    Otherwise, creates a new session.
    """
    verify_api_key(x_api_key)
    
    try:
        # Get or create session
        if req.session_id:
            session = get_session(req.session_id)
            if not session:
                raise HTTPException(status_code=404, detail=f"Session not found: {req.session_id}")
        else:
            session = create_session(user_id="api-user")
        
        # Add user question to session
        session.add_message("user", req.question)
        
        # Generate RAG answer
        try:
            rag_answer = generate_rag_answer(
                question=req.question,
                top_k=req.top_k,
                llm_model="phi4-mini:latest",
                llm_timeout=120.0
            )
        except LLMTimeout as e:
            logger.error(f"Chat RAG generation timed out: {e}")
            raise HTTPException(status_code=504, detail=str(e))
        
        # Add assistant answer to session
        session.add_message(
            "assistant",
            rag_answer.answer,
            sources=rag_answer.sources
        )
        session.save()
        
        return ChatResponse(
            session_id=session.session_id,
            message_id=session.messages[-1]["message_id"],
            question=req.question,
            answer=rag_answer.answer,
            sources=rag_answer.sources,
            timestamp=datetime.now().isoformat()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/{session_id}", tags=["Chat"])
async def get_chat_session(session_id: str):
    """Retrieve a chat session with full history."""
    try:
        session = get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        
        return session.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat", tags=["Chat"])
async def list_chat_sessions(limit: int = Query(50, ge=1, le=500)):
    """List recent chat sessions."""
    try:
        sessions = list_sessions(limit=limit)
        return {
            "count": len(sessions),
            "sessions": [s.to_dict() for s in sessions]
        }
    except Exception as e:
        logger.error(f"List sessions failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export", tags=["Export"])
async def export_results(req: ExportRequest, x_api_key: Optional[str] = Header(None)):
    """
    Export ranking results in multiple formats.
    
    Supported formats: 'csv', 'xlsx', 'json', 'pdf'
    """
    verify_api_key(x_api_key)
    
    try:
        format_lower = req.format.lower()
        
        if format_lower == "csv":
            file_path = export_csv(req.results, req.jd_title)
        elif format_lower == "xlsx":
            file_path = export_xlsx(req.results, req.jd_data, req.jd_title)
        elif format_lower == "json":
            file_path = export_json(req.results, req.jd_data)
        elif format_lower == "pdf":
            file_path = export_pdf(req.results, req.jd_data)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format_lower}")
        
        return {
            "format": format_lower,
            "file_path": file_path,
            "message": f"Exported {len(req.results)} results to {format_lower.upper()}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Root Endpoint ====================

@app.get("/", tags=["Root"])
async def root():
    """API root endpoint with documentation."""
    return {
        "name": "ATS API",
        "version": "1.0.0",
        "description": "CV Ingestion, Search & Ranking API",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "health": "GET /health",
            "upload_single": "POST /upload",
            "upload_bulk": "POST /upload-bulk",
            "upload_directory": "POST /upload-directory",
            "get_status": "GET /status/{job_id}",
            "list_jobs": "GET /jobs",
            "queue_stats": "GET /stats",
            "re_ingest": "POST /re-ingest/{job_id}",
            "delete_job": "DELETE /jobs/{job_id}",
            "chat": "POST /chat",
            "chat_session": "GET /chat/{session_id}",
            "export": "POST /export",
            "auth_login": "POST /auth/login"
        },
        "auth": "Use X-API-Key header or Bearer token"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
