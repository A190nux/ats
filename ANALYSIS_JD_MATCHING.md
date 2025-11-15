# JD Matching & Ranking Feature - Detailed Analysis

## Executive Summary

The ATS system now has a fully functional RAG pipeline for CV retrieval and question answering. The next major feature is **JD (Job Description) Matching & Ranking**, which will allow recruiters to:

1. **Upload/paste a JD** into the system
2. **Score all candidates** against the JD using configurable criteria
3. **Generate a ranked shortlist** with explanations of why each candidate matches or doesn't match
4. **Export results** as CSV or JSON for downstream use

---

## Current System Architecture

### ✅ Completed Components

| Layer | Status | Details |
|-------|--------|---------|
| **Data** | ✅ Ready | 14 CVs parsed and normalized in `CVParsed` schema |
| **Embeddings** | ✅ Ready | 1024-dim Qwen embeddings for chunks + resume-level |
| **Vector DB** | ✅ Ready | Chroma with dual collections (chunks + resumes) |
| **Retrieval** | ✅ Ready | Resume-first pipeline with optional reranking |
| **LLM** | ✅ Ready | Ollama phi4-mini with 120s RAG timeout |
| **GPU Mgmt** | ✅ Ready | Cross-process locking prevents OOM |
| **API** | ✅ Ready | FastAPI with 10+ endpoints |
| **UI** | ✅ Ready | Streamlit with interactive chat |

### 📊 Data Inventory

```
CVParsed Schema (fully normalized):
├── name: str (optional)
├── contact: CandidateContact
│   ├── email
│   ├── phone
│   └── linkedin
├── professional_summary: str
├── education: List[EducationEntry]
│   ├── institution
│   ├── degree
│   ├── major
│   └── graduation_year
├── experience: List[ExperienceEntry]
│   ├── job_title
│   ├── company
│   ├── start_date
│   ├── end_date
│   └── description
├── skills: List[str] (normalized via skills_map.json)
├── certifications: List[CertificationEntry]
│   ├── name
│   ├── issuer
│   └── year
└── languages: List[str]

Skills Mapping (23 entries):
- Deep Learning: TensorFlow, PyTorch, YOLO → normalized
- Data Processing: Pandas, NumPy, Spark
- Database: SQL
- Infrastructure: Docker, Kubernetes, AWS
- Web: Flask, FastAPI
- Version Control: Git
```

---

## Gap Analysis: What's Missing for JD Matching

### 1. **JD Parsing & Schema** ❌
**Goal**: Parse unstructured JD text into structured format matching CV schema

**Current State**: None
- No JD parsing module
- No JDParsed schema
- No LLM integration for JD extraction

**Requirements**:
- Accept JD as: (a) uploaded file (PDF, DOCX, TXT), (b) pasted text
- Extract: title, skills (must-have/nice-to-have), education, experience, responsibilities
- Normalize skills against `skills_map.json`
- Store parsed JD for reuse

**Approach**: Use Ollama (phi4-mini) with structured prompt to extract and normalize JD elements

---

### 2. **Scoring Rubric Engine** ❌
**Goal**: Flexible, configurable scoring system for candidate-JD matching

**Current State**: None
- No rubric model
- No scoring algorithm
- No configurable weights

**Requirements**:
- Configurable weights for: must-have skills, nice-to-have skills, education, years of experience
- Support multiple rubric presets (e.g., "junior", "mid-level", "senior")
- Generate numeric score (0-100) and qualitative reasoning
- Fast evaluation (no LLM calls during scoring)

**Approach**: 
```python
ScoringRubric:
  skill_must_have_weight: 3.0          # each must-have skill match = 3 pts
  skill_nice_to_have_weight: 1.0       # each nice-to-have skill match = 1 pt
  education_exact_match: 2.0           # exact degree/major match = 2 pts
  education_related: 1.0               # related field = 1 pt
  years_of_exp_per_year: 0.5 pt       # 0.5 pts per year beyond threshold
  years_of_exp_threshold: 3            # minimum years required
  max_score: 100                       # normalization ceiling
```

---

### 3. **Candidate Scoring Logic** ❌
**Goal**: For each candidate, compute relevance score and reasoning

**Current State**: None
- No matching algorithm
- No reasoning generation
- No ranking

