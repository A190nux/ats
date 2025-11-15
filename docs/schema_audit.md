# Schema Audit — ATS Project

Date: 2025-11-13

This document summarizes the current parsing schema, utility functions, skills taxonomy, and gaps relative to the project requirements. It is derived from the code in `data_schemas/` and the ingestion scripts (`ingest.py`, `ingest_simplified.py`).

**Scope**: `data_schemas/cv.py`, `data_schemas/parse_utils.py`, `data_schemas/parse_utils_minimal.py`, `data_schemas/skills_map.json`, `ingest.py`, `ingest_simplified.py`.

---

## 1. Main schema (`CVParsed`)

Top-level model: `CVParsed` (Pydantic)

- `name` (Optional[str]) — candidate full name
- `contact` (CandidateContact)
  - `email` (Optional[str])
  - `phone` (Optional[str])
  - `linkedin` (Optional[str])
- `professional_summary` (Optional[str])
- `education` (List[EducationEntry])
  - `institution` (str)
  - `degree` (Optional[str])
  - `major` (Optional[str])
  - `graduation_year` (Optional[int])
- `experience` (List[ExperienceEntry])
  - `job_title` (str)
  - `company` (str)
  - `start_date` (Optional[str])
  - `end_date` (Optional[str])
  - `description` (Optional[str])
- `skills` (List[str])
- `certifications` (List[CertificationEntry])
  - `name` (str)
  - `issuer` (Optional[str])
  - `year` (Optional[int])
- `languages` (List[str])

Notes:
- All lists default to empty lists; `contact` defaults to a CandidateContact instance so downstream code can assume the object exists.
- Dates in experiences are stored as strings where parsers format them; education graduation year is an integer where possible.

---

## 2. Parsing utilities

There are two utility modules: `parse_utils.py` (full deterministic heuristics) and `parse_utils_minimal.py` (smaller helpers used by `ingest_simplified.py`).

### `parse_utils.py` (full)
- Responsibilities:
  - `extract_name_contacts(text)` — heuristics to find `name`, `email`, `phone`, `linkedin`, `github`.
  - `split_sections(text)` — section detection (HEADINGS like SKILLS/EXPERIENCE/EDUCATION etc.).
  - `extract_skills(text)` — canonicalize using `skills_map.json` and extract from SKILLS section or global pass.
  - `parse_experience_section(text, nlp=None)` — split EXPERIENCE into entries with title/company/dates/description; uses `dateparser` and optional spaCy NER for ORG detection.
  - `parse_education_section(text, nlp=None)` — parse EDUCATION blocks (institution, degree, major, years).

- External optional deps: `dateparser`, `spaCy` (en_core_web_sm). If these are missing functions degrade gracefully.

### `parse_utils_minimal.py` (minimal)
- A smaller set of helpers used by the simplified pipeline:
  - `extract_email`, `extract_phone`, `extract_linkedin`, `extract_github`
  - `extract_skills_from_section(text)` — conservative SKILLS section extractor
- Intentionally removes heavier deterministic parsing and NER in favor of LLM-first parsing.

---

## 3. Skills mapping (`skills_map.json`)

- A small key→canonical mapping (lowercase keys such as `tensorflow` -> `TensorFlow`, `fastapi` -> `FastAPI`, `pandas` -> `Pandas`, etc.).
- Used by `extract_skills` (full utils) and minimally by `parse_utils_minimal`.

Limitations:
- The map is small and does not include alternate spellings, seniority titles, or domain-group mappings.
- It expects lowercased keys in some lookups but also tries raw lookups.

---

## 4. How ingestion currently uses schemas/utilities

- `ingest_simplified.py`:
  - Uses `CVParsed` as the structured schema for the LLM (`sllm = llm.as_structured_llm(CVParsed)`).
  - Prefills basic contact fields using `parse_utils_minimal` (`extract_email`, `extract_phone`, `extract_linkedin`, `extract_github`).
  - Falls back to deterministic utilities from `parse_utils.py` only when LLM output is empty or incomplete (e.g., `extract_name_contacts`, `split_sections`, `parse_experience_section`, `parse_education_section`, `extract_skills`).
  - Performs lightweight `cleanup_parsed_data(parsed)` to normalize types and strip whitespace.
  - Persists parsed JSON to `./cv_uploads/parsed/*.parsed.json` and stores metadata in the vector store documents.

- `ingest.py` (original / fuller pipeline):
  - Uses `parse_utils.py` more heavily for deterministic prefill and to merge deterministic results with LLM outputs.
  - Uses spaCy (if available) and `dateparser` where helpful.
  - Includes a validation LLM and smaller auxiliary LLM calls to fill missing fields.
  - Saves `doc.metadata['cv_structured_data']` for ingestion.

---

## 5. Gaps vs project requirements (mapped to schema & parsing)

1. Contact fields are limited:
   - `CVParsed.contact` includes `email`, `phone`, `linkedin`, `github`. Missing: `address`, `city`, `country`, `portfolio_url`, `other_socials`.
2. No explicit candidate identifier or normalized ID schema for deduplication:
   - Persisted metadata currently uses file-based names and JSON blobs; no canonical `candidate_id` or `source_id` field.
