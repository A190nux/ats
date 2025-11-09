import re
import json
from typing import Dict, List, Set, Optional
from pathlib import Path

try:
    import dateparser
except Exception:
    dateparser = None

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


def _safe_search(pattern: str, text: str, flags=0) -> Optional[re.Match]:
    try:
        return re.search(pattern, text, flags)
    except re.error:
        return None


def extract_name_contacts(text: str) -> Dict[str, Optional[str]]:
    """Extract name and common contact fields from resume text.

    Heuristics used (format-agnostic):
    - Regex for email, phone, linkedin, github anywhere in text
    - Name heuristics: prefer first non-empty line(s) that are not contact lines,
      allow Title Case or ALL CAPS. If spaCy is installed and name not found,
      attempt NER on the first 800 characters.

    Returns a dict: {name, email, phone, linkedin, github}
    """
    if not text:
        return {k: None for k in ('name', 'email', 'phone', 'linkedin', 'github')}

    # Normalize
    t = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = [l.strip() for l in t.split('\n') if l.strip()]

    email_m = _safe_search(r"[\w\.-]+@[\w\.-]+\.[A-Za-z]{2,}", t)
    phone_m = _safe_search(r"(\+?\d[\d\s\-\(\)\.]{6,}\d)", t)
    linkedin_m = _safe_search(r"(https?://)?(www\.)?linkedin\.com\/[A-Za-z0-9\-_/]+", t, re.I)
    github_m = _safe_search(r"(https?://)?(www\.)?github\.com\/[A-Za-z0-9\-_/]+", t, re.I)

    def clean_phone(p: Optional[re.Match]) -> Optional[str]:
        if not p:
            return None
        s = p.group(0)
        s = re.sub(r"[\s\-\.]+", " ", s).strip()
        return s

    result = {
        'name': None,
        'email': email_m.group(0) if email_m else None,
        'phone': clean_phone(phone_m) if phone_m else None,
        'linkedin': linkedin_m.group(0) if linkedin_m else None,
        'github': github_m.group(0) if github_m else None,
    }

    # Try name heuristics from top N lines
    candidate = None
    max_lines = min(6, len(lines))
    for i in range(max_lines):
        line = lines[i]
        # skip if looks like contact line
        if any(tok in line.lower() for tok in ('@', 'linkedin.com', 'github.com', 'phone', 'tel', 'www.')):
            continue
        # if line contains many uppercase words or Title Case, it's likely a name
        words = line.split()
        if 1 < len(words) <= 6:
            # Filter out lines with digits or many symbols
            if any(c.isdigit() for c in line):
                continue
            # Accept Title Case or ALLCAPS
            if all(w.istitle() or w.isupper() for w in words):
                candidate = ' '.join(w.title() for w in words)
                break
            # Accept short lines with 2-3 words and no punctuation
            if 2 <= len(words) <= 4 and re.match(r"^[A-Za-z\-']+(\s+[A-Za-z\-']+){1,3}$", line):
                candidate = ' '.join(w.title() for w in words)
                break

    # As a last resort, try spaCy NER if available
    if not candidate:
        try:
            import spacy
            nlp = spacy.load("en_core_web_sm")
            doc = nlp('\n'.join(lines[:6]))
            persons = [ent.text for ent in doc.ents if ent.label_ == 'PERSON']
            if persons:
                candidate = persons[0]
        except Exception:
            pass

    result['name'] = candidate
    return result


def split_sections(text: str) -> Dict[str, str]:
    """Split resume text into sections using flexible heading detection.

    Heuristics:
    - Lines that are short (<=5 words) and either ALL CAPS or end with ':' or are common headings
    - Fuzzy-match common headings (SKILLS, EXPERIENCE, EDUCATION, PROJECTS, SUMMARY, LANGUAGES, CERTIFICATIONS)
    - If no headings found, return {'BODY': full_text}
    """
    if not text:
        return {}

    t = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = t.split('\n')

    common = ['SUMMARY', 'PROFESSIONAL SUMMARY', 'EDUCATION', 'EXPERIENCE', 'WORK EXPERIENCE', 'SKILLS',
              'PROJECTS', 'SELECTED PROJECTS', 'PUBLICATIONS', 'CERTIFICATIONS', 'LANGUAGES', 'AWARDS',
              'CONTACT', 'PROFILE']
    common_lc = [c.lower() for c in common]

    section_indices = []  # list of (index, heading)
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        # candidate heading if short
        words = line.split()
        if len(words) <= 6:
            # remove trailing ':'
            candidate = line.rstrip(':').strip()
            # check exact fuzzy match
            if candidate.lower() in common_lc:
                section_indices.append((i, candidate.upper()))
                continue
            # ALL CAPS
            if candidate.isupper() and len(candidate) > 1 and re.search(r'[A-Z]', candidate):
                section_indices.append((i, candidate.upper()))
                continue
            # Ends with ':'
            if raw.strip().endswith(':'):
                section_indices.append((i, candidate.upper()))
                continue

    if not section_indices:
        return {'BODY': t.strip()}

    sections = {}
    for idx, (line_idx, heading) in enumerate(section_indices):
        start = line_idx + 1
        end = section_indices[idx + 1][0] if idx + 1 < len(section_indices) else len(lines)
        body = '\n'.join(l for l in lines[start:end]).strip()
        sections[heading] = body

    return sections


