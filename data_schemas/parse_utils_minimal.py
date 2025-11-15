"""
Minimal utility functions for CV parsing.

Removed:
- Complex deterministic parsing (causes overfitting)
- Section splitting (let LLM handle it)
- Skill canonicalization (let LLM decide)
- spaCy NER for name/org extraction (LLM is better)
- Multiple date parsing strategies

Kept:
- Basic email/phone extraction (useful for validation)
- Simple skill extraction from SKILLS section (if present)
"""

import re
import json
from pathlib import Path
from typing import Optional, Dict


# Load optional skills mapping (simple canonicalization)
SKILLS_FILE = Path(__file__).parent / "skills_map.json"
if SKILLS_FILE.exists():
    try:
        with open(SKILLS_FILE, encoding='utf-8') as f:
            SKILLS_MAP = json.load(f)
    except Exception:
        SKILLS_MAP = {}
else:
    SKILLS_MAP = {}


def extract_email(text: str) -> Optional[str]:
    """Extract first email from text."""
    match = re.search(r"[\w\.-]+@[\w\.-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else None


def extract_phone(text: str) -> Optional[str]:
    """Extract first phone number from text."""
    match = re.search(r"(\+?\d[\d\s\-\(\)\.]{6,}\d)", text)
    if match:
        phone = match.group(0)
        # Clean up whitespace/separators
        phone = re.sub(r"[\s\-\.]+", " ", phone).strip()
        return phone
    return None


def extract_linkedin(text: str) -> Optional[str]:
    """Extract LinkedIn profile URL."""
    match = re.search(r"https?://(www\.)?linkedin\.com/[A-Za-z0-9\-_/]+", text, re.I)
    return match.group(0) if match else None


def extract_github(text: str) -> Optional[str]:
    """Extract GitHub profile URL."""
    match = re.search(r"https?://(www\.)?github\.com/[A-Za-z0-9\-_/]+", text, re.I)
    return match.group(0) if match else None


def extract_skills_from_section(text: str) -> list:
    """
    Extract skills from SKILLS section if clearly marked.
    
    This is optional - the LLM will also find skills in the full text.
    """
    skills = []

    # Look for obvious SKILLS section
    match = re.search(r"(?im)^skills?[\s:]+(.+?)(?=^[A-Z\s]+:|$)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return skills

    skill_text = match.group(1)

    # Split by common delimiters: bullets, newlines, commas, pipes, semicolons
    parts = re.split(r'[•\n,;|\t]', skill_text)

    for part in parts:
        skill = part.strip()
        if not skill or len(skill) < 2:
            continue

        # Skip years/numbers
        if re.search(r'\d{4}', skill):
            continue

        # Canonicalize if in skills map
        skill_lower = skill.lower()
        canonical = SKILLS_MAP.get(skill_lower) or SKILLS_MAP.get(skill)
        if canonical:
            skills.append(canonical)
        else:
            # Keep as-is (title case)
            skills.append(skill.title())

    return list(set(skills))  # Remove duplicates
