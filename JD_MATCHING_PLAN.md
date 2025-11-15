"""
JD MATCHING & RANKING - ANALYSIS & IMPLEMENTATION PLAN

=== CURRENT STATE ===

✓ Infrastructure Ready:
- CV parsing pipeline with normalized data (skills, education, experience)
- Resume-level embeddings in Chroma (cv_collection_resumes)
- Chunk-level embeddings in Chroma (cv_collection)
- Semantic retrieval module (search_resumes_v2) with optional reranking
- FastAPI endpoints for search and RAG
- Streamlit UI for interactive queries
- GPU locking to prevent OOM during concurrent embedding/LLM ops

✓ Data Available:
- CVParsed schema: name, contact, professional_summary, education, experience, skills, certifications, languages
- 14 CV files parsed (in cv_uploads/parsed/)
- Normalized skills mapping (skills_map.json)
- Candidate embeddings indexed in Chroma

=== GAP ANALYSIS ===

Missing for JD Matching:
1. JD Parsing Module
   - Parse/extract JD text (upload or paste)
   - Structure JD into: title, department, location, must-have skills, nice-to-have skills, education, experience, salary range, etc.
   - Normalize JD skills against skills_map.json for consistency

2. Scoring Rubric Engine
   - Configurable skill weights (must-have vs nice-to-have)
   - Education level matching (degree/major alignment)
   - Experience year thresholds
   - Keyword/context matching
   - Composite scoring algorithm

3. Candidate Ranking Logic
   - Score all candidates against JD
   - Generate matching explanations (matched skills, gaps, years of exp, etc.)
   - Sort and return ranked shortlist with reasoning

4. API Endpoints
   - POST /jd/parse — upload/paste JD and parse it
   - POST /jd/rank — compute scores and rank candidates against JD
   - GET /jd/{jd_id} — retrieve stored JD
   - DELETE /jd/{jd_id} — delete JD

5. Storage
   - Persist parsed JDs (database or JSON files)
   - Store JD embeddings (for future reuse/analytics)

6. Streamlit UI Integration
   - JD upload/paste form
   - Ranking results display (shortlist with scores and reasoning)
   - Export shortlist (CSV, JSON)

=== PROPOSED IMPLEMENTATION APPROACH ===

Phase 1: JD Parsing & Storage
- Create backend/parse/jd_parser.py with:
  - JDParsed Pydantic schema (mirrors CVParsed structure)
  - parse_jd_text() function using LLM or heuristics
  - Storage layer (simple JSON or database)

Phase 2: Scoring Engine
- Create backend/parse/jd_matcher.py with:
  - Scoring rubric configuration (JSON or Pydantic model)
  - match_candidate_to_jd() function:
    * Extract skills from CV and JD
    * Compute skill overlap (must-have, nice-to-have)
    * Calculate education fit
    * Assess years of experience
    * Generate matching reasoning
  - score_all_candidates(jd) function

Phase 3: API Endpoints
- Add to backend/api.py:
  - POST /jd/parse
  - POST /jd/rank
  - GET /jd/{jd_id}
  - DELETE /jd/{jd_id}

Phase 4: Streamlit UI
- Add tab to web/app.py:
  - JD input (paste/upload)
  - Ranking results (table with scores, matched skills, gaps)
  - Export functionality

=== IMPLEMENTATION DETAILS ===

1. JD Schema (backend/parse/jd_parser.py)
   - title, department, location, salary_range
   - must_have_skills, nice_to_have_skills
   - preferred_education (degree, major)
   - years_of_experience (min, preferred)
   - description, responsibilities, benefits

2. Scoring Rubric Config (JSON)
   {
     "skill_weight_must_have": 3.0,
     "skill_weight_nice_to_have": 1.0,
     "education_exact_match": 2.0,
     "education_related_field": 1.0,
     "years_of_exp_threshold": 3,
     "years_per_point": 0.5,
     "max_score": 100
   }

3. Matching Logic
   - For each candidate:
     * Extract their skills (normalized)
     * Count must-have skill matches (with weights)
     * Count nice-to-have skill matches
     * Check education level/field
     * Calculate years of experience
     * Normalize to 0-100 score
     * Generate reasoning string (e.g., "Matched 8/10 must-have skills, 3+ years exp, BS Computer Science")

4. API Request/Response
   POST /jd/rank
   Request:
   {
     "jd_text": "...",  # paste
     "or jd_file": "...",  # upload
     "rubric": { ... }  # optional, use default if not provided
   }
   Response:
   {
     "jd_id": "...",
     "jd_parsed": { ... },
     "rankings": [
       {
         "candidate_id": "...",
         "candidate_name": "...",
         "score": 87.5,
         "reasoning": "Matched 8/10 must-have skills...",
         "matched_skills": ["Python", "FastAPI", ...],
         "missing_skills": ["Docker", ...],
         "years_of_experience": 5
       },
       ...
     ]
   }

=== DECISION POINTS ===

1. JD Parsing Approach
   - Option A: Use LLM to parse JD into structured format (more flexible, slower)
   - Option B: Use heuristics/regex to extract sections (faster, less flexible)
   - Recommendation: Start with Option A (LLM) since we have Ollama available

2. Storage
   - Option A: JSON files in backend/data/jds/
   - Option B: SQLite database
   - Option C: Chroma embeddings (future: semantic JD search)
   - Recommendation: Start with Option A (simple, no DB dependency)

3. Scoring
   - Option A: Rule-based (configurable rubric, deterministic)
   - Option B: LLM-based (more semantic, slower)
   - Option C: Hybrid (rules + semantic)
   - Recommendation: Start with Option A; Option C can follow

4. UI Integration
   - Option A: New tab in existing Streamlit app
   - Option B: Separate Streamlit page
   - Recommendation: Option A (keep in main app)

=== NEXT STEPS ===

1. ✓ Analysis complete (this document)
2. Create JD parser module (backend/parse/jd_parser.py)
3. Create JD matcher module (backend/parse/jd_matcher.py)
4. Add API endpoints (/jd/parse, /jd/rank, etc.)
5. Integrate into Streamlit UI
6. Test end-to-end with sample JD

=== ESTIMATED EFFORT ===
- JD Parser: ~1-2 hours
- JD Matcher: ~2-3 hours
- API Endpoints: ~1 hour
- Streamlit UI: ~1-2 hours
- Testing: ~1 hour
- Total: ~6-9 hours

"""
