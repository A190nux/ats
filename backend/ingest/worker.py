"""
Worker process for ingestion jobs.

Polls the queue for pending jobs, processes them, and updates status.
Handles retries and error tracking.

Usage:
    python worker.py  # Run indefinitely
    python worker.py --one-time  # Process one job and exit
"""

import logging
import sys
import time
import argparse as arg_parser
import traceback
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import queue first to avoid import conflicts with stdlib
from backend.ingest.job_queue import IngestionQueue, JobStatus
from backend.parse.dedupe import run_dedupe

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./ingestion_worker.log'),
        logging.StreamHandler(),
    ]
)


def process_job(queue: IngestionQueue, job_id: str, enable_ocr: bool = True) -> tuple[bool, list]:
    """Process a single ingestion job.
    
    Args:
        queue: IngestionQueue instance.
        job_id: Job ID.
        enable_ocr: Enable OCR for scanned PDFs.
    
    Returns:
        Tuple of (success: bool, newly_created_parsed_files: list[str])
    """
    # Import here to avoid circular imports
    from backend.ingest.loader import load_documents
    # Import internal helpers to support single-file loading without scanning the whole directory
    try:
        from backend.ingest.loader import _load_pdf, _load_docx, _load_doc, _load_txt, _load_image
        from llama_index.core import Document as LlamaDocument
        HAS_DIRECT_LOADERS = True
    except Exception:
        HAS_DIRECT_LOADERS = False
    
    job = queue.get_job(job_id)
    if not job:
        logger.error(f"Job {job_id} not found")
        return False, []
    
    try:
        logger.info(f"Processing job {job_id}: {job.file_path}")
        queue.mark_processing(job_id)
        
        # Track newly created parsed files for dedupe
        parsed_out_dir = Path("./cv_uploads/parsed")
        newly_created = []
        
        # Check if it's a directory or file
        path = Path(job.file_path)
        
        if path.is_dir():
            # Load documents from directory
            docs = load_documents(str(path), enable_ocr=enable_ocr)
        elif path.is_file():
            # Prefer loading single file directly to avoid scanning the whole upload directory
            docs = []
            if HAS_DIRECT_LOADERS:
                file_ext = path.suffix.lower()
                text = None
                if file_ext == '.pdf':
                    text = _load_pdf(str(path), enable_ocr=enable_ocr)
                elif file_ext == '.docx':
                    text = _load_docx(str(path))
                elif file_ext == '.doc':
                    text = _load_doc(str(path))
                elif file_ext == '.txt':
                    text = _load_txt(str(path))
                elif file_ext in ('.jpg', '.jpeg', '.png', '.tiff'):
                    text = _load_image(str(path)) if enable_ocr else None

                if text:
                    # Build a minimal Llama Document equivalent to loader output
                    try:
                        doc = LlamaDocument(
                            text=text,
                            metadata={
                                'file_name': path.name,
                                'source': str(path),
                                'file_type': file_ext.lstrip('.')
                            }
                        )
                        docs.append(doc)
                    except Exception:
                        # Fallback: keep as simple dict-like holder
                        class _SimpleDoc:
                            def __init__(self, text, name, src, ftype):
                                self.text = text
                                self.metadata = {'file_name': name, 'source': src, 'file_type': ftype}
                        docs.append(_SimpleDoc(text, path.name, str(path), file_ext.lstrip('.')))
            else:
                # Fallback: load parent directory and filter
                docs = load_documents(str(path.parent), supported_formats=[path.suffix.lower()], enable_ocr=enable_ocr)
                docs = [d for d in docs if d.metadata.get('file_name') == path.name]
        else:
            raise FileNotFoundError(f"Path does not exist: {job.file_path}")
        
        # Ensure parsed output directory exists
        parsed_out_dir.mkdir(parents=True, exist_ok=True)
        
        # Parse each document and save JSON
        parsed_count = 0
        for idx, doc in enumerate(docs):
            try:
                # Extract text content (llama_index Document uses .text)
                doc_text = getattr(doc, 'text', '')

                # Try to parse with project's parser (LLM + fallbacks)
                parsed_dict = try_parse_with_llm(doc_text)
                
                # Save parsed JSON
                source_name = doc.metadata.get('file_name') or doc.metadata.get('source') or f"doc_{idx}"
                safe_name = Path(source_name).name
                out_path = parsed_out_dir / f"{safe_name}.parsed.json"
                
                with open(out_path, 'w', encoding='utf-8') as f:
                    json.dump(parsed_dict, f, ensure_ascii=False, indent=2)
                
                parsed_count += 1
                newly_created.append(str(out_path))
                logger.info(f"  ✓ Parsed and saved: {safe_name}")
                
            except Exception as e:
                logger.warning(f"Failed to parse {doc.metadata.get('file_name', 'unknown')}: {e}")
        
        result = {
            "documents_loaded": len(docs),
            "documents_parsed": parsed_count,
            "type": "directory" if path.is_dir() else "file",
        }
        logger.info(f"Loaded {len(docs)} documents, parsed {parsed_count}")
        
        # Mark as completed
        queue.mark_completed(job_id, result)
        return True, newly_created
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Job {job_id} failed: {error_msg}\n{traceback.format_exc()}")
        queue.mark_failed(job_id, error_msg)
        return False, []


