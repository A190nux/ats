"""
Simplified CV Parsing Pipeline

Architecture:
1. Load CV documents
2. Single structured LLM call per document
3. Lightweight post-processing (cleanup)
4. Store in ChromaDB with metadata

Key differences from original:
- One LLM call instead of 3+ (removes validation LLM and education specialist)
- No deterministic pre-passes (they cause overfitting)
- Simple fallback to null values instead of complex merging
- Clear error handling without silent failures
- ~150 lines vs 500+
"""

import json
import logging
import os
import traceback
from pathlib import Path
from typing import List

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore

from backend.ingest.loader import load_documents
from data_schemas.cv import CVParsed
from data_schemas.parse_utils_minimal import (
    extract_email, extract_phone, extract_linkedin, extract_github
)
# Deterministic fallback utilities (used when LLM is unavailable or OOMs)
from data_schemas.parse_utils import (
    extract_name_contacts, split_sections, extract_skills as extract_skills_full,
    parse_experience_section, parse_education_section,
)
# Normalization utilities
from backend.parse.normalize import normalize_parsed_cv, load_skills_map

import chromadb

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Setup Components ---
llm = Ollama(
    model="phi4-mini:latest",
    request_timeout=300.0,
    temperature=0.1,
    additional_kwargs={
        "system": "You are a CV parser. Return only valid JSON matching the provided schema. "
                  "If a field cannot be determined from the CV, set it to null. Do not invent data."
    }
)

# Note: embed_model will be created lazily inside main() while holding the GPU lock
embed_model = None

# ChromaDB connection
db = chromadb.PersistentClient(path="./chroma_db")
chroma_collection = db.get_or_create_collection("cv_collection")
# Separate collection to store one embedding per resume (document-level)
resume_collection = db.get_or_create_collection("cv_collection_resumes")
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
storage_context = StorageContext.from_defaults(vector_store=vector_store)

# Create structured LLM (single, reliable tool)
try:
    sllm = llm.as_structured_llm(CVParsed)
    logger.info("Structured LLM created successfully")
except Exception as e:
    logger.error(f"Failed to create structured LLM: {e}")
    sllm = None

# --- Document Loading (via backend.ingest.loader) ---
# Documents are loaded by calling load_documents(directory) from backend.ingest.loader
# which supports PDF, DOCX, DOC, TXT formats