**Requirements**:
- For each candidate CV:
  * Extract skills, education, experience years
  * Match against JD must-have/nice-to-have skills
  * Assess education fit (degree type, major field)
  * Calculate years of experience
  * Generate composite score (0-100)
  * Generate reasoning: "Matched 8/10 must-have skills (Python, FastAPI, Docker...), BS CS, 5 years exp"
- Sort candidates by score descending
- Return top N candidates with reasoning

**Approach**: Rule-based (no LLM needed for scoring; deterministic, fast)

---

### 4. **Storage Layer** ❌
**Goal**: Persist JDs and scoring results for audit trail and future use

**Current State**: None
- No JD storage
- No result caching
- No job tracking

**Requirements**:
- Store parsed JD with metadata (created_at, job_id, source file)
- Store ranking results (timestamp, scores, candidate order)
- Support retrieval of historical results
- Enable comparative analysis across multiple JDs

**Approach**: JSON files in `backend/data/jds/` (simple, no DB dependency)
```
backend/data/jds/
├── job-001/
│   ├── jd_parsed.json        # parsed JD
│   ├── jd_original.txt       # original text
│   ├── ranking_2024-12-15.json
│   └── metadata.json
└── job-002/
    └── ...
```

---

### 5. **API Endpoints** ❌
**Goal**: HTTP interface for JD management and ranking

**Current State**: Exists but incomplete
- Missing JD-specific endpoints
- No ranking endpoint

**New Endpoints Needed**:
```
POST /jd/parse
  Request: { "jd_text": "...", "jd_file": "..." }
  Response: { "jd_id": "...", "jd_parsed": {...} }

POST /jd/{jd_id}/rank
  Request: { "rubric": {...} }  # optional, use default
  Response: { "rankings": [...] }

GET /jd/{jd_id}
  Response: { "jd_parsed": {...}, "metadata": {...} }

DELETE /jd/{jd_id}
  Response: { "status": "deleted" }

GET /jd/list
  Response: { "jds": [...] }
```

---

### 6. **Streamlit UI Integration** ❌
**Goal**: Interactive interface for JD matching workflow

**Current State**: UI exists but no JD section

**New UI Components Needed**:
- **JD Input Tab**:
  * File upload (PDF, DOCX, TXT)
  * Text paste area
  * Parse button
  * Preview of parsed JD
  
- **Configuration Tab**:
  * Rubric selector (dropdown: default, junior, mid, senior)
  * Custom weight sliders
  * Skill filtering (must-have vs nice-to-have)
  
- **Results Tab**:
  * Ranked shortlist (table with scores)
  * Per-candidate detail:
    - Matched skills (highlighted)
    - Missing skills
    - Education alignment
    - Years of experience
    - Matched text snippets from CV
  * Export buttons (CSV, JSON)
  * Comparison view (side-by-side candidate comparison)

---

## Implementation Roadmap

### Phase 1: JD Parsing Module (2-3 hours)
**File**: `backend/parse/jd_parser.py`

```python
class JDParsed(BaseModel):
    """Structured JD data, mirrors CVParsed for consistency"""
    title: str
    department: Optional[str]
    location: Optional[str]
    company: Optional[str]
    
    # Skills categorization
    must_have_skills: List[str]
    nice_to_have_skills: List[str]
    
    # Education & experience expectations
    preferred_education: Optional[str]
    years_of_experience: Optional[int]
    
    # Additional metadata
    salary_range: Optional[str]
    description: Optional[str]
    responsibilities: List[str]
    benefits: Optional[str]

def parse_jd_text(jd_text: str) -> JDParsed:
    """Use Ollama to parse JD text into structured format"""
    # Call Ollama with structured prompt
    # Extract: title, skills, education, experience, etc.
    # Normalize skills against skills_map.json
    # Return JDParsed object

def parse_jd_file(file_path: str) -> str:
    """Extract text from PDF/DOCX/TXT"""
    # Handle multiple file formats
    # Return raw text for parse_jd_text()
```

**Testing**: 
- Unit tests for skill normalization
- Integration test with sample JD

---

### Phase 2: Scoring Engine (2-3 hours)
**File**: `backend/parse/jd_matcher.py`

