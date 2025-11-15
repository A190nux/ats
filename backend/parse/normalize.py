"""
Normalization utilities for parsed CVs.

Functions:
- load_skills_map(path)
- normalize_skill(skill, skills_map, scorer)
- normalize_title(title)
- normalize_parsed_cv(parsed_dict, skills_map=None)
- deduplicate_candidates(candidates, threshold=90)

This module prefers `rapidfuzz` for fuzzy matching but falls back to simple
lowercase substring matching if not available.
"""
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import process, fuzz
    HAS_RAPIDFUZZ = True
except Exception:
    HAS_RAPIDFUZZ = False


def load_skills_map(path: str = None):
    """Load skills map JSON from project data directory.

    Returns a dict mapping normalized skill -> canonical skill or taxonomy.
    """
    default = Path(__file__).parent.parent.parent / "data_schemas" / "skills_map.json"
    p = Path(path) if path else default
    if not p.exists():
        logger.warning(f"Skills map not found at {p}; continuing without mapping")
        return {}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Normalize keys to lowercase
        norm = {k.lower(): v for k, v in data.items()}
        return norm
    except Exception as e:
        logger.warning(f"Failed to load skills map: {e}")
        return {}


def normalize_skill(skill: str, skills_map: dict, top_k: int = 1):
    """Normalize a single skill string to a canonical skill using skills_map.

    Uses rapidfuzz when available; otherwise falls back to lowercasing and exact
    or substring matching.
    Returns canonical skill (string) or original trimmed skill.
    """
    if not skill or not skill.strip():
        return None
    s = skill.strip()
    s_low = s.lower()
    # direct map
    if skills_map and s_low in skills_map:
        return skills_map[s_low]

    # rapidfuzz fuzzy match against keys
    if skills_map and HAS_RAPIDFUZZ:
        choices = list(skills_map.keys())
        match = process.extractOne(s_low, choices, scorer=fuzz.WRatio)
        if match and match[1] >= 80:
            k = match[0]
            return skills_map.get(k, s)

    # fallback: substring match
    if skills_map:
        for k in skills_map.keys():
            if k in s_low or s_low in k:
                return skills_map.get(k, s)

    return s


def normalize_title(title: str):
    """Normalize job title by simple heuristics.

    - Lowercase, strip, collapse multiple spaces
    - Map common short forms
    """
    if not title:
        return None
    t = " ".join(title.strip().split())
    low = t.lower()
    # simple replacements
    replacements = {
        "svr": "senior",
        "sr": "senior",
        "jr": "junior",
        "dev": "developer",
        "eng": "engineer",
        "ml eng": "machine learning engineer",
    }
    for k, v in replacements.items():
        if low == k or low.startswith(k + " ") or (" " + k + " ") in (" " + low + " "):
            low = low.replace(k, v)
    # Title case for readability
    return low.title()


def normalize_parsed_cv(parsed: dict, skills_map: dict = None):
    """Normalize only the skills list on the parsed CV and attach a
    lightweight `normalized.skills` subtree. Do not alter other fields.

    This keeps normalization focused and safe while still providing a
    canonical skills list for indexing and matching.
    """
    if not isinstance(parsed, dict):
        return parsed

    skills_map = skills_map or load_skills_map()

    raw_skills = parsed.get('skills') or []
    normalized_skills = []
    seen = set()
    for s in raw_skills:
        if not isinstance(s, str):
            continue
        can = normalize_skill(s, skills_map)
        if not can:
            continue
        # deduplicate canonical names
        if can in seen:
            continue
        normalized_skills.append(can)
        seen.add(can)

    # Attach or update normalized subtree with just skills
    norm = parsed.get('normalized') if isinstance(parsed.get('normalized'), dict) else {}
    norm['skills'] = normalized_skills
    parsed['normalized'] = norm
    return parsed


def deduplicate_candidates(candidates: list, threshold: int = 95):
    """Deduplicate a list of candidate dicts by email/phone/name similarity.

    Returns a list of unique candidates (keeps first occurrence).
    Uses rapidfuzz if available; otherwise does exact email/phone match.
    """
    if not candidates:
        return []

    unique = []
    seen_emails = set()
    seen_phones = set()
    names = []

    for c in candidates:
        contact = c.get('normalized', {}).get('contact') or c.get('contact') or {}
        email = (contact.get('email') or '').lower() if contact.get('email') else None
        phone = contact.get('phone') if contact.get('phone') else None
        name = (c.get('normalized', {}).get('name') or c.get('name') or '').strip()

        duplicate = False
        if email and email in seen_emails:
            duplicate = True
        if phone and phone in seen_phones:
            duplicate = True
        if not duplicate and name and HAS_RAPIDFUZZ and names:
            # fuzzy name match
            match = process.extractOne(name, names, scorer=fuzz.WRatio)
            if match and match[1] >= threshold:
                duplicate = True

        if not duplicate:
            unique.append(c)
            if email:
                seen_emails.add(email)
            if phone:
                seen_phones.add(phone)
            if name:
                names.append(name)

    return unique
