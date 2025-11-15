"""
JD (Job Description) Parsing Module

Extracts and normalizes job description data into structured format,
mirroring the CVParsed schema for consistency and comparability.
"""

import json
import os
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# JD Schema (mirrors CVParsed for consistency)
# ============================================================================

class JDSkillsBreakdown(BaseModel):
    """Categorized skills from JD."""
    must_have: List[str] = Field(
        default_factory=list,
        description="Skills explicitly required for the role."
    )
    nice_to_have: List[str] = Field(
        default_factory=list,
        description="Skills that are beneficial but not required."
    )


class JDEducationRequirements(BaseModel):
    """Education requirements from JD."""
    degree_level: Optional[str] = Field(
        None,
        description="Degree level required (e.g., 'Bachelor', 'Master', 'Ph.D.')."
    )
    fields_of_study: List[str] = Field(
        default_factory=list,
        description="Preferred fields of study (e.g., 'Computer Science', 'Engineering')."
    )


class JDExperienceRequirements(BaseModel):
    """Experience requirements from JD."""
    minimum_years: Optional[int] = Field(
        None,
        description="Minimum years of experience required."
    )
    preferred_years: Optional[int] = Field(
        None,
        description="Preferred years of experience."
    )


class JDParsed(BaseModel):
    """
    Structured data extracted from a single JD document.
    Mirrors CVParsed schema for easy comparison during candidate matching.
    """
    
    # Role information
    job_title: str = Field(
        description="The position title (e.g., 'Senior Software Engineer')."
    )
    company: Optional[str] = Field(
        None,
        description="Company name if provided in JD."
    )
    department: Optional[str] = Field(
        None,
        description="Department or team (e.g., 'Backend', 'Data Science')."
    )
    location: Optional[str] = Field(
        None,
        description="Job location or remote status."
    )
    
    # Skills breakdown
    skills: JDSkillsBreakdown = Field(
        default_factory=JDSkillsBreakdown,
        description="Categorized required and preferred skills."
    )
    
    # Education and experience
    education: JDEducationRequirements = Field(
        default_factory=JDEducationRequirements,
        description="Education requirements."
    )
    experience: JDExperienceRequirements = Field(
        default_factory=JDExperienceRequirements,
        description="Years of experience requirements."
    )
    
    # Additional metadata
    description: Optional[str] = Field(
        None,
        description="Full job description text."
    )
    responsibilities: List[str] = Field(
        default_factory=list,
        description="Key responsibilities extracted from JD."
    )
    benefits: Optional[str] = Field(
        None,
        description="Benefits and perks mentioned in JD."
    )
    salary_range: Optional[str] = Field(
        None,
        description="Salary range if provided (e.g., '$100k-$150k')."
    )
    
    # Metadata
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when JD was parsed."
    )
    source_file: Optional[str] = Field(
        None,
        description="Original filename if uploaded."
    )


# ============================================================================
# File Extraction (handles multiple formats)
# ============================================================================

def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from various file formats (TXT, PDF, DOCX).
    
    Args:
        file_path: Path to the file to extract text from
        
    Returns:
        Extracted text content
        
    Raises:
        ValueError: If file format not supported or extraction fails
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise ValueError(f"File not found: {file_path}")
    
    suffix = file_path.suffix.lower()
    
    # TXT files (simplest case)
    if suffix == ".txt":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            raise ValueError(f"Failed to read TXT file: {e}")
    
    # PDF files
    elif suffix == ".pdf":
        try:
            import pdfplumber
            text = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text.append(page_text)
            return "\n".join(text)
        except ImportError:
            raise ValueError("PDF support requires 'pdfplumber'. Install with: pip install pdfplumber")
        except Exception as e:
            raise ValueError(f"Failed to read PDF file: {e}")
    
    # DOCX files
    elif suffix == ".docx":
        try:
            from docx import Document
            doc = Document(file_path)
            text = [para.text for para in doc.paragraphs]
            return "\n".join(text)
        except ImportError:
            raise ValueError("DOCX support requires 'python-docx'. Install with: pip install python-docx")
        except Exception as e:
            raise ValueError(f"Failed to read DOCX file: {e}")
    
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Supported: .txt, .pdf, .docx")


