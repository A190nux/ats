from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb
import spacy
from data_schemas.cv import *
from data_schemas.parse_utils import (
    extract_name_contacts, split_sections, extract_skills,
    parse_experience_section, parse_education_section
)
import json

# Load spacy model
try:
    nlp = spacy.load("en_core_web_sm")
except:
    # Download if not installed
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")
import os
from pathlib import Path
import logging
import traceback

# Configure basic logging
logging.basicConfig(level=logging.DEBUG)

# --- 1. Connect to Core Components ---
llm = Ollama(
    model="phi4-mini:latest", 
    request_timeout=300.0,  # Increase timeout for structured generation
    temperature=0.1,  # Lower temperature for more focused/structured outputs
    additional_kwargs={
        "system": "You are a CV parser. Use any deterministic prefill provided to you to help fill missing fields. Return only valid JSON matching the provided schema. If a field is ambiguous, prefer leaving it null rather than inventing data.",
    }
)
embed_model = HuggingFaceEmbedding(model_name="Qwen/Qwen3-Embedding-0.6B") # Open-source model 

# --- 2. Connect to ChromaDB ---
db = chromadb.PersistentClient(path="./chroma_db")
chroma_collection = db.get_or_create_collection("cv_collection")
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
storage_context = StorageContext.from_defaults(vector_store=vector_store)

# --- 3. Define the Structured LLM for parsing ---
# Prefer the Structured LLM (.as_structured_llm) approach where available.
try:
    sllm = llm.as_structured_llm(CVParsed)
except Exception:
    sllm = None
    logging.exception(
        "Could not create a Structured LLM via llm.as_structured_llm(CVParsed)."
    )

# --- 4a. Run Parsing on Full Documents ---
# 1. Load documents (each document is one full CV file)
import os
from pathlib import Path
from typing import List
import pypdf
from llama_index.core import Document

def load_documents(directory: str) -> List[Document]:
    documents = []
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        
        # Skip directories and hidden files
        if os.path.isdir(filepath) or filename.startswith('.'):
            continue
            
        if filename.lower().endswith('.pdf'):
            # Handle PDF files
            with open(filepath, 'rb') as file:
                pdf = pypdf.PdfReader(file)
                text = '\n'.join(page.extract_text() for page in pdf.pages)
                documents.append(Document(
                    text=text,
                    metadata={"file_name": filename}
                ))
        else:
            try:
                # Use SimpleDirectoryReader for non-PDF files
                reader = SimpleDirectoryReader(input_files=[filepath])
                documents.extend(reader.load_data())
            except Exception as e:
                print(f"Warning: Could not load file {filename}: {e}")
    
    return documents

# Load documents using our custom loader
documents = load_documents("./cv_uploads/")

print(f"Loaded {len(documents)} documents for parsing:")
for doc in documents:
    print(f"  - {doc.metadata.get('file_name', 'Unknown file')}")

# Ensure parsed output directory exists for auditability
parsed_out_dir = Path("./cv_uploads/parsed")
parsed_out_dir.mkdir(parents=True, exist_ok=True)