```python
class ScoringRubric(BaseModel):
    """Configurable scoring weights"""
    skill_must_have_weight: float = 3.0
    skill_nice_to_have_weight: float = 1.0
    education_exact_match: float = 2.0
    education_related: float = 1.0
    years_of_exp_per_year: float = 0.5
    years_of_exp_threshold: int = 3
    max_score: float = 100.0

class CandidateScore(BaseModel):
    """Result of matching one candidate to a JD"""
    candidate_id: str
    candidate_name: str
    score: float  # 0-100
    reasoning: str  # "Matched 8/10 must-have skills..."
    matched_skills: List[str]
    missing_skills: List[str]
    years_of_experience: int
    education_fit: str  # "exact match", "related field", "no match"

def match_candidate_to_jd(
    cv: CVParsed, 
    jd: JDParsed, 
    rubric: ScoringRubric
) -> CandidateScore:
    """Score one candidate against JD"""
    # 1. Extract skills from CV (normalized)
    # 2. Count must-have skill matches
    # 3. Count nice-to-have skill matches
    # 4. Check education level/field
    # 5. Calculate years of experience
    # 6. Apply rubric weights
    # 7. Normalize to 0-100
    # 8. Generate reasoning
    # Return CandidateScore

def rank_all_candidates(
    cvs: List[CVParsed], 
    jd: JDParsed, 
    rubric: ScoringRubric
) -> List[CandidateScore]:
    """Score all candidates and sort by score descending"""
    pass
```

**Key Algorithms**:
- **Skill Matching**: Exact match + partial match (stemming/lemmatization)
- **Education Fit**: Degree type comparison (BS/MS/PhD), major field relevance
- **Experience Calc**: Parse dates from CV, compute years since earliest role
- **Score Normalization**: (total_points / max_points) * 100

---

### Phase 3: API Endpoints (1-2 hours)
**File**: `backend/api.py` (additions)

```python
@app.post("/jd/parse")
async def api_parse_jd(
    jd_text: Optional[str] = None,
    jd_file: Optional[UploadFile] = None
) -> Dict:
    """Parse JD and store"""
    # Extract text from file or use pasted text
    # Call parse_jd_text()
    # Store parsed JD
    # Return { jd_id, jd_parsed, metadata }

@app.post("/jd/{jd_id}/rank")
async def api_rank_candidates(
    jd_id: str,
    rubric: Optional[ScoringRubric] = None
) -> Dict:
    """Rank all candidates against JD"""
    # Load JD by jd_id
    # Load all CVs from Chroma or parsed files
    # Apply rubric (default if not provided)
    # Sort candidates by score
    # Return { jd_id, rankings: [...] }

@app.get("/jd/{jd_id}")
async def api_get_jd(jd_id: str) -> Dict:
    """Retrieve stored JD"""

@app.delete("/jd/{jd_id}")
async def api_delete_jd(jd_id: str) -> Dict:
    """Delete JD"""

@app.get("/jd/list")
async def api_list_jds() -> Dict:
    """List all stored JDs"""
```

---

### Phase 4: Streamlit UI Integration (1-2 hours)
**File**: `web/app.py` (additions to `render_jd_matching_section()`)

```python
def render_jd_matching_section():
    """New tab for JD matching workflow"""
    
    # Tab 1: JD Input
    st.subheader("📋 Upload Job Description")
    jd_input_method = st.radio("Input method", ["Paste Text", "Upload File"])
    
    if jd_input_method == "Paste Text":
        jd_text = st.text_area("Paste JD here", height=200)
    else:
        jd_file = st.file_uploader("Upload JD (PDF, DOCX, TXT)")
    
    if st.button("Parse JD"):
        # Call API /jd/parse
        jd_id = response["jd_id"]
        st.session_state.current_jd_id = jd_id
        st.success(f"JD parsed: {jd_id}")
        st.write(response["jd_parsed"])
    
    # Tab 2: Configuration
    st.subheader("⚙️ Scoring Configuration")
    rubric_preset = st.selectbox("Rubric preset", ["Default", "Junior", "Mid-level", "Senior"])
    
    col1, col2 = st.columns(2)
    with col1:
        must_have_weight = st.slider("Must-have skill weight", 0.1, 5.0, 3.0)
    with col2:
        nice_to_have_weight = st.slider("Nice-to-have skill weight", 0.1, 2.0, 1.0)
    
    # Tab 3: Results
    st.subheader("🏆 Ranked Candidates")
    if st.button("Rank Candidates"):
        # Call API /jd/{jd_id}/rank with custom rubric
        rankings = response["rankings"]
        
        # Display as table
        df = pd.DataFrame([
            {
                "Rank": i+1,
                "Candidate": r["candidate_name"],
                "Score": f"{r['score']:.1f}",
                "Matched Skills": ", ".join(r["matched_skills"][:3]) + "...",
                "Years Exp": r["years_of_experience"]
            }
            for i, r in enumerate(rankings[:10])
        ])
        st.dataframe(df)
        
        # Expandable details per candidate
        for rank, r in enumerate(rankings[:5], 1):
            with st.expander(f"#{rank} {r['candidate_name']} ({r['score']:.1f})"):
                st.write(f"**Reasoning**: {r['reasoning']}")
                st.write(f"**Matched Skills**: {', '.join(r['matched_skills'])}")
                st.write(f"**Missing Skills**: {', '.join(r['missing_skills'])}")
    
    # Export
    if st.button("Export Results (CSV)"):
        # Export to CSV
        pass
```