# ============================================================================
# Skills Normalization (load from skills_map.json)
# ============================================================================

def load_skills_map() -> Dict[str, str]:
    """
    Load skills mapping from skills_map.json.
    
    Returns:
        Dictionary mapping skill aliases to canonical skill names
    """
    try:
        skills_map_path = Path(__file__).parent.parent.parent / "data_schemas" / "skills_map.json"
        if not skills_map_path.exists():
            logger.warning(f"Skills map not found at {skills_map_path}. Using empty map.")
            return {}
        
        with open(skills_map_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load skills map: {e}")
        return {}


def normalize_skill(skill: str, skills_map: Dict[str, str]) -> str:
    """
    Normalize a single skill using the skills map.
    
    Args:
        skill: Raw skill string (e.g., "fast api")
        skills_map: Dictionary of skill aliases to canonical names
        
    Returns:
        Normalized skill name (e.g., "FastAPI")
    """
    if not skill or not isinstance(skill, str):
        return ""
    
    # Clean and lowercase for lookup
    skill_lower = skill.strip().lower()
    
    if not skill_lower:
        return ""
    
    # Direct match
    if skill_lower in skills_map:
        return skills_map[skill_lower]
    
    # Partial/fuzzy match (simple heuristic)
    # For each skill in the map, check if it contains this substring
    for key, canonical in skills_map.items():
        if key in skill_lower or skill_lower in key:
            return canonical
    
    # No match found, return original (cleaned)
    return skill.strip()


def normalize_skills(skills: List[Any], skills_map: Dict[str, str]) -> List[str]:
    """
    Normalize and deduplicate a list of skills.
    
    Args:
        skills: List of skill items (may contain None or non-string values)
        skills_map: Dictionary of skill aliases to canonical names
        
    Returns:
        Deduplicated list of normalized skills
    """
    if not skills:
        return []
    
    # Filter out None and non-string values
    valid_skills = [s for s in skills if s and isinstance(s, str)]
    
    normalized = set()
    for skill in valid_skills:
        norm_skill = normalize_skill(skill, skills_map)
        if norm_skill:
            normalized.add(norm_skill)
    
    return sorted(list(normalized))


# ============================================================================
# LLM-based JD Parsing (using Ollama)
# ============================================================================

def extract_json_from_response(llm_output: str) -> Dict[str, Any]:
    """
    Extract JSON from LLM response, handling markdown wrapping.
    
    Args:
        llm_output: Raw LLM response text
        
    Returns:
        Parsed JSON as dictionary
        
    Raises:
        ValueError: If no valid JSON found
    """
    # Try to find JSON block (with or without markdown)
    # First, try markdown code block
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', llm_output, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try bare JSON
        json_start = llm_output.find("{")
        json_end = llm_output.rfind("}") + 1
        
        if json_start == -1 or json_end <= json_start:
            raise ValueError("No JSON found in LLM response")
        
        json_str = llm_output[json_start:json_end]
    
    return json.loads(json_str)


def parse_jd_with_llm(jd_text: str, model: str = "phi4-mini:latest", timeout: int = 120) -> JDParsed:
    """
    Use Ollama LLM to parse JD text into structured format.
    
    Args:
        jd_text: Raw JD text to parse
        model: Ollama model to use
        timeout: Timeout in seconds for LLM call
        
    Returns:
        JDParsed object with structured JD data
    """
    try:
        from ollama import Client
    except ImportError:
        raise ImportError("Ollama client required. Install with: pip install ollama")
    
    # Truncate if too long (to avoid token limits)
    max_chars = 8000
    if len(jd_text) > max_chars:
        jd_text = jd_text[:max_chars]
        logger.warning(f"JD text truncated to {max_chars} characters")
    
    # Structured extraction prompt
    prompt = f"""You are an expert HR analyst. Extract and structure the following Job Description into a JSON object.

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON (can be wrapped in ```json ... ``` if needed)
2. For arrays of skills, return individual strings: ["skill1", "skill2"]
3. Extract ONLY what is explicitly stated; don't invent requirements
4. For numbers, use actual integers or null if not found
5. Filter out None/null values from all arrays
6. Keep descriptions concise

Required JSON structure:
{{
  "job_title": "title here",
  "company": "company or null",
  "department": "dept or null",
  "location": "location or null",
  "skills_must_have": ["skill1", "skill2"],
  "skills_nice_to_have": ["skill1", "skill2"],
  "education_degree_level": "Bachelor or null",
  "education_fields_of_study": ["field1", "field2"],
  "experience_minimum_years": 5 or null,
  "experience_preferred_years": 7 or null,
  "responsibilities": ["resp1", "resp2"],
  "benefits": "benefits or null",
  "salary_range": "range or null"
}}

Job Description:
{jd_text}"""
    
    try:
        client = Client(host="http://localhost:11434")
        response = client.generate(
            model=model,
            prompt=prompt,
            stream=False
        )
        
        llm_output = response.get("response", "").strip()
        
        # Extract JSON from response
        extracted = extract_json_from_response(llm_output)
        
        # Load skills map for normalization
        skills_map = load_skills_map()
        
        # Normalize skills (filter out None values)
        must_have_skills = normalize_skills(
            extracted.get("skills_must_have", []),
            skills_map
        )
        nice_to_have_skills = normalize_skills(
            extracted.get("skills_nice_to_have", []),
            skills_map
        )
        
        # Filter education fields
        education_fields = extracted.get("education_fields_of_study", [])
        if education_fields:
            education_fields = [f for f in education_fields if f and isinstance(f, str)]
        
        # Filter responsibilities
        responsibilities = extracted.get("responsibilities", [])
        if responsibilities:
            responsibilities = [r for r in responsibilities if r and isinstance(r, str)][:5]
        
        # Build JDParsed object
        jd_parsed = JDParsed(
            job_title=str(extracted.get("job_title", "Unknown")).strip(),
            company=extracted.get("company"),
            department=extracted.get("department"),
            location=extracted.get("location"),
            skills=JDSkillsBreakdown(
                must_have=must_have_skills,
                nice_to_have=nice_to_have_skills
            ),
            education=JDEducationRequirements(
                degree_level=extracted.get("education_degree_level"),
                fields_of_study=education_fields
            ),
            experience=JDExperienceRequirements(
                minimum_years=extracted.get("experience_minimum_years"),
                preferred_years=extracted.get("experience_preferred_years")
            ),
            description=jd_text[:500] + "..." if len(jd_text) > 500 else jd_text,
            responsibilities=responsibilities,
            benefits=extracted.get("benefits"),
            salary_range=extracted.get("salary_range")
        )
        
        return jd_parsed
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON output: {e}\nOutput: {llm_output}")
        raise ValueError(f"LLM returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"LLM parsing failed: {e}")
        raise


# ============================================================================
# Public API
# ============================================================================

def parse_jd_text(jd_text: str, model: str = "phi4-mini:latest", timeout: int = 120) -> JDParsed:
    """
    Parse JD from plain text.
    
    Args:
        jd_text: Raw JD text
        model: Ollama model to use
        timeout: Timeout in seconds
        
    Returns:
        JDParsed object
    """
    if not jd_text or not jd_text.strip():
        raise ValueError("JD text cannot be empty")
    
    return parse_jd_with_llm(jd_text, model=model, timeout=timeout)


def parse_jd_file(file_path: str, model: str = "phi4-mini:latest", timeout: int = 120) -> JDParsed:
    """
    Parse JD from file (PDF, DOCX, or TXT).
    
    Args:
        file_path: Path to JD file
        model: Ollama model to use
        timeout: Timeout in seconds
        
    Returns:
        JDParsed object
    """
    # Extract text from file
    jd_text = extract_text_from_file(file_path)
    
    # Parse with LLM
    jd_parsed = parse_jd_with_llm(jd_text, model=model, timeout=timeout)
    
    # Add source file metadata
    jd_parsed.source_file = Path(file_path).name
    
    return jd_parsed


def save_jd_parsed(jd_parsed: JDParsed, output_dir: Path) -> Path:
    """
    Save parsed JD to JSON file.
    
    Args:
        jd_parsed: JDParsed object to save
        output_dir: Directory to save to
        
    Returns:
        Path to saved file
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename based on job title and timestamp
    safe_title = re.sub(r'[^\w\s-]', '', jd_parsed.job_title).strip()[:30]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_{timestamp}.jd.json"
    
    output_path = output_dir / filename
    
    # Serialize with custom JSON encoder for datetime
    output_path.write_text(jd_parsed.model_dump_json(indent=2))
    
    logger.info(f"Saved parsed JD to {output_path}")
    return output_path


def load_jd_parsed(json_path: Path) -> JDParsed:
    """
    Load a parsed JD from JSON file.
    
    Args:
        json_path: Path to JD JSON file
        
    Returns:
        JDParsed object
    """
    json_path = Path(json_path)
    data = json.loads(json_path.read_text())
    return JDParsed(**data)


def save_jd_with_original(jd_parsed: JDParsed, original_text: str, output_base_dir: Path) -> tuple[str, Path]:
    """
    Save both parsed JD (JSON) and original text to a uuid-keyed directory.
    
    Unified persistence helper to avoid duplication between jd_parser and api.
    Creates structure: `output_base_dir/{jd_id}/jd_parsed.json` + `jd_original.txt`
    
    Args:
        jd_parsed: JDParsed object to save
        original_text: Raw JD text that was parsed
        output_base_dir: Base directory (e.g., backend/data/jds)
        
    Returns:
        (jd_id, Path to jd directory)
    """
    import uuid
    jd_id = uuid.uuid4().hex
    dest = Path(output_base_dir) / jd_id
    dest.mkdir(parents=True, exist_ok=True)
    
    # Save parsed JSON using model_dump_json (handles datetime serialization)
    if hasattr(jd_parsed, 'model_dump_json'):
        json_str = jd_parsed.model_dump_json(indent=2)
    else:
        # Fallback: use model_dump and serialize with custom encoder
        jd_json = jd_parsed.model_dump() if hasattr(jd_parsed, 'model_dump') else jd_parsed.dict()
        json_str = json.dumps(jd_json, ensure_ascii=False, indent=2, default=str)
    
    (dest / "jd_parsed.json").write_text(json_str)
    (dest / "jd_original.txt").write_text(original_text or "")
    
    logger.info(f"Saved JD {jd_id} to {dest}")
    return jd_id, dest


def load_jd_with_original(jd_id: str, base_dir: Path) -> tuple[JDParsed, str]:
    """
    Load both parsed JD and original text from a jd_id directory.
    
    Args:
        jd_id: UUID of the JD (directory name)
        base_dir: Base directory (e.g., backend/data/jds)
        
    Returns:
        (JDParsed object, original text string)
    """
    jd_folder = Path(base_dir) / jd_id
    if not jd_folder.exists():
        raise FileNotFoundError(f"JD folder not found: {jd_folder}")
    
    parsed_json = json.loads((jd_folder / "jd_parsed.json").read_text(encoding='utf-8'))
    original = (jd_folder / "jd_original.txt").read_text(encoding='utf-8')
    
    jd_parsed = JDParsed(**parsed_json)
    return jd_parsed, original


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    # Example usage
    sample_jd = """
    Senior Python Developer
    
    We are looking for a Senior Python Developer to join our backend team.
    
    Requirements:
    - 5+ years of experience with Python
    - Strong knowledge of FastAPI or Django
    - Experience with PostgreSQL and Redis
    - Proficiency in Git and Docker
    - AWS or GCP experience preferred
    - Bachelor's degree in Computer Science or related field
    
    Responsibilities:
    - Design and build scalable backend APIs
    - Write clean, maintainable code
    - Collaborate with the data science team
    - Participate in code reviews
    
    Benefits:
    - Competitive salary ($150k-$180k)
    - Health insurance
    - Flexible remote work
    """
    
    print("Parsing sample JD...")
    try:
        jd_parsed = parse_jd_text(sample_jd)
        print("\nParsed JD:")
        print(jd_parsed.model_dump_json(indent=2))
    except Exception as e:
        print(f"Error: {e}")