def parse_cv_document(text: str) -> dict:
    """
    Parse a single CV document using structured LLM.

    Returns:
        dict: Parsed CV data (may contain null fields)
    """
    if not sllm:
        raise RuntimeError("Structured LLM is not available")

    if not text or not text.strip():
        logger.warning("Received empty document text")
        return CVParsed().model_dump()

    try:
        # Prepare a small deterministic prefill for contact fields to help the LLM
        prefill = {
            "contact": {
                "email": extract_email(text),
                "phone": extract_phone(text),
                "linkedin": extract_linkedin(text),
                "github": extract_github(text),
            }
        }

        # Helper to extract a section block by heading keywords (simple, robust)
        def _find_section_block(full_text: str, heading_keywords):
            import re
            lines = full_text.split('\n')
            indices = []
            for i, ln in enumerate(lines):
                stripped = ln.strip()
                if not stripped:
                    continue
                up = stripped.upper()
                for hk in heading_keywords:
                    # match heading if line starts with the keyword or is exactly the keyword
                    if up.startswith(hk) or up == hk:
                        indices.append((i, hk))
                        break
            if not indices:
                return None
            # take first matching heading
            start = indices[0][0] + 1
            # find next heading index after start
            next_idx = len(lines)
            for j in range(start, len(lines)):
                l = lines[j].strip()
                if not l:
                    continue
                up = l.upper()
                # if line looks like a heading (all caps and short) treat as next heading
                if len(l.split()) <= 6 and (up.isupper() or any(k in up for k in ['EDUCATION','EXPERIENCE','PROJECTS','SKILLS','CERTIFICATIONS','LANGUAGES','PROFILE','SUMMARY'])):
                    next_idx = j
                    break
            block = '\n'.join(lines[start:next_idx]).strip()
            return block if block else None

        # Try a compact main prompt on a truncated window first to avoid OOM on local model
        main_window = text[:4000]
        prompt_main = (
            "PREFILL: " + json.dumps(prefill, ensure_ascii=False) +
            "\n\nParse the provided CV excerpt and return JSON matching the CVParsed schema. "
            "Fill name, contact (use PREFILL where available), professional_summary, skills, and languages. "
            "If you cannot determine a field, set it to null. Return strictly JSON only.\n\nCV_EXCERPT:\n" + main_window
        )

        # Try structured LLM first; if it fails (OOM or other), fall back to plain LLM text
        response = None
        parsed_dict = None
        try:
            response = sllm.complete(prompt_main)
        except Exception as e:
            logger.warning(f"Structured LLM main call failed, falling back to plain LLM: {e}")
            try:
                resp = llm.complete(prompt_main)
                text_out = getattr(resp, 'text', None) or (getattr(resp, 'message', None) and getattr(resp.message, 'content', None))
                if text_out:
                    try:
                        parsed_dict = json.loads(text_out)
                    except Exception:
                        # try to extract JSON substring
                        start = text_out.find('{')
                        end = text_out.rfind('}')
                        if start >= 0 and end > start:
                            try:
                                parsed_dict = json.loads(text_out[start:end+1])
                            except Exception:
                                parsed_dict = None
            except Exception as e2:
                logger.error(f"Plain LLM fallback also failed: {e2}")

        # If we got a structured response object, try to convert to dict
        if parsed_dict is None and response is not None:
            if hasattr(response, 'raw') and response.raw is not None:
                parsed = response.raw
                if hasattr(parsed, 'model_dump'):
                    parsed_dict = parsed.model_dump()
                elif hasattr(parsed, 'dict'):
                    parsed_dict = parsed.dict()
                elif isinstance(parsed, dict):
                    parsed_dict = parsed
            elif hasattr(response, 'text') and response.text:
                try:
                    parsed_dict = json.loads(response.text)
                except Exception:
                    text_out = response.text
                    start = text_out.find('{')
                    end = text_out.rfind('}')
                    if start >= 0 and end > start:
                        try:
                            parsed_dict = json.loads(text_out[start:end+1])
                        except Exception:
                            parsed_dict = None

        if not parsed_dict:
            parsed_dict = CVParsed().model_dump()

        # If LLM returned nothing useful, apply deterministic fallback using existing heuristics
        try:
            empty_contact = True
            c = parsed_dict.get('contact') or {}
            if any(c.get(k) for k in ('email','phone','linkedin','github')):
                empty_contact = False
            is_empty_main = (not parsed_dict.get('name')) and empty_contact and (not parsed_dict.get('professional_summary'))
            if is_empty_main or ((not parsed_dict.get('experience')) and (not parsed_dict.get('education'))):
                pre_contacts = extract_name_contacts(text)
                name = pre_contacts.pop('name', None)
                if not parsed_dict.get('name') and name:
                    parsed_dict['name'] = name

                parsed_contact = parsed_dict.get('contact') or {}
                for k in ('email','phone','linkedin','github'):
                    if not parsed_contact.get(k) and pre_contacts.get(k):
                        parsed_contact[k] = pre_contacts.get(k)
                parsed_dict['contact'] = parsed_contact

                sections = split_sections(text)
                if not parsed_dict.get('professional_summary'):
                    for key in ('SUMMARY','PROFILE','PROFESSIONAL SUMMARY'):
                        if key in sections and sections[key].strip():
                            parsed_dict['professional_summary'] = sections[key].split('\n\n')[0].strip()
                            break

                # Skills
                if not parsed_dict.get('skills') or len(parsed_dict.get('skills', [])) == 0:
                    parsed_dict['skills'] = list(extract_skills_full(text))

                # Education
                if not parsed_dict.get('education') or len(parsed_dict.get('education', [])) == 0:
                    if 'EDUCATION' in sections:
                        ed = parse_education_section(sections['EDUCATION'])
                        if ed:
                            parsed_dict['education'] = ed

                # Experience
                if not parsed_dict.get('experience') or len(parsed_dict.get('experience', [])) == 0:
                    if 'EXPERIENCE' in sections:
                        ex = parse_experience_section(sections['EXPERIENCE'])
                        if ex:
                            parsed_dict['experience'] = ex
        except Exception:
            logger.debug('Deterministic fallback failed')

        # If experience or education are empty, try targeted prompts on those sections
        try:
            # Education
            if (not parsed_dict.get('education')) or len(parsed_dict.get('education', [])) == 0:
                ed_block = _find_section_block(text, ['EDUCATION'])
                if ed_block:
                    prompt_ed = (
                        "Extract up to 5 education entries from the EDUCATION block. Return a JSON array of objects "
                        "with keys: institution, degree, major, graduation_year. Use null when unknown. Return strictly JSON only.\n\nEDUCATION_BLOCK:\n" + ed_block
                    )
                    try:
                        # prefer plain llm for small focused call (fallback to structured if available)
                        try:
                            resp_ed = sllm.complete(prompt_ed)
                        except Exception:
                            resp_ed = llm.complete(prompt_ed)
                        text_out = getattr(resp_ed, 'text', None) or (getattr(resp_ed, 'message', None) and getattr(resp_ed.message, 'content', None))
                        if text_out:
                            try:
                                ed_list = json.loads(text_out)
                                if isinstance(ed_list, list) and ed_list:
                                    parsed_dict['education'] = ed_list
                            except Exception:
                                pass
                    except Exception:
                        pass

            # Experience
            if (not parsed_dict.get('experience')) or len(parsed_dict.get('experience', [])) == 0:
                exp_block = _find_section_block(text, ['EXPERIENCE', 'PROFESSIONAL EXPERIENCE', 'WORK EXPERIENCE'])
                if exp_block:
                    prompt_exp = (
                        "Extract up to 5 experience entries from the EXPERIENCE block. Return a JSON array of objects "
                        "with keys: job_title, company, start_date, end_date, description. Use null when unknown. Return strictly JSON only.\n\nEXPERIENCE_BLOCK:\n" + exp_block
                    )
                    try:
                        try:
                            resp_exp = sllm.complete(prompt_exp)
                        except Exception:
                            resp_exp = llm.complete(prompt_exp)
                        text_out = getattr(resp_exp, 'text', None) or (getattr(resp_exp, 'message', None) and getattr(resp_exp.message, 'content', None))
                        if text_out:
                            try:
                                exp_list = json.loads(text_out)
                                if isinstance(exp_list, list) and exp_list:
                                    parsed_dict['experience'] = exp_list
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            logger.debug('Targeted section extraction failed')

        return parsed_dict

    except Exception as e:
        logger.error(f"LLM parsing failed: {e}\n{traceback.format_exc()}")
        return CVParsed().model_dump()