def _invoke_structured_safe(sllm_obj, text, prefill=None):
    """Invoke the Structured LLM and return (parsed_dict, raw_response).

    This follows the documented pattern where sllm.complete(text) returns a
    CompletionResponse with .raw (Pydantic object) and .text (JSON string).
    """
    import time
    from typing import Optional, Tuple, Any
    
    def try_variant(fn, text: str, max_retries: int = 2) -> Optional[Tuple[Any, Any]]:
        """Try a variant with retries on timeout."""
        for attempt in range(max_retries + 1):
            try:
                resp = fn(sllm_obj, text)
                if resp is None:
                    continue
                
                # Try to get structured data from various response shapes
                if hasattr(resp, 'raw') and resp.raw is not None:
                    raw = resp.raw
                    if hasattr(raw, 'model_dump'):
                        return raw.model_dump(), resp
                    if hasattr(raw, 'dict'):
                        return raw.dict(), resp
                    if isinstance(raw, dict):
                        return raw, resp
                    return {"raw": str(raw)}, resp
                
                # Try resp.text or resp.message.content
                text_out = getattr(resp, 'text', None)
                if not text_out and hasattr(resp, 'message'):
                    text_out = getattr(resp.message, 'content', None)
                
                if text_out:
                    if isinstance(text_out, dict):
                        return text_out, resp
                    try:
                        return json.loads(text_out), resp
                    except Exception:
                        # Try to extract JSON substring
                        start_idx = min([i for i in [text_out.find('{'), text_out.find('[')] if i >= 0], default=-1)
                        if start_idx >= 0:
                            if text_out[start_idx] == '{':
                                end_idx = text_out.rfind('}')
                            else:
                                end_idx = text_out.rfind(']')
                            if end_idx > start_idx:
                                try:
                                    parsed = json.loads(text_out[start_idx:end_idx+1])
                                    return parsed, resp
                                except Exception:
                                    pass
                        return {"raw_text": text_out}, resp
                
            except Exception as e:
                if 'timed out' in str(e).lower() and attempt < max_retries:
                    logging.info(f"Attempt {attempt + 1} timed out, retrying in 2s...")
                    time.sleep(2)
                    continue
                logging.debug(f"Variant failed: {e}")
            
            return None
    
    if sllm_obj is None:
        raise RuntimeError("Structured LLM (sllm) is not available.")

    # Prepare prompt text: include deterministic prefill if provided (keeps it concise)
    prompt_input = text
    try:
        if prefill:
            import json as _json
            small = {
                'contact': {k: v for k, v in prefill.get('contact', {}).items() if v},
                'skills': prefill.get('skills', [])[:20],
            }
            prefill_str = _json.dumps(small, ensure_ascii=False)
            prompt_input = f"PREFILL: {prefill_str}\n\nPlease parse the following CV and return only valid JSON matching the CV schema.\n\nCV TEXT:\n" + text
    except Exception:
        prompt_input = text

    # Try variants with retry logic
    variants = [
        lambda o, t: o.complete(t),
        lambda o, t: o.complete(text=t),
        lambda o, t: o(t),
    ]
    
    for fn in variants:
        result = try_variant(fn, prompt_input)
        if result is not None:
            return result
    
    # If structured variants failed, try plain LLM with retries
    logging.info("Structured LLM variants failed; trying plain LLM...")
    try:
        result = try_variant(lambda _, t: llm.complete(t), prompt_input, max_retries=1)
        if result is not None:
            return result
    except Exception as e:
        logging.debug(f"Plain LLM fallback failed: {e}")
    raise RuntimeError("Structured LLM did not return a usable response.")


def _invoke_validation_llm(parsed: dict, prefill: dict, doc_text: str):
    """Ask the LLM a small, focused question to fill or validate only missing fields.

    Returns a dict of suggested field-values (may be empty). This call is conservative:
    instruct LLM to return only JSON and to prefer null when unsure.
    """
    # Determine which top-level fields are missing or empty
    missing = {}
    # name
    if not parsed.get('name'):
        missing['name'] = True
    # contact subfields
    parsed_contact = parsed.get('contact') or {}
    for k in ('email', 'phone', 'linkedin', 'github'):
        if not parsed_contact.get(k) and not prefill.get('contact', {}).get(k):
            missing.setdefault('contact', {})[k] = True
        else:
            # if deterministic prefill has the value, ensure it's applied
            if not parsed_contact.get(k) and prefill.get('contact', {}).get(k):
                parsed_contact[k] = prefill['contact'][k]
    # experience: if empty, ask LLM to extract up to 3 entries
    if not parsed.get('experience') or len(parsed.get('experience', [])) == 0:
        missing['experience'] = True

    if not missing:
        return {}

    # Build a compact prompt
    small_prefill = {
        'contact': {k: v for k, v in (prefill.get('contact') or {}).items() if v},
        'skills': prefill.get('skills', [])[:20],
    }
    prompt = (
        "You are a strict JSON-only assistant. Using the CV text and any provided prefill, "
        "return a JSON object containing only the missing fields requested. "
        "If unsure about a field, set it to null. Do not invent details.\n\n"
    )
    prompt += f"PREFILL: {json.dumps(small_prefill, ensure_ascii=False)}\n\n"
    # Tell LLM exactly which keys we want
    ask_keys = list(missing.keys())
    prompt += f"MISSING_KEYS: {json.dumps(ask_keys)}\n\n"
    prompt += "CV_TEXT:\n" + (doc_text[:5000] if len(doc_text) > 5000 else doc_text)

    # Call the LLM (prefer structured variant if available)
    try:
        resp = llm.complete(prompt)
        text_out = getattr(resp, 'text', None) or (getattr(resp, 'message', None) and getattr(resp.message, 'content', None))
        if not text_out:
            return {}
        # Try to parse JSON from response
        try:
            parsed_json = json.loads(text_out)
        except Exception:
            # Try to extract JSON substring
            start_idx = min([i for i in [text_out.find('{'), text_out.find('[')] if i >= 0], default=-1)
            if start_idx >= 0:
                if text_out[start_idx] == '{':
                    end_idx = text_out.rfind('}')
                else:
                    end_idx = text_out.rfind(']')
                if end_idx > start_idx:
                    try:
                        parsed_json = json.loads(text_out[start_idx:end_idx+1])
                    except Exception:
                        parsed_json = {}
                else:
                    parsed_json = {}
            else:
                parsed_json = {}
        if isinstance(parsed_json, dict):
            return parsed_json
    except Exception as e:
        logging.debug(f"Validation LLM call failed: {e}")
    return {}