def extract_skills(text: str) -> Set[str]:
    """Extract and canonicalize skills from the document.

    Strategy:
    - If there's a SKILLS section, parse delimited tokens
    - Do a global pass for known skill variants from SKILLS_MAP
    - Return a set of normalized skill names
    """
    skills: Set[str] = set()
    if not text:
        return skills

    sections = split_sections(text)
    skill_text = ''
    if 'SKILLS' in sections:
        skill_text = sections['SKILLS']
    else:
        # Heuristic: look for a line that starts with 'Skills' anywhere
        m = re.search(r"(?im)^skills?[:\-\s]+(.+)$", text)
        if m:
            skill_text = m.group(1)

    # Tokenize skill_text
    if skill_text:
        parts = re.split(r'[•\n,;|\t]', skill_text)
        for p in parts:
            s = p.strip()
            if not s:
                continue
            s_key = s.lower()
            canonical = SKILLS_MAP.get(s_key) or SKILLS_MAP.get(s)
            if canonical:
                skills.add(canonical)
            else:
                # filter out short noise
                if len(s) > 1 and not re.search(r'\d{4}', s):
                    skills.add(s.title())

    # global mapping pass
    for variant, canonical in SKILLS_MAP.items():
        if re.search(r'\b' + re.escape(variant) + r'\b', text, re.I):
            skills.add(canonical)

    return skills


def _find_date_strings(block: str) -> List[str]:
    """Return substrings that look like dates or date ranges inside block."""
    patterns = [
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
        r"\b\d{4}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b(?:present|now|current)\b",
    ]
    found = []
    for p in patterns:
        for m in re.finditer(p, block, re.I):
            found.append(m.group(0))
    return found


def parse_experience_section(text: str, nlp=None) -> List[Dict]:
    """Parse the EXPERIENCE section into structured entries.

    This function is intentionally forgiving: it groups by blank-line-separated blocks
    or by bullets, then attempts to extract dates, title, company and description.
    If `nlp` (spaCy model) is provided, it will be used to detect ORG entities.
    """
    entries: List[Dict] = []
    if not text:
        return entries

    # Normalize bullets and split into blocks (blank-line separated)
    blocks = [b.strip() for b in re.split(r'\n\s*\n', text) if b.strip()]
    # If the section is a single long block, further split on lines that look like headers
    if len(blocks) == 1:
        lines = [l for l in blocks[0].split('\n') if l.strip()]
        # split when a line looks like 'Title at Company — Dates' or starts with a date
        candidate_indices = []
        for i, ln in enumerate(lines):
            if re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', ln, re.I) or re.search(r'\d{4}', ln):
                candidate_indices.append(i)
        if candidate_indices and candidate_indices[0] > 0:
            # split before each candidate index
            new_blocks = []
            cur = []
            for i, ln in enumerate(lines):
                if i in candidate_indices and cur:
                    new_blocks.append('\n'.join(cur))
                    cur = [ln]
                else:
                    cur.append(ln)
            if cur:
                new_blocks.append('\n'.join(cur))
            blocks = new_blocks

    for block in blocks:
        # Build a simple record
        rec = {'job_title': None, 'company': None, 'start_date': None, 'end_date': None, 'description': None}
        # First line often contains title/company/dates
        first_line = block.split('\n', 1)[0].strip()

        # Try to find date range in the block
        date_range = None
        # look for patterns like 'Jan 2020 - Present' or '2020 – 2022'
        m = _safe_search(r'(?P<start>(?:[A-Za-z]{3,9}\s+\d{4}|\d{4}|present|current))\s*(?:[-–—to]+)\s*(?P<end>(?:[A-Za-z]{3,9}\s+\d{4}|\d{4}|present|current))', block, re.I)
        if m:
            date_range = (m.group('start'), m.group('end'))
        else:
            # fallback: look for two date-like strings in block
            dates = _find_date_strings(block)
            if len(dates) >= 2:
                date_range = (dates[0], dates[1])
            elif len(dates) == 1:
                date_range = (dates[0], None)

        if date_range and dateparser:
            try:
                sd = dateparser.parse(date_range[0]) if date_range[0] else None
                ed = dateparser.parse(date_range[1]) if date_range[1] else None
                rec['start_date'] = sd.strftime('%Y-%m') if sd else None
                if ed:
                    rec['end_date'] = ed.strftime('%Y-%m')
                else:
                    # if end is 'present' or None, leave as None or 'Present'
                    if date_range[1] and re.search(r'present|current', date_range[1], re.I):
                        rec['end_date'] = 'Present'
            except Exception:
                pass

        # Identify company and title
        # Common patterns: 'Senior ML Engineer at Acme Corp', 'Acme Corp — Senior ML Engineer', 'Senior ML Engineer, Acme'
        # Try ' at '
        if ' at ' in first_line.lower():
            parts = re.split(r'\s+at\s+', first_line, flags=re.I)
            rec['job_title'] = parts[0].strip()
            rec['company'] = parts[1].strip() if len(parts) > 1 else None
        else:
            # Try splitting on '—' or '-' or ',' with heuristic
            parts = re.split(r'\s+[–—\-]\s+|\s*,\s*', first_line)
            if len(parts) >= 2:
                # Heuristic: shorter part is title (<=5 words)
                if len(parts[0].split()) <= 6:
                    rec['job_title'] = parts[0].strip()
                    rec['company'] = parts[1].strip()
                else:
                    rec['company'] = parts[0].strip()
                    rec['job_title'] = parts[1].strip()
            else:
                # Use spaCy NER if available to find ORG
                if nlp is not None:
                    try:
                        doc = nlp(first_line)
                        orgs = [ent.text for ent in doc.ents if ent.label_ == 'ORG']
                        persons = [ent.text for ent in doc.ents if ent.label_ == 'PERSON']
                        if orgs:
                            rec['company'] = orgs[-1]
                            # title is what's left
                            rec['job_title'] = first_line.replace(orgs[-1], '').strip(' ,–—-')
                        elif persons:
                            # If name present in line, probably not title/company; keep as description
                            rec['job_title'] = first_line
                        else:
                            rec['job_title'] = first_line
                    except Exception:
                        rec['job_title'] = first_line
                else:
                    rec['job_title'] = first_line

        # Description is everything after the first line
        rest = block.split('\n', 1)
        if len(rest) > 1:
            rec['description'] = rest[1].strip()

        # Normalize empty strings to None
        for k, v in list(rec.items()):
            if isinstance(v, str) and not v.strip():
                rec[k] = None

        entries.append(rec)

    return entries