3. Experience granularity and normalization gaps:
   - `ExperienceEntry` stores free-text `job_title` and `company` as-is. There is no canonical job title taxonomy, normalized company identifiers, or computed `years_experience` fields.
4. Education normalization:
   - `EducationEntry` has basic fields but lacks `degree_level` (enum: Bachelor/Master/PhD), `country`, or normalized institution IDs.
5. Skills taxonomy is shallow:
   - `skills_map.json` is a good start but limited; no multi-word variant handling or hierarchical grouping (e.g., `NLP` -> category `AI/ML`).
6. Missing provenance & offsets:
   - For RAG and ranking, we need chunk offsets (start/end character indices) and `source_snippet` references stored alongside each embedding.
7. No explicit fields for seniority, certifications' expiration, or skill years/proficiency.
8. No structure for JD matching metadata or scoring fields like `match_score`, `matched_skills`, or clinician-friendly `reasoning` field.

---

## 6. Recommended schema additions

These are additive; existing parsers and LLM outputs can keep working while we gradually populate new fields.

- Top-level additions to `CVParsed`:
  - `candidate_id: Optional[str]` — canonical stable id (UUID or hash of email+name+source) for deduplication and record linking.
  - `source`: Optional[dict] with `file_name`, `file_path`, `uploaded_at`, `source_type` (API/UI/bulk).
  - `provenance`: Optional[List[dict]] — list of provenance entries for changes/ingestion events.
  - `years_experience`: Optional[float] — computed estimate from experience date ranges.
  - `seniority`: Optional[str] — inferred seniority (e.g., Junior/Mid/Senior/Lead).

- Enrich `CandidateContact`:
  - Add `address`, `city`, `country`, `portfolio`, `other`.

- Enrich `ExperienceEntry`:
  - Add `start_date_iso`, `end_date_iso` (normalized ISO strings), `start_year`, `end_year`, `duration_months` (computed), `location`.
  - Add `matched_skills` (List[str]) — skills appearing in this role (used by ranking).

- Enrich `EducationEntry`:
  - Add `degree_level` (enum), `country`, `institution_normalized_id`.

- Add `parsing_metadata` top-level field:
  - `parser_version`, `llm_model`, `llm_confidence` (optional), `parse_warnings`, `provenance`.

- Add `embeddings_info` (if persisted per resume):
  - `full_resume_embedding_id`, `chunk_embeddings` list with `chunk_id`, `start_char`, `end_char`, `embedding_vector_id` (or stored inline in vector DB metadata).

- Add `last_updated` timestamp.

---

## 7. Parsing & normalization recommendations

- Keep LLM-driven structured parsing (`CVParsed`) for primary extraction but complement it with deterministic normalization pipelines:
  - Normalize skills using an expanded `skills_map` and fuzzy matching (rapidfuzz) against a controlled vocabulary.
  - Normalize job titles into canonical titles/taxonomy (a simple mapping or lightweight ML model can be used later).
  - Normalize dates with `dateparser` to ISO format and compute durations.
- Add a deduplication step after parsing that produces `candidate_id` and merges repeated records by email/phone/name fuzzy match.
- Persist provenance and parser metadata so changes/re-parses are auditable.

---

## 8. Immediate next steps (technical tasks)

1. Expand `CVParsed` incrementally to include `candidate_id`, `source`, and `parsing_metadata`.
2. Implement `backend/parse/normalize.py` to:
   - Normalize emails/phones, compute `candidate_id` (UUID5 or hash), normalize dates, compute `years_experience`, and map skills via `skills_map.json` + fuzzy matching.
3. Enhance ingestion to store chunk-level offsets in vector store metadata (`start_char`, `end_char`, `chunk_text`) to enable precise citations in RAG responses.
4. Expand `skills_map.json` and provide tooling to bulk-import or extend the taxonomy from CSV.
5. Add unit tests to validate the schema round-trip: parsed LLM output -> normalization -> canonical candidate record.

---

## 9. Backwards compatibility

- Existing stored parsed JSON files and metadata will remain readable if new fields are optional with sensible defaults.
- When adding `candidate_id` generation, prefer not to mutate existing parsed files in-place; instead, compute `candidate_id` at ingestion time and store canonical records in a separate `candidates/` store.

---

## 10. Quick checklist for Task 1 completion

- [x] Reviewed `CVParsed` and nested models.
- [x] Reviewed parsing utilities (`parse_utils.py`, `parse_utils_minimal.py`).
- [x] Reviewed `skills_map.json` contents and limitations.
- [x] Mapped gaps and recommended schema additions.

---

If you want, I'll now: (pick one)

- Implement the small `parsing_metadata` and `candidate_id` additions to `data_schemas/cv.py` and update `ingest_simplified.py` to populate `candidate_id` at ingestion; or
- Start implementing `.docx` / `.doc` ingestion and update `load_documents`; or
- Build `backend/parse/normalize.py` to canonicalize skills, compute `candidate_id`, and calculate `years_experience`.

Tell me which you prefer and I'll proceed.