def _invoke_education_llm(education_raw: str, prefill: dict = None, max_entries: int = 3):
    """Ask the LLM to extract up to `max_entries` education records from a raw education block.

    The LLM is instructed to be conservative: return only JSON (an array) with objects
    containing keys: institution, degree, major, graduation_year. Use null when unsure.
    """
    if not education_raw or not education_raw.strip():
        return []

    small_prefill = {
        'contact': {k: v for k, v in (prefill.get('contact') or {}).items() if v} if prefill else {},
        'skills': prefill.get('skills', [])[:20] if prefill else []
    }

    prompt = (
        "You are a strict JSON-only assistant. Extract up to " + str(max_entries) +
        " education entries from the provided EDUCATION block. Return a JSON array of objects. "
        "Each object must have the keys: institution, degree, major, graduation_year. "
        "If a field cannot be determined, set it to null. Do NOT invent data. "
        "Trim long text; keep institution and degree concise."
        "\n\nPREFILL: " + json.dumps(small_prefill, ensure_ascii=False) + "\n\n"
    )
    prompt += "EDUCATION_BLOCK:\n" + (education_raw[:8000] if len(education_raw) > 8000 else education_raw)

    try:
        resp = llm.complete(prompt)
        text_out = getattr(resp, 'text', None) or (getattr(resp, 'message', None) and getattr(resp.message, 'content', None))
        if not text_out:
            return []
        # Try parsing JSON
        try:
            parsed_json = json.loads(text_out)
        except Exception:
            # Extract JSON substring heuristically
            start_idx = min([i for i in [text_out.find('['), text_out.find('{')] if i >= 0], default=-1)
            if start_idx >= 0:
                if text_out[start_idx] == '[':
                    end_idx = text_out.rfind(']')
                else:
                    end_idx = text_out.rfind('}')
                if end_idx > start_idx:
                    try:
                        parsed_json = json.loads(text_out[start_idx:end_idx+1])
                    except Exception:
                        parsed_json = []
                else:
                    parsed_json = []
            else:
                parsed_json = []

        if isinstance(parsed_json, list):
            # sanitize entries: ensure keys exist
            out = []
            for item in parsed_json[:max_entries]:
                if not isinstance(item, dict):
                    continue
                safe = {
                    'institution': item.get('institution') if item.get('institution') else None,
                    'degree': item.get('degree') if item.get('degree') else None,
                    'major': item.get('major') if item.get('major') else None,
                    'graduation_year': None
                }
                gy = item.get('graduation_year')
                try:
                    if isinstance(gy, (int, float)):
                        safe['graduation_year'] = int(gy)
                    elif isinstance(gy, str) and gy.isdigit():
                        safe['graduation_year'] = int(gy)
                except Exception:
                    safe['graduation_year'] = None
                out.append(safe)
            return out
    except Exception:
        logging.debug('Education LLM call failed')
    return []


