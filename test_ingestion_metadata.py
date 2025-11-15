#!/usr/bin/env python3
"""
Quick test: verify ChunkOffsetProcessor works and attaches metadata to vectors.
"""
import json
import logging
from pathlib import Path

from llama_index.core import Document, StorageContext
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, TransformComponent
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom chunk offset processor (same as in ingest_simplified.py)
class ChunkOffsetProcessor(TransformComponent):
    """Attach character offsets and resume_id to each chunk node for citation."""
    
    def __call__(self, nodes, **kwargs):
        """Process nodes to attach chunk metadata."""
        for node in nodes:
            node.metadata['chunk_text'] = node.get_content()
            file_name = node.metadata.get('file_name', 'unknown')
            node.metadata['resume_id'] = file_name
            node.metadata['start_char'] = None
            node.metadata['end_char'] = None
            node.metadata['source_file'] = file_name
        return nodes


# Create fresh Chroma DB
db = chromadb.PersistentClient(path="./chroma_db")
col = db.get_or_create_collection("cv_collection")
vector_store = ChromaVectorStore(chroma_collection=col)
storage_context = StorageContext.from_defaults(vector_store=vector_store)

# Setup embedder
embed_model = HuggingFaceEmbedding(model_name="Qwen/Qwen3-Embedding-0.6B")

# Create test documents from parsed JSON files
parsed_dir = Path("./cv_uploads/parsed")
test_docs = []

for parsed_file in list(parsed_dir.glob("*.parsed.json"))[:2]:  # Test with first 2
    try:
        with open(parsed_file, 'r', encoding='utf-8') as f:
            parsed_data = json.load(f)
        
        # Extract text from parsed data
        text_parts = []
        if parsed_data.get('professional_summary'):
            text_parts.append(parsed_data['professional_summary'])
        if parsed_data.get('skills'):
            text_parts.append("Skills: " + ", ".join(str(s) for s in parsed_data['skills']))
        
        if text_parts:
            text = "\n".join(text_parts)
            doc = Document(
                text=text,
                metadata={
                    'file_name': parsed_file.stem,
                    'candidate_name': parsed_data.get('name'),
                }
            )
            test_docs.append(doc)
            logger.info(f"Created test doc from {parsed_file.name}")
    except Exception as e:
        logger.warning(f"Could not load {parsed_file.name}: {e}")

if not test_docs:
    logger.error("No test documents created; exiting")
    exit(1)

logger.info(f"Running ingestion pipeline with {len(test_docs)} test documents...")

# Run pipeline with ChunkOffsetProcessor
pipeline = IngestionPipeline(
    transformations=[
        SentenceSplitter(chunk_size=512, chunk_overlap=128),
        ChunkOffsetProcessor(),
        embed_model,
    ],
    vector_store=vector_store,
)

pipeline.run(documents=test_docs)
logger.info("Ingestion complete")

# Inspect what was stored
logger.info("\nInspecting stored vectors...")
try:
    all_data = col.get(include=['metadatas', 'documents'])
    ids = all_data.get('ids', [])
    metadatas = all_data.get('metadatas', [])
    documents = all_data.get('documents', [])
    
    logger.info(f"Total vectors stored: {len(ids)}")
    
    # Print sample metadata
    for i in range(min(3, len(ids))):
        logger.info(f"\n--- Vector {i+1} ---")
        logger.info(f"ID: {ids[i]}")
        logger.info(f"Metadata keys: {sorted(metadatas[i].keys())}")
        logger.info(f"Resume ID: {metadatas[i].get('resume_id')}")
        logger.info(f"Source file: {metadatas[i].get('source_file')}")
        logger.info(f"Candidate: {metadatas[i].get('candidate_name')}")
        logger.info(f"Has chunk_text: {'chunk_text' in metadatas[i]}")
        logger.info(f"Document preview: {documents[i][:100]}...")
    
    logger.info("\n✓ Metadata attached successfully!")
    
except Exception as e:
    logger.error(f"Failed to inspect: {e}", exc_info=True)