def parse_education_section(text: str, nlp=None) -> List[Dict]:
    """Parse the EDUCATION section into structured education entries.

    Returns a list of dicts with keys: institution, degree, major, graduation_year, start_year, raw
    Uses heuristics and optional spaCy NER for ORG detection and dateparser for dates.
    """
    # Simplified, conservative education parser.
    ed_entries: List[Dict] = []
    if not text:
        return ed_entries

    # Split on blank lines to get candidate blocks. This is general and avoids
    # brittle per-line heuristics tied to one CV layout.
    blocks = [b.strip() for b in re.split(r'\n\s*\n', text) if b.strip()]
    if not blocks:
        blocks = [text.strip()]

    # Lightweight patterns
    year_re = re.compile(r'\b(19\d{2}|20\d{2})\b')
    degree_re = re.compile(r'\b(Bachelor|Master|B\.Sc|BSc|M\.Sc|MSc|PhD|Doctor|Diploma|Certificate|Associate|MBA)\b', re.I)
    inst_re = re.compile(r'\b(University|Institute|College|Faculty|School|Academy|ITI)\b', re.I)

    for block in blocks:
        rec = {'institution': None, 'degree': None, 'major': None, 'graduation_year': None, 'start_year': None, 'raw': block}

        # Year(s)
        years = year_re.findall(block)
        if years:
            try:
                rec['graduation_year'] = int(years[-1])
                if len(years) >= 2:
                    rec['start_year'] = int(years[0])
            except Exception:
                pass

        # Degree (keep it short, do not capture long surrounding text)
        m = degree_re.search(block)
        if m:
            rec['degree'] = m.group(0).strip().title()

        # Institution via spaCy NER if available, else simple keyword match
        if nlp is not None:
            try:
                doc = nlp(block)
                orgs = [ent.text for ent in doc.ents if ent.label_ == 'ORG']
                if orgs:
                    rec['institution'] = orgs[0]
            except Exception:
                pass

        if not rec['institution']:
            inst_m = inst_re.search(block)
            if inst_m:
                # take the whole line containing the institution keyword (conservative)
                lines = [l.strip() for l in block.split('\n') if l.strip()]
                for ln in lines:
                    if inst_re.search(ln):
                        rec['institution'] = ln
                        break

        # Major: look for short 'in <major>' patterns; keep concise
        maj_m = re.search(r'\bin\s+([A-Za-z &/\-]{2,80})', block, re.I)
        if maj_m:
            rec['major'] = maj_m.group(1).strip().title()

        # Only accept if there's some evidence: degree, institution, or year
        if rec['degree'] or rec['institution'] or rec['graduation_year']:
            ed_entries.append(rec)

    return ed_entries