def try_parse_with_llm(doc_text: str) -> dict:
    """Try to parse CV with the project's parsing pipeline.

    Prefer the structured parser in `ingest_simplified.parse_cv_document` and
    post-process with `cleanup_parsed_data`. Falls back to a lightweight
    deterministic cleanup if the structured LLM is unavailable.
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from ingest_simplified import parse_cv_document, cleanup_parsed_data

        parsed = parse_cv_document(doc_text)
        parsed = cleanup_parsed_data(parsed)
        # Attempt normalization if available
        try:
            from ingest_simplified import cleanup_parsed_data as _cleanup  # noqa: F401
            from backend.parse.normalize import normalize_parsed_cv, load_skills_map
            skills_map = load_skills_map()
            parsed = normalize_parsed_cv(parsed, skills_map=skills_map)
        except Exception:
            # Normalization is best-effort; continue without failing
            pass
        return parsed or {}
    except Exception as e:
        logger.debug(f"Structured parser unavailable or failed: {e}")
        try:
            from ingest_simplified import cleanup_parsed_data
            parsed = cleanup_parsed_data({
                "name": None,
                "contact": {},
                "professional_summary": doc_text[:500] if doc_text else None,
                "skills": [],
                "education": [],
                "experience": [],
            })
            return parsed
        except Exception:
            return {
                "name": None,
                "contact": {},
                "professional_summary": doc_text[:500] if doc_text else None,
            }


def run_worker(queue_path: str = "./jobs.db", enable_ocr: bool = True, poll_interval: int = 5, one_time: bool = False):
    """Run the worker process.
    
    Args:
        queue_path: Path to SQLite queue database.
        enable_ocr: Enable OCR for scanned PDFs.
        poll_interval: Seconds between queue polls.
        one_time: If True, process one job and exit.
    """
    queue = IngestionQueue(queue_path)
    logger.info(f"Worker started (OCR: {enable_ocr}, poll_interval: {poll_interval}s)")
    parsed_dir = Path("./cv_uploads/parsed")
    
    try:
        while True:
            job = queue.get_pending_job()
            
            if job:
                logger.info(f"Found pending job: {job.job_id}")
                success, newly_created = process_job(queue, job.job_id, enable_ocr=enable_ocr)
                
                # Run dedupe after each successful job
                if success and newly_created:
                    try:
                        logger.info(f"Running dedupe on {len(newly_created)} newly created files...")
                        dedupe_result = run_dedupe(parsed_dir)
                        logger.info(f"Dedupe complete: kept={len(dedupe_result.get('kept', []))}, removed={len(dedupe_result.get('removed', []))}")
                    except Exception as e:
                        logger.warning(f"Dedupe failed (non-fatal): {e}")
                
                if one_time:
                    logger.info("One-time mode: processed one job, exiting")
                    break
            else:
                if one_time:
                    logger.info("One-time mode: no pending jobs, exiting")
                    break
                
                logger.debug(f"No pending jobs, waiting {poll_interval}s...")
                time.sleep(poll_interval)
    
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker error: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    parser = arg_parser.ArgumentParser(description="Ingestion worker process")
    parser.add_argument("--queue-path", default="./jobs.db", help="Path to queue database")
    parser.add_argument("--disable-ocr", action="store_true", help="Disable OCR for scanned PDFs")
    parser.add_argument("--poll-interval", type=int, default=5, help="Seconds between queue polls")
    parser.add_argument("--one-time", action="store_true", help="Process one job and exit")
    
    args = parser.parse_args()
    
    run_worker(
        queue_path=args.queue_path,
        enable_ocr=not args.disable_ocr,
        poll_interval=args.poll_interval,
        one_time=args.one_time,
    )