---

## Decision Matrix

| Decision | Option A | Option B | Option C | **Choice** |
|----------|----------|----------|----------|-----------|
| **JD Parsing** | LLM (phi4-mini) | Regex/heuristics | Hybrid | **LLM** — flexible, handles varied formats |
| **Scoring** | Rule-based | LLM-based | Hybrid | **Rule-based** — fast, deterministic |
| **Storage** | JSON files | SQLite | Chroma embeddings | **JSON files** — simple, no DB |
| **UI Location** | New tab (existing app) | Separate Streamlit page | Modal overlay | **New tab** — keeps context |
| **Skill Matching** | Exact only | Partial (stem) | Fuzzy (leven) | **Exact + fuzzy** — balanced |

---

## Success Criteria

- ✅ JD can be uploaded (PDF, DOCX, TXT) or pasted as text
- ✅ Parsed JD extracted and normalized (skills against skills_map.json)
- ✅ All 14 candidates scored against JD in <5 seconds
- ✅ Ranked shortlist displayed with:
  * Score (0-100)
  * Matched skills (highlighted)
  * Missing skills
  * Years of experience
  * Education alignment
  * Reasoning (e.g., "Matched 8/10 must-haves...")
- ✅ Configurable scoring rubric (presets + custom weights)
- ✅ Export results (CSV, JSON)
- ✅ Historical JD storage and retrieval
- ✅ Streamlit UI with full workflow (input → config → results → export)

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|-----------|
| JD parsing LLM hallucination | Medium | Medium | Validation rules, fallback to manual correction |
| Skill normalization misses | Medium | Medium | Manual skills_map.json expansion |
| Scoring rubric too rigid | Low | Low | Support custom rubric via API |
| Performance (14 CVs scoring) | Low | Low | Rule-based (no LLM); should be <1s total |
| File format support (PDF parsing) | Medium | Medium | Use `pdfplumber` or `pypdf` libraries |

---

## File Structure (After Implementation)

```
backend/
├── parse/
│   ├── jd_parser.py           # NEW: JD parsing & schema
│   ├── jd_matcher.py          # NEW: Scoring engine
│   ├── retrieval.py           # EXISTING
│   ├── rag.py                 # EXISTING
│   └── ...
├── data/
│   └── jds/                   # NEW: JD storage
│       ├── job-001/
│       │   ├── jd_parsed.json
│       │   ├── jd_original.txt
│       │   └── metadata.json
│       └── ...
├── api.py                      # MODIFIED: Add /jd/* endpoints
└── gpu_lock.py                # EXISTING

web/
└── app.py                      # MODIFIED: Add JD matching tab

data_schemas/
├── cv.py                       # EXISTING
└── jd.py                       # NEW: JDParsed schema (optional, can be in jd_parser.py)
```

---

## Implementation Sequence

1. **Create `backend/parse/jd_parser.py`** with JDParsed schema and parse_jd_text()
2. **Create `backend/parse/jd_matcher.py`** with ScoringRubric and match_candidate_to_jd()
3. **Add API endpoints** to `backend/api.py` (/jd/parse, /jd/{id}/rank, etc.)
4. **Create `backend/data/jds/`** directory for storage
5. **Add Streamlit UI** to `web/app.py` with new tab for JD matching
6. **Test end-to-end** with sample JD
7. **Optimize** if needed (caching, async scoring)

---

## Conclusion

The JD Matching feature builds directly on the existing RAG infrastructure. By reusing the normalized CVParsed schema and skills_map.json, we can quickly implement a rule-based scoring engine that's both fast and transparent.

**Next Step**: Confirm approach and begin Phase 1 (JD parsing module).