for idx, doc in enumerate(documents):
    try:
        # Deterministic pre-extraction: contacts, sections, skills
        prefill = {}
        try:
            # Extract name and contacts
            pre_contacts = extract_name_contacts(doc.text)
            name = pre_contacts.pop('name', None)  # Remove name from contacts dict
            
            # Get sections
            pre_sections = split_sections(doc.text)
            
            # Extract skills using our improved extractor
            pre_skills = list(extract_skills(doc.text))
            
            # Parse experience section if present
            experience_entries = []
            if 'EXPERIENCE' in pre_sections:
                experience_entries = parse_experience_section(pre_sections['EXPERIENCE'], nlp)
            
            prefill = {
                'name': name,
                'contact': pre_contacts,
                'sections': pre_sections,
                'skills': pre_skills,
                'experience': experience_entries
            }
            # Attach a small metadata summary (avoid large metadata which breaks chunking)
            try:
                summary_snippet = None
                for key in ('SUMMARY', 'PROFESSIONAL SUMMARY'):
                    if key in pre_sections and pre_sections[key].strip():
                        summary_snippet = pre_sections[key].split('\n\n')[0].strip()
                        break
                meta_prefill = {
                    'contact': {k: v for k, v in pre_contacts.items() if v},
                    'skills': pre_skills[:20],
                    'summary_snippet': (summary_snippet[:300] + '...') if summary_snippet and len(summary_snippet) > 300 else summary_snippet,
                }
                doc.metadata['deterministic_prefill'] = json.dumps(meta_prefill, ensure_ascii=False)
            except Exception:
                # Fallback to a tiny string so metadata stays small
                try:
                    doc.metadata['deterministic_prefill'] = json.dumps({'contact': pre_contacts.get('email')})
                except Exception:
                    doc.metadata['deterministic_prefill'] = 'prefill'
        except Exception as e:
            logging.debug(f"Deterministic prefill failed for {doc.metadata.get('file_name')}: {e}")

        parsed_dict, raw_resp = _invoke_structured_safe(sllm, doc.text, prefill=prefill)

        # Merge deterministic prefill into parsed result when fields are missing
        try:
            if isinstance(parsed_dict, dict):
                # Merge contact fields
                parsed_contact = parsed_dict.get('contact') or {}
                for k in ('email', 'phone', 'linkedin', 'github'):
                    if not parsed_contact.get(k) and prefill.get('contact', {}).get(k):
                        parsed_contact[k] = prefill['contact'][k]
                parsed_dict['contact'] = parsed_contact

                # Merge professional_summary if missing
                if not parsed_dict.get('professional_summary'):
                    for key in ('SUMMARY', 'PROFESSIONAL SUMMARY'):
                        if key in prefill.get('sections', {}) and prefill['sections'][key].strip():
                            parsed_dict['professional_summary'] = prefill['sections'][key].split('\n\n')[0].strip()
                            break

                # Merge name if missing
                if not parsed_dict.get('name') and prefill.get('name'):
                    parsed_dict['name'] = prefill['name']

                # If still missing critical fields, run a small validation-only LLM pass
                try:
                    validation_suggestions = _invoke_validation_llm(parsed_dict, prefill, doc.text)
                    if isinstance(validation_suggestions, dict):
                        # Merge only the provided keys (don't overwrite existing values)
                        for k, v in validation_suggestions.items():
                            if k == 'contact' and isinstance(v, dict):
                                parsed_contact = parsed_dict.get('contact') or {}
                                for ck, cv in v.items():
                                    if not parsed_contact.get(ck) and cv:
                                        parsed_contact[ck] = cv
                                parsed_dict['contact'] = parsed_contact
                            else:
                                if not parsed_dict.get(k) and v:
                                    parsed_dict[k] = v
                except Exception:
                    logging.debug('Validation LLM merge failed')

                # Merge skills if missing or empty; normalize
                if (not parsed_dict.get('skills')) or len(parsed_dict.get('skills', [])) == 0:
                    if prefill.get('skills'):
                        parsed_dict['skills'] = list(extract_skills('\n'.join(prefill['skills'])))
                else:
                    # Normalize any LLM-provided skills
                    try:
                        if isinstance(parsed_dict.get('skills'), (list, tuple)):
                            parsed_dict['skills'] = list(extract_skills('\n'.join(map(str, parsed_dict['skills']))))
                    except Exception:
                        pass

                # Keep raw education/experience if arrays are empty
                if (not parsed_dict.get('education')) or len(parsed_dict.get('education', [])) == 0:
                    # Prefer deterministic structured education when available
                    try:
                        if 'EDUCATION' in prefill.get('sections', {}):
                            ed_block = prefill['sections']['EDUCATION']
                            ed = parse_education_section(ed_block, nlp)
                            if ed:
                                parsed_dict['education'] = ed
                            else:
                                # No deterministic entries: keep raw and ask the LLM conservatively
                                parsed_dict['education_raw'] = ed_block
                                try:
                                    llm_ed = _invoke_education_llm(ed_block, prefill=prefill, max_entries=3)
                                    if llm_ed:
                                        parsed_dict['education'] = llm_ed
                                        # remove raw once we have structured LLM output
                                        parsed_dict.pop('education_raw', None)
                                except Exception:
                                    pass
                    except Exception:
                        if 'EDUCATION' in prefill.get('sections', {}):
                            parsed_dict['education_raw'] = prefill['sections']['EDUCATION']
                if (not parsed_dict.get('experience')) or len(parsed_dict.get('experience', [])) == 0:
                    if prefill.get('experience'):
                        parsed_dict['experience'] = prefill['experience']
                    elif 'EXPERIENCE' in prefill.get('sections', {}):
                        parsed_dict['experience_raw'] = prefill['sections']['EXPERIENCE']
        except Exception as e:
            logging.debug(f"Failed to merge deterministic prefill: {e}")

        # Store the structured object in the document's metadata as a JSON string
        # (vector store metadata requires flat primitive types)
        try:
            doc.metadata['cv_structured_data'] = json.dumps(parsed_dict, ensure_ascii=False)
        except Exception:
            doc.metadata['cv_structured_data'] = str(parsed_dict)

        # Safely extract candidate name and skills
        candidate_name = parsed_dict.get('name') if isinstance(parsed_dict, dict) else None
        if candidate_name:
            doc.metadata['candidate_name'] = candidate_name

        skills_val = parsed_dict.get('skills') if isinstance(parsed_dict, dict) else None
        if isinstance(skills_val, (list, tuple)):
            doc.metadata['skills'] = ", ".join([str(s) for s in skills_val if s])
        elif isinstance(skills_val, str):
            doc.metadata['skills'] = skills_val

        # Persist parsed JSON for audit / debugging
        source_name = doc.metadata.get('file_name') or doc.metadata.get('source') or f"doc_{idx}"
        safe_name = Path(source_name).name
        out_path = parsed_out_dir / f"{safe_name}.parsed.json"
        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(parsed_dict, f, ensure_ascii=False, indent=2)
        except Exception:
            logging.warning(f"Failed to write parsed JSON for {safe_name}:\n{traceback.format_exc()}")

    except Exception as e:
        logging.error(f"Failed to parse CV: {doc.metadata.get('file_name', f'doc_{idx}')}. Error: {e}\n{traceback.format_exc()}")
        doc.metadata['cv_structured_data'] = None


# --- 4b. Define and Run the RAG Pipeline ---

pipeline = IngestionPipeline(
    transformations=[
        SentenceSplitter(
            chunk_size=2048,
            chunk_overlap=256,
        ),
        embed_model, # Embed the chunked nodes
    ],
    vector_store=vector_store,
)

# Run the pipeline on the documents which now have the metadata attached.
pipeline.run(documents=documents)

print("Ingestion complete. Vector store updated with embedded chunks and structured metadata.")