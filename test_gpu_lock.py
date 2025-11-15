#!/usr/bin/env python3
"""
Test script to verify GPU locking works end-to-end.
Parses one CV and runs Phase 2 (embeddings) with GPU lock.
"""

import json
import logging
import os
import sys
from pathlib import Path

# Add workspace to path
sys.path.insert(0, str(Path(__file__).parent))

from llama_index.core import StorageContext
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from backend.ingest.loader import load_documents
from ingest_simplified import parse_cv_document, cleanup_parsed_data, ChunkOffsetProcessor
from backend.parse.normalize import normalize_parsed_cv, load_skills_map
from backend.gpu_lock import acquire_gpu, release_gpu
import chromadb

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_gpu_lock():
    """Test GPU lock with a single CV."""
    logger.info("=== GPU Lock Test: Parse One CV & Run Phase 2 ===")
    
    # Load first CV only
    logger.info("Loading first CV...")
    all_docs = load_documents("./cv_uploads/")
    if not all_docs:
        logger.error("No documents loaded!")
        return False
    
    documents = all_docs[:1]  # Take only first CV
    logger.info(f"Using {len(documents)} document(s)")
    logger.info(f"Note: Existing Chroma DB will be preserved and new embeddings appended")
    
    # Setup output dir
    parsed_out_dir = Path("./cv_uploads/parsed")
    parsed_out_dir.mkdir(parents=True, exist_ok=True)
    
    # --- Phase 1: Parse (without GPU)
    logger.info("--- PHASE 1: Parse CV (LLM, no GPU) ---")
    doc = documents[0]
    file_name = doc.metadata.get('file_name', 'doc_0')
    logger.info(f"Parsing {file_name}...")
    
    try:
        parsed_dict = parse_cv_document(doc.text)
        parsed_dict = cleanup_parsed_data(parsed_dict)
        
        # Normalization
        try:
            skills_map = load_skills_map()
            parsed_dict = normalize_parsed_cv(parsed_dict, skills_map=skills_map)
        except Exception as e:
            logger.debug(f"Normalization failed: {e}")
        
        # Save parsed JSON
        safe_name = Path(file_name).name
        out_path = parsed_out_dir / f"{safe_name}.parsed.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(parsed_dict, f, ensure_ascii=False, indent=2)
        logger.info(f"✓ Saved parsed JSON to {out_path}")
        
    except Exception as e:
        logger.error(f"Phase 1 failed: {e}")
        return False
    
    # --- Phase 2: Embeddings (with GPU lock)
    logger.info("--- PHASE 2: Create Embeddings (with GPU lock) ---")
    
    # Acquire GPU lock
    logger.info("Acquiring GPU lock...")
    got_gpu = acquire_gpu(blocking=True, timeout=60)
    if got_gpu:
        logger.info("✓ GPU lock acquired — enabling GPU for embeddings")
        os.environ.pop("CUDA_VISIBLE_DEVICES", None)
    else:
        logger.warning("! Could not acquire GPU lock — falling back to CPU")
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    
    try:
        # Create embedder
        logger.info("Creating HuggingFaceEmbedding model...")
        embed = HuggingFaceEmbedding(model_name="Qwen/Qwen3-Embedding-0.6B")
        
        # Setup Chroma collections
        db = chromadb.PersistentClient(path="./chroma_db")
        chroma_collection = db.get_or_create_collection("cv_collection")
        resume_collection = db.get_or_create_collection("cv_collection_resumes")
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        # Create resume-level embedding
        logger.info(f"Creating resume-level embedding for {safe_name}...")
        resume_text = doc.text
        resume_emb = embed.get_text_embedding(resume_text)
        logger.info(f"✓ Resume embedding created (dim: {len(resume_emb)})")
        
        # Store resume embedding
        resume_id = safe_name
        resume_metadata = {
            'candidate_name': parsed_dict.get('name'),
            'file_name': safe_name,
        }
        try:
            resume_collection.delete(ids=[resume_id])
        except Exception:
            pass
        
        resume_collection.add(
            ids=[resume_id],
            metadatas=[resume_metadata],
            documents=[parsed_dict.get('professional_summary') or ''],
            embeddings=[resume_emb]
        )
        logger.info(f"✓ Stored resume embedding for {resume_id}")
        
        # Create chunk embeddings via ingestion pipeline
        logger.info("Creating chunk embeddings and ingesting into Chroma...")
        pipeline = IngestionPipeline(
            transformations=[
                SentenceSplitter(chunk_size=2048, chunk_overlap=256),
                ChunkOffsetProcessor(),
                embed,
            ],
            vector_store=vector_store,
        )
        pipeline.run(documents=documents)
        logger.info("✓ Chunk ingestion complete")
        
        # Verify storage
        chunk_count = chroma_collection.count()
        resume_count = resume_collection.count()
        logger.info(f"✓ Stored {chunk_count} chunks in cv_collection")
        logger.info(f"✓ Stored {resume_count} resumes in cv_collection_resumes")
        
        logger.info("=== TEST PASSED ===")
        return True
        
    except Exception as e:
        logger.error(f"Phase 2 failed: {e}", exc_info=True)
        return False
    finally:
        if got_gpu:
            release_gpu()
            logger.info("Released GPU lock")


if __name__ == "__main__":
    success = test_gpu_lock()
    sys.exit(0 if success else 1)
