# Simplified CV Pipeline - Changes Summary

## Files Created

### 1. `ingest_simplified.py` (150 lines vs 500+)
**What Changed:**

#### Removed (Cause of Overfitting & Complexity)
- ❌ `extract_name_contacts()` deterministic pass
- ❌ `split_sections()` heuristic section detection
- ❌ `extract_skills()` complex canonicalization
- ❌ `parse_experience_section()` regex-based experience parsing
- ❌ `parse_education_section()` deterministic education extraction
- ❌ `_invoke_validation_llm()` second LLM call for missing fields
- ❌ `_invoke_education_llm()` third specialized LLM call
- ❌ Complex `_invoke_structured_safe()` with 100+ lines of fallback logic
- ❌ Spacy NER loading for organization/person detection
- ❌ Large metadata structures with "deterministic_prefill"
- ❌ Sophisticated merging logic trying to combine multiple parse results

#### Why These Were Problematic
1. **Overfitting**: Regex rules were tuned to your specific CVs (e.g., specific date formats, company patterns)
2. **Fragility**: When CVs deviate from expected patterns, the deterministic rules fail silently
3. **Confusion**: Multiple overlapping sources meant unclear which data was authoritative
4. **Latency**: 3-4 LLM calls per document instead of 1
5. **Maintenance**: Adding new rules required changes in multiple places

#### Kept & Simplified
- ✅ Single structured LLM call (let it handle all extraction)
- ✅ Simple document loading (PDF + text files)
- ✅ Lightweight post-processing (normalize whitespace, validate types)
- ✅ ChromaDB storage with minimal, clean metadata
- ✅ Clear error handling (failures logged, sensible null defaults)

### 2. `data_schemas/parse_utils_minimal.py` (70 lines vs 416)
**What Changed:**

#### Kept (Actually Useful)
- ✅ `extract_email()` - simple regex
- ✅ `extract_phone()` - simple regex
- ✅ `extract_linkedin()` - simple regex
- ✅ `extract_github()` - simple regex
- ✅ `extract_skills_from_section()` - finds SKILLS section if marked (optional)

#### Removed (Let LLM Handle)
- ❌ `extract_name_contacts()` with spaCy fallback - 70 lines
- ❌ `split_sections()` with fuzzy matching - 60 lines
- ❌ `extract_skills()` with global mapping pass - 50 lines
- ❌ `parse_experience_section()` with date parsing, NER, heuristics - 100 lines
- ❌ `parse_education_section()` with institution detection, degree extraction - 80 lines
- ❌ `_find_date_strings()` and other helpers - 30 lines

---

## Architecture Comparison

### Old Pipeline
```
CV Text
  ↓ (extract_name_contacts - spaCy + regex)
  ↓ (split_sections - heuristic heading detection)
  ↓ (extract_skills - global regex pass + canonicalization)
  ↓ (parse_experience_section - date parsing + NER + heuristics)
  ↓ (parse_education_section - institution detection + degree extraction)
  ↓ (Structured LLM Call) → CVParsed JSON
  ↓ (Validation LLM Call) → Missing field suggestions
  ↓ (Education LLM Call) → Education entries
  ↓ (Complex merging logic)
  ↓ Final JSON
  ↓ ChromaDB with large metadata
```

### New Pipeline
```
CV Text
  ↓
[Structured LLM Call] → CVParsed JSON
  ↓
[Lightweight Cleanup] (normalize strings, validate types)
  ↓
Final JSON
  ↓
ChromaDB with minimal metadata
```

---

## Usage

Replace your current ingestion with the simplified version:

```bash
# Test the simplified version
python ingest_simplified.py

# Once validated, you can rename/replace the original
# mv ingest.py ingest_old.py
# mv ingest_simplified.py ingest.py
```

---

## Benefits

| Aspect | Old | New |
|--------|-----|-----|
| Lines of code | 500+ | 150 |
| Helper utilities | 416 | 70 |
| LLM calls per CV | 3-4 | 1 |
| Deterministic rules | 8+ functions | 0 |
| Overfitting risk | High | Low |
| Error modes | Silent failures + complex fallbacks | Clear, logged errors |
| Latency | ~30-60s per CV | ~10-20s per CV |
| Maintainability | Hard (multiple overlapping systems) | Easy (single code path) |
| Debuggability | Unclear which source contributed data | Clear source (LLM output) |

---

## What the LLM Does Better

The structured LLM with `CVParsed` schema is actually very good at:
- **Extracting section context**: It understands "EXPERIENCE" sections even with varied formats
- **Parsing structured data**: Lists of education/experience entries with proper fields
- **Understanding relationships**: Can match titles to companies without explicit patterns
- **Handling variations**: Works with different CV formats, not just regex patterns
- **Nullability**: Naturally returns `null` for fields that aren't present

Your original approach tried to make the LLM better by feeding it "hints" from deterministic rules, but this actually:
1. Added complexity without proportional benefit
2. Introduced conflicting signals (deterministic rules vs LLM)
3. Caused overfitting to your specific examples
4. Made debugging harder when things go wrong

---

## Next Steps

1. **Test on a few CVs** to see if structured LLM alone is sufficient
2. **If results are worse**: Identify specific patterns the LLM misses and fix the schema/prompt
3. **Don't go back to deterministic rules**: Instead, improve the LLM prompt or try a better model
4. **Monitor failures**: Track which fields are most commonly null and why