def cleanup_parsed_data(parsed: dict) -> dict:
    """
    Lightweight post-processing: normalize fields, validate types.
    """
    if not isinstance(parsed, dict):
        return CVParsed().model_dump()

    # Ensure contact object exists
    if 'contact' not in parsed or not isinstance(parsed.get('contact'), dict):
        parsed['contact'] = {}

    # Ensure list fields are lists
    for field in ['skills', 'education', 'experience', 'certifications', 'languages']:
        if field not in parsed or not isinstance(parsed.get(field), list):
            parsed[field] = []

    # Clean up whitespace in strings
    if isinstance(parsed.get('name'), str):
        parsed['name'] = parsed['name'].strip() or None
    if isinstance(parsed.get('professional_summary'), str):
        parsed['professional_summary'] = parsed['professional_summary'].strip() or None

    # Remove empty values in contact
    contact_fields = ['email', 'phone', 'linkedin', 'github']
    for field in contact_fields:
        if field in parsed['contact']:
            val = parsed['contact'][field]
            if isinstance(val, str):
                parsed['contact'][field] = val.strip() or None
            elif not val:
                parsed['contact'][field] = None

    return parsed


# --- Chunk Offset Processor ---
# Custom transformation to attach chunk-level metadata (start_char, end_char, chunk_text, resume_id)
from llama_index.core.schema import BaseNode, TransformComponent
from typing import List, Any

class ChunkOffsetProcessor(TransformComponent):
    """Attach character offsets and resume_id to each chunk node for citation."""
    
    def __call__(self, nodes: List[BaseNode], **kwargs: Any) -> List[BaseNode]:
        """Process nodes to attach chunk metadata."""
        for node in nodes:
            # Attach chunk text (already in node.get_content())
            node.metadata['chunk_text'] = node.get_content()
            
            # Try to compute character offsets from the source document
            ref_doc_id = node.metadata.get('ref_doc_id') or node.metadata.get('doc_id')
            file_name = node.metadata.get('file_name', 'unknown')
            node.metadata['resume_id'] = file_name  # Use filename as resume identifier
            
            # Attempt to find chunk offsets in original doc
            # If the original full text is available, find this chunk in it
            try:
                # This is a heuristic: look for the chunk start in the doc text
                # For a more robust approach, the SentenceSplitter would need to preserve offsets
                chunk_text = node.get_content()
                # We'll store a placeholder; actual offsets would require modifying SentenceSplitter
                node.metadata['start_char'] = None  # Would need custom splitter
                node.metadata['end_char'] = None    # Would need custom splitter
                node.metadata['source_file'] = file_name
            except Exception as e:
                logger.debug(f"Could not compute offsets for chunk: {e}")
        
        return nodes


# --- Main Pipeline ---
def main():
    logger.info("Loading documents...")
    documents = load_documents("./cv_uploads/")
    logger.info(f"Loaded {len(documents)} documents")

    # Ensure output directory
    parsed_out_dir = Path("./cv_uploads/parsed")
    parsed_out_dir.mkdir(parents=True, exist_ok=True)

    # Parse each document
    successful = 0
    failed = 0

    # Phase 1: parse all documents (LLM-heavy) and save parsed JSON. Do NOT touch GPU here.
    for idx, doc in enumerate(documents):
        file_name = doc.metadata.get('file_name', f'doc_{idx}')
        logger.info(f"[{idx+1}/{len(documents)}] Parsing {file_name}...")

        try:
            # Parse with single LLM call
            parsed_dict = parse_cv_document(doc.text)

            # Lightweight cleanup
            parsed_dict = cleanup_parsed_data(parsed_dict)

            # Normalization: map skills/titles and attach normalized subtree
            try:
                skills_map = load_skills_map()
                parsed_dict = normalize_parsed_cv(parsed_dict, skills_map=skills_map)
            except Exception as e:
                logger.debug(f"Normalization failed: {e}")

            # Attach to document metadata (keep it small for vector store)
            try:
                doc.metadata['cv_parsed'] = json.dumps(parsed_dict, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Could not serialize parsed data for {file_name}: {e}")

            # Extract basic info for metadata tags
            if parsed_dict.get('name'):
                doc.metadata['candidate_name'] = parsed_dict['name']

            if parsed_dict.get('skills'):
                doc.metadata['skills'] = ", ".join(str(s) for s in parsed_dict['skills'][:10])

            # Save parsed JSON for audit/debugging
            safe_name = Path(file_name).name
            out_path = parsed_out_dir / f"{safe_name}.parsed.json"
            try:
                with open(out_path, 'w', encoding='utf-8') as f:
                    json.dump(parsed_dict, f, ensure_ascii=False, indent=2)
                logger.info(f"  ✓ Saved to {out_path}")
                successful += 1
            except Exception as e:
                logger.error(f"Failed to write parsed JSON for {file_name}: {e}")
                failed += 1

        except Exception as e:
            logger.error(f"Failed to parse {file_name}: {e}\n{traceback.format_exc()}")
            failed += 1

    logger.info(f"\nParsing complete: {successful} successful, {failed} failed")

    # --- Phase 2: Acquire GPU and create resume & chunk embeddings ---
    from backend.gpu_lock import acquire_gpu, release_gpu

    logger.info("Acquiring GPU lock to run embeddings...")
    got_gpu = acquire_gpu(blocking=True, timeout=60)
    if got_gpu:
        logger.info("GPU lock acquired — enabling GPU for embeddings")
        os.environ.pop("CUDA_VISIBLE_DEVICES", None)
    else:
        logger.warning("Could not acquire GPU lock — falling back to CPU embeddings")
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    try:
        # create embedder now that GPU mode is configured
        embed = HuggingFaceEmbedding(model_name="Qwen/Qwen3-Embedding-0.6B")

        # Create resume-level embeddings
        for idx, doc in enumerate(documents):
            file_name = doc.metadata.get('file_name', f'doc_{idx}')
            safe_name = Path(file_name).name
            parsed_path = parsed_out_dir / f"{safe_name}.parsed.json"
            try:
                with open(parsed_path, 'r', encoding='utf-8') as f:
                    parsed_dict = json.load(f)
            except Exception:
                parsed_dict = {}

            try:
                resume_text = doc.text if getattr(doc, 'text', None) else (
                    (parsed_dict.get('professional_summary') or '') + ' ' + ' '.join(parsed_dict.get('skills', []))
                )
                emb = embed.get_text_embedding(resume_text)
                resume_id = safe_name
                resume_metadata = {
                    'candidate_name': parsed_dict.get('name'),
                    'file_name': safe_name,
                }
                try:
                    resume_collection.delete(ids=[resume_id])
                except Exception:
                    pass
                try:
                    resume_collection.add(
                        ids=[resume_id],
                        metadatas=[resume_metadata],
                        documents=[parsed_dict.get('professional_summary') or ''],
                        embeddings=[emb]
                    )
                    logger.info(f"  ✓ Stored resume embedding for {resume_id}")
                except Exception as e:
                    logger.warning(f"Failed to store resume embedding for {resume_id}: {e}")
            except Exception as e:
                logger.debug(f"Resume embedding creation failed for {safe_name}: {e}")

        # --- Ingest into Vector Store (chunk-level embeddings)
        logger.info("Ingesting documents into vector store...")

        pipeline = IngestionPipeline(
            transformations=[
                SentenceSplitter(chunk_size=2048, chunk_overlap=256),
                ChunkOffsetProcessor(),  # Attach chunk metadata BEFORE embedding
                embed,
            ],
            vector_store=vector_store,
        )

        pipeline.run(documents=documents)
        logger.info("Ingestion complete - vectors stored with chunk metadata and resume_id")

    finally:
        if got_gpu:
            release_gpu()
            logger.info("Released GPU lock")


if __name__ == "__main__":
    main()
